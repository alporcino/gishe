"""
Gishe asistanının Türkçe dil katmanı: soruyu aramadan ÖNCE anlamlandırır.

Neden gerekli?
  - Öğrenciler Türkçe karakter kullanmadan yazar: "kayit dondurma", "devamsizlik".
  - Kısaltma ve günlük dil kullanır: "büt", "vize", "GANO", "add-drop", "bölüm değiştirmek".
  - Türkçede EŞ SESLİ kelimeler çoktur ve yanlış anlam yanlış maddeyi getirir:
      yaz   -> "yazın yurtta kalabilir miyim" (yaz dönemi)  /  "dilekçe nasıl yazılır" (yazmak)
      kal   -> "dersten kaldım" (başarısız)  /  "yurtta kalmak" (konaklama)  /  "tek dersim kaldı" (geriye kalan)
      geç   -> "dersi geçmek" (başarı)  /  "başka bölüme geçmek" (yatay geçiş)  /  "kayda geç kaldım" (gecikme)
      kredi -> "kaç kredi ders" (AKTS)  /  "KYK kredim kesildi" (öğrenim kredisi, üniversitenin konusu değil)
      bırak -> "dersi bırakmak" (ders çıkarma)  /  "okulu bırakmak" (üniversiteden ayrılma)
      izin  -> öğrenci için yarıyıl izni (kayıt dondurma)  /  akademisyen için yıllık izin
      rapor -> "rapor aldım" (sağlık raporu, mazeret)  /  "staj raporu"
      lisans-> "yazılım lisansı"  /  "lisans programı"
    Bu modül cümlenin geri kalanına bakarak doğru anlamı seçer ve aramaya yönetmeliğin kendi
    kelimelerini ekler; yanlış anlama götürecek kelimeyi aramadan çıkarır.
  - Selam, teşekkür, vedalaşma gibi sohbet mesajlarını tanır (bunlar yönetmelikte aranmaz).

Hepsi kural tabanlıdır, dış servis veya ek paket gerektirmez; ne yaptığı okunarak anlaşılabilir.
"""
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Temel metin işlemleri
# ---------------------------------------------------------------------------
_KATLAMA = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def kucult(metin: str) -> str:
    """Türkçe'ye uygun küçük harf (I -> ı, İ -> i)."""
    return metin.replace("I", "ı").replace("İ", "i").lower()


def katla(metin: str) -> str:
    """Küçük harf + Türkçe karakterleri sadeleştirir: "Kaydımı Dondurmak" -> "kaydimi dondurmak".
    Hem yönetmelikler hem sorular aynı biçime getirildiği için "kayit" ile "kayıt" eşleşir."""
    return kucult(metin).translate(_KATLAMA)


# Ayrı yazılınca anlamını yitiren ifadeler tek kelimeye çevrilir (hem metinlerde hem sorularda)
_BIRLESTIR = [
    (r"\be\s*-?\s*posta", "eposta"),
    (r"\bd\s+sinav", "dsinav sinav"),
    (r"\bcift\s+ana\s*dal", "ciftanadal"),
    (r"\bcift\s+anadal", "ciftanadal"),
    (r"\byan\s*-?\s*dal", "yandal"),
    (r"\bana\s+dal", "anadal"),
    (r"\btek\s+ders", "tekders"),
    (r"\bwi\s*-?\s*fi\b", "wifi"),
    (r"\badd\s*-?\s*drop\b", "adddrop"),
    (r"\bkatki\s+payi", "katkipayi"),
    (r"\bis\s+gun", "isgun"),
    # "yurt içi / yurt dışı" (ülke) ile "yurt" (yurt binası) karışmasın
    (r"\byurt\s*-?\s*ici", "yurtici"),
    (r"\byurt\s*-?\s*disi", "yurtdisi"),
]
_IKI_HARFLI = {"ff", "dd", "dc", "cc", "cb", "bb", "ba", "aa", "na", "vf", "ex", "nc"}


def birlestir(katli: str) -> str:
    for desen, yerine in _BIRLESTIR:
        katli = re.sub(desen, yerine, katli)
    return katli


def kelimeler(metin: str) -> list[str]:
    """Metnin sadeleştirilmiş kelimeleri. Harf notları (FF, DD, CC…) iki harfli olsa da korunur."""
    katli = birlestir(katla(metin))
    return [k for k in re.findall(r"[a-z0-9]+", katli) if len(k) > 2 or k in _IKI_HARFLI]


# Aramada anlam taşımayan kelimeler (sadeleştirilmiş biçimde)
DURAKLAR = set(katla("""
ve ile bir bu şu o için mi mı mu mü ne neden niye nasıl nedir neler nerede nereden nereye hangi hangisi kim kime
ben benim bana beni sen senin sana biz bize siz size var yok olarak olur olursa olabilir olmalı olmalıyım
gibi daha de da ki ya yani veya ama fakat ancak çok en her kadar sonra önce olan ise eğer acaba şey şeyler
istiyorum isterim istersem istiyor ister isteyen lazım gerek gerekli gerekir gerekiyor gereken gerekmektedir
miyim mıyım muyum müyüm misin mısın musun müsün midir mıdır mudur müdür miydi
merhaba selam lütfen teşekkürler teşekkür öğrenci öğrenciyim öğrenciler üniversite üniversitede üniversitenin
okul gtü gebze teknik hocam abi abla
yapmalıyım yapmam yapmak yapabilirim yapabilir yapılır yapılmalı yapılıyor yaparım yapıyorum
edebilir edebilirim edilir edilmeli ediyor ederim alabilirim alabilir alınır alınabilir alınıyor alırım
söyler söyle söyleyebilir anlat anlatır anlatabilir misiniz hakkında bilgi bilgisi
zaman zamanı olmalı nedir neler nelerdir kaç kaçtır tane mümkün
kimler kimlerden kimden kime kimlere kimin kimse nedenle niçin nasıldır ne zaman nereye nerden hangisi hangileri
eder eden ederse ediliyor edilmiş etmek etmem etmeliyim etsem ettim olabilmem olabilmek olmam olmak olsun olsa
oluyor olacak oldu olmuş olmaz olmuyor olmaması yapayım yapsam yaparsam yapılması yaptım yapacağım
alınması alınabilmesi alabilmem almam gerekmez gerekenler lazımdı istiyordum isteyebilir miyiz muyuz müyüz
aynı anda şimdi hemen artık bile sadece hep hiç bazen biraz gerçekten tam
aldım aldık aldın aldı aldığım aldığımız alıyor alıyorum alırsam alsam almam almak almalıyım alınca
şart şartı şartlar şartları şartlarını koşul koşulu koşullar koşulları gereklilik gereklilikler
olamıyorum olamam olamaz olamadım olacak olacağım olur muyum olunur olunuyor
kere kez defa gelen gelince almalı almalıyım almalı mıyım alınmalı
nedeniyle nedenle yüzünden dolayı sebebiyle sebebi için ötürü olmadan olmaksızın
yapan yapanlar yapanların olunca olduğunda olursa arasındaki arasında fark farkı farklar
""").split())

# ---------------------------------------------------------------------------
# Kök bulma: Türkçe eklemeli bir dildir. Kelimenin sonundaki ekler atılır, kalan kök en fazla
# 6 harfle tutulur: "yurtlarda", "yurdu" -> "yurt"; "kaydımı" -> "kayit"; "notlarım" -> "not".
# ---------------------------------------------------------------------------
_EKLER = sorted(set("""
lerinden larindan lerinde larinda lerine larina lerini larini lerin larin leri lari ler lar
imizden imizde imize imizi imiz umuz iniz unuz ndeki ndaki deki daki teki taki
sinden sindan sinde sinda sine sina sini sinin sunun inden indan inde inda ine ina ini inin unun
nden ndan nde nda dan den tan ten
abilir ebilir abilecek ebilecek abiliyor ebiliyor amaz emez amiyor emiyor amadim emedim
acagim ecegim acak ecek iyorum uyorum iyor uyor
mak mek mali meli
dim dum tim tum dik duk tik tuk diniz
mis mus
irsam ursam arsam ersem irsem irse urse arsa erse sam sem
yla yle nin nun lik luk
da de ta te in un im um si su ya ye yi yu na ne ni nu la le di du ti tu sa se i u a e
""".split()), key=len, reverse=True)

# 3 harfli kökte de güvenle atılabilen ekler (labda -> lab, yüzde -> yüz, hızla -> hız)
_KISA_KOKTE_ATILIR = {"da", "de", "ta", "te"}
# Ek atılınca kökün son ünsüzü yumuşamış olabilir (kitabı -> kitap, yurdu -> yurt, dileği -> dilek)
_YUMUSAMA = {"b": "p", "d": "t", "g": "k"}
# Ek gelince ünlüsü düşen kelimeler (kayıt -> kaydı, kayıp -> kaybı, vakit -> vakti)
_DUSME = {"izn": "izin", "kayd": "kayit", "kayb": "kayip", "vakt": "vakit", "isim": "isim", "ism": "isim", "hakk": "hak",
          "akl": "akil", "sehr": "sehir", "fikr": "fikir", "hukm": "hukum", "ogl": "ogul", "agz": "agiz"}
# Ek atmanın yanlış sonuç verdiği kelimeler (olduğu gibi kalır)
_DOKUNMA = {"devam", "mezun", "staj", "yatay", "harc", "burs", "akts", "ders", "dekan", "kampus", "erasmus",
            "sinav", "tatil", "eduroam", "yemek", "rapor", "lisans", "lisansustu", "kredi", "ilan", "iban", "dilekce",
            "yazici", "yazilim", "senato", "komisyon", "kontenjan", "transkript", "diploma", "hazirlik", "ucret",
            "sinamali", "eposta", "yoklama", "hafta", "akademik", "takvim", "yariyil", "donem", "kayit", "ortalama",
            "dsinav", "tekders", "yandal", "anadal", "ciftanadal", "katkipayi", "isgun", "laboratuvar", "danisman",
            "yurtici", "yurtdisi", "belge", "saglik", "secmeli", "zorunlu", "saat", "oda"}


_DOKUNMA_UZUNDAN = sorted(_DOKUNMA, key=len, reverse=True)
# Mevsim anlamındaki "yazın/yazları" (Türkçe karakterler sadeleşince "yazı" ile karışmasın)
_MEVSIM = {"yazin", "yazlari", "yazlarin", "yazlar", "yazdan", "yazinda"}


def kok(kelime: str) -> str:
    k = kelime
    if k in _DOKUNMA or k.isdigit():
        return k[:6]
    if k in _MEVSIM:
        return "yaz"
    for dk in _DOKUNMA_UZUNDAN:
        if k.startswith(dk) and len(k) > len(dk):
            return dk[:6]
    for bas, yerine in _DUSME.items():  # kaydımı, kaydını, kaybettim -> kayıt, kayıp
        if k.startswith(bas) and len(k) > len(bas) and k[len(bas)] in "aeiou":
            return yerine[:6]
    son_ek = ""
    for tur in range(4):
        for ek in _EKLER:
            if k.endswith(ek):
                kalan = k[: -len(ek)]
                # Kısa ek atıldıktan sonra kök en az 4, uzun ek atıldıktan sonra en az 3 harf kalmalı.
                # "labda", "yüzde" gibi kısa köklerde bulunma eki ilk turda atılabilir.
                kisa_izin = len(ek) >= 3 or (ek in _KISA_KOKTE_ATILIR and tur == 0)
                if len(kalan) >= (3 if kisa_izin else 4) or kalan in _DOKUNMA:
                    k, son_ek = kalan, ek
                    break
        else:
            break  # atılacak ek kalmadı
        if k in _DOKUNMA:
            break
    if son_ek:
        k = _DUSME.get(k, k)
        # Ünsüz yumuşaması sadece ünlüyle başlayan ekten önce olur (kitab-ı, yurd-u); "labda" -> "lab" kalır
        if son_ek[0] in "aeiou" and k[-1] in _YUMUSAMA and k not in _DOKUNMA:
            k = k[:-1] + _YUMUSAMA[k[-1]]
    return k[:6]


# Soru kalıplarının kökleri de aranmaz ("kimlere" -> "kim", "olabilmem" -> "olabil")
_DURAK_KOKLERI = {kok(w) for w in DURAKLAR if len(w) > 3} | {"olabil", "yapabi", "edebil", "alabil", "gereki", "isteri",
                                                            "kim", "yapay", "nasil", "neden", "nere", "aldim", "aldig",
                                                            "aliyor", "alir", "alsam", "dus", "sart", "kosul", "olam",
                                                            "olunur", "almal", "kere"}


def kokler(metin: str) -> list[str]:
    """Metindeki anlamlı kelimelerin kökleri (sırayla, tekrarlı)."""
    return [k for k in (kok(w) for w in kelimeler(metin) if w not in DURAKLAR) if k not in _DURAK_KOKLERI]


def benzerlik(a: str, b: str) -> float:
    """İki kökün benzerliği: 1 güçlü (biri ötekinin başı ya da ilk 5 harf ortak),
    0.4 zayıf (sadece ilk 4 harf ortak, ör. sınır/sınıf), 0 yok."""
    if a == b:
        return 1.0
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    kisa = min(len(a), len(b))
    if n == kisa and kisa >= 3:
        k, u = (a, b) if len(a) <= len(b) else (b, a)
        if any(u.startswith(x) for x in _ON_EK_ENGEL.get(k, ())):
            return 0.0
        return 1.0
    if n >= 5:
        return 1.0
    return 0.4 if n >= 4 else 0.0


# Kısa kökün, başı aynı ama anlamı farklı uzun kelimelerle eşleşmesi engellenir:
# "yaz" (yaz dönemi) ~ "yazılı/yazı" (yazmak), "not" ~ "noter"
_ON_EK_ENGEL = {"yaz": ("yazi",), "not": ("noter",), "ara": ("arac",), "yurt": ("yurtic", "yurtdi"), "oku": ("okul",)}


_FIIL_SONU = re.compile(r"(inca|ince|unca|unce|ken|sem|sam|mak|mek|iyor\w*|uyor\w*|acak\w*|ecek\w*|dim|dum|tim|tum|dik|duk|"
                        r"mis|mus|abil\w*|ebil\w*|meli\w*|mali\w*|irim|arim|urum|erim|ersem|arsam|irsem|irsam|ursam|"
                        r"ayim|eyim|elim|alim|siniz|mez|maz|mesem|masam|medim|madim|meyen|mayan|ilir|ulur|inir|unur)$")
_GENIS_ZAMAN = re.compile(r"^[a-z]{1,4}(ar|er|ir|ur)$")  # kısa geniş zaman fiilleri: uzar, geçer, olur (misafir, odalar değil)


def fiil_gibi(kelime: str) -> bool:
    """Kelime çekimli bir fiile benziyor mu? ("gidince", "uzar", "gelmesem") Bu tür kelimeler sorunun
    konusunu değil söyleniş biçimini taşır."""
    if len(kelime) <= 3 or kelime.endswith(("lar", "ler")):
        return False
    return bool(_FIIL_SONU.search(kelime) or _GENIS_ZAMAN.match(kelime))


# ---------------------------------------------------------------------------
# Anlam çözme (eş sesli kelimeler, kısaltmalar, günlük dil)
# Her kural: (sorunun sadeleştirilmiş hâlinde aranacak desen, aramaya EKLENECEK yönetmelik kelimeleri,
#             aramadan ÇIKARILACAK kelimelerin deseni, etiket). Kurallar sırayla uygulanır.
# ---------------------------------------------------------------------------
_YAZMA_BAGLAMI = r"(dilekce|siir|mektup|hikaye|makale|odev|metin|kompozisyon|cv|ozgecmis|mail|eposta|mesaj|kod|yazi|cevap|yorum)"
_YAZMA_FIIL = r"\byaz(mak|maliyim|mali|malisin|dim|din|di|dik|acagim|acak|iyorum|iyor|ilir|ilmali|ayim|ar misin|abilir\w*|ar|sana|sene|sin|iniz|in bana|ar misiniz)\b"
_GECME_BAGLAMI = r"(ders\w*|not\w*|sinav\w*|final\w*|vize\w*|ff|dd|dc|cc|hazirli\w*|donem\w*|sinif\w*)"


@dataclass
class Kural:
    desen: str
    ekle: str = ""
    sil: str | None = None
    etiket: str = ""
    rol: str | None = None  # sadece bu rol için
    engel: tuple = ()       # bu etiketlerden biri zaten seçildiyse kural uygulanmaz
    haric: str | None = None  # soruda bu desen varsa kural uygulanmaz
    zayif: bool = False       # eklediği kelimeler sorunun konusu sayılmaz (ör. "hoca" -> "öğretim elemanı")


KURALLAR = [
    # ---- YAZ: yazmak (dilekçe, şiir, rapor…) -> "yaz" kelimesi aranmaz; yaz dönemi sanılmasın
    Kural(rf"\b{_YAZMA_BAGLAMI}\w*\b.*\byaz|\byaz\w*\b.*\b{_YAZMA_BAGLAMI}", sil=r"\byaz(?!ili\b|ici\b|ilim\w*)\w*", etiket="yaz_yazmak"),
    Kural(_YAZMA_FIIL, sil=_YAZMA_FIIL, etiket="yaz_yazmak"),
    Kural(r"\brapor\w*\b.*\byaz|\byaz\w*\b.*\brapor", sil=r"\byaz(?!ili\b|ici\b|ilim\w*)\w*", etiket="yaz_yazmak"),
    # ---- YAZ: mevsim ("yazın", "yaz okulu", "yaz döneminde")
    Kural(r"\byaz(in|lari|larin|a|da|dan)?\b", ekle="yaz donemi ogretimi", etiket="yaz_donem", engel=("yaz_yazmak",)),
    # ---- GEÇ: "geçen süre", "transkripte geçer" (geçmek = sayılmak/işlenmek)
    Kural(r"\bgec(en|irdigim|irilen|tigi)\b", sil=r"\bgec\w*", etiket="gec_sure"),
    Kural(r"transkript\w*\b.*\bgec\w*|\bgec\w*\b.*transkript", ekle="transkript", sil=r"\bgec(?!is)\w*", etiket="gec_islenme"),
    # ---- GEÇ KAL: gecikme
    Kural(r"\bgec\s+kal\w*", ekle="mazeretli sure", sil=r"\bgec\b|\bkal\w*", etiket="gec_gecikme"),
    # ---- GEÇ: dersi / hazırlığı geçmek (başarı)
    Kural(rf"\b{_GECME_BAGLAMI}\b.*\bgec(?!is)\w*|\bgec(?!is)\w*\b.*\b{_GECME_BAGLAMI}",
          ekle="basari ile tamamlamak basarili", sil=r"\bgec(?!is)\w*", etiket="gec_basari",
          engel=("gec_sure", "gec_islenme", "gec_gecikme"), haric=r"bolum\w*\s+degis|baska\s+(bolum|universite|fakulte|program)"),
    # ---- GEÇ: başka bölüme / üniversiteye geçmek (yatay geçiş)
    Kural(r"(bolum\w*|universite\w*|fakulte\w*|program\w*|gtu\w*|okul\w*|muhendislig\w*)\b.*\bgec(mek|ebil\w*|mey\w*|is\w*|ecek\w*|sem|tim|mem|meyi|mesi)?\b"
          r"|bolum\w*\s+degis\w*|\bbolum\w*\s+(degistir\w*|degisikli\w*)|\b\w+(e|a|ye|ya|ne|na)\s+gec(mek|ebilir\w*|ecegim|sem|mem)\b",
          ekle="yatay gecis", sil=r"\bgec(?!is)\w*|\bdegis\w*", etiket="gec_yatay",
          engel=("gec_basari", "gec_sure", "gec_islenme", "gec_gecikme")),
    # ---- KAL: konaklamak ("yurtta kalmak")
    Kural(r"\b(yurt\w*|kampus\w*|oda\w*|pansiyon\w*)\b.*\bkal\w*|\bkal\w*\b.*\b(yurt|kampus|pansiyon)\w*",
          ekle="yurtta kalabilir", etiket="kal_konaklama"),
    # ---- KAL: geriye kalan ("tek dersim kaldı", "son dersim kaldı", "mezuniyete bir ders kaldı")
    Kural(r"\b(tekders\w*|bir ders\w*|son ders\w*)\s+kal\w*|\bkal\w*\s+(tekders|bir ders)\w*|mezuniyet\w*\s+(tekders|bir ders)\w*",
          ekle="tekders sinavi", sil=r"\bkal\w*|\bson\b", etiket="kal_kalan", engel=("kal_konaklama",)),
    # ---- KAL: "kalan derslerim", "kaldığım dersler" (başarısız olunan dersler)
    Kural(r"\b(kalan|kaldigim|kaldigimiz)\s+ders\w*", ekle="basarisiz ders tekrari", sil=r"\bkal\w*", etiket="kal_basarisiz"),
    # ---- KAL: başarısız olmak ("dersten kaldım", "sınıfta kaldım", "FF ile kaldım")
    Kural(r"\b\w+(dan|den|tan|ten)\s+kal\w*|\bsinifta\s+kal\w*|\b(ff|na|vf)\b.*\bkal\w*|^kald\w*|\bkal(dim|irsam|irsan|dik|ma|irim|irsin|iriz|ir mi)\b(?!.*\b(yurt|kampus|oda|ev|pansiyon)\w*)"
          r"|\bders\w*\b.*\bkal(ir|acag|dig|an)\w*",
          ekle="basarisiz ders tekrari ff", sil=r"\bkal\w*", etiket="kal_basarisiz",
          engel=("kal_konaklama", "kal_kalan", "gec_gecikme", "kal_basarisiz"), haric=r"\b(gelme|gitme|katilma|girme)(sem|zsem|dim|mek)\b|kac\s+kere"),
    # ---- KREDİ: öğrenim kredisi (KYK) -> yönetmeliklerin konusu değil, AKTS ile karıştırılmasın
    Kural(r"\bkyk\b|kredi ve yurt|ogrenim kredi\w*|\bkredi\w*\b.*\b(borc\w*|odeme\w*|kesil\w*|yatma\w*|yatir\w*|faiz\w*)|\b(borc\w*|kesil\w*)\b.*\bkredi",
          sil=r"\bkredi\w*", etiket="kredi_kyk"),
    # ---- KREDİ: ders kredisi
    Kural(r"\bkredi\w*", ekle="kredi yuku akts", etiket="kredi_akts", engel=("kredi_kyk",)),
    # ---- BIRAK / ÇEKİL: ders
    Kural(r"\bders\w*\b.*\b(birak\w*|cekil\w*|sil\w*|cikar\w*)|\b(birak\w*|cekil\w*)\b.*\bders\w*|\badddrop\b|ekle\w* cikar\w*",
          ekle="ders ekleme cikarma", sil=r"\b(birak|cekil)\w*", etiket="birak_ders"),
    # ---- BIRAK: yan dal
    Kural(r"\byandal\w*\b.*\b(birak\w*|ayril\w*|cik\w*)", ekle="birakabilir kayit sildiren", etiket="birak_yandal"),
    # ---- BIRAK: okul / üniversite
    Kural(r"\b(okul\w*|universite\w*|egitim\w*|ogrenim\w*)\b.*\b(birak\w*|ayril\w*)|\b(kayd|kayit)\w*\s+sil\w*|ilisi\w*\s+kes\w*",
          ekle="universiteden ayrilma kaydi silinen", sil=r"\bbirak\w*", etiket="birak_okul"),
    # ---- İZİN: öğrenci için yarıyıl izni (kayıt dondurma)
    Kural(r"\bizin\w*|\bara\s+ver\w*|\bdondur\w*", ekle="yariyil izni kayit dondurma", etiket="izin_yariyil", rol="ogrenci",
          haric=r"\bstaj\w*|\bsinav\w*|\byillik\s+izin"),
    # ---- DEVAM: derse devam (yoklama, derse gelmemek)
    Kural(r"devamsiz\w*|yoklama\w*|\b(derse|derslere|derslerine)\s+devam|devam\s+(zorunlu\w*|sart\w*|durum\w*|etme\w*)|devam\w*\s+yuzde"
          r"|\bders\w*\b.*\b(gelme\w*|gitme\w*|katilma\w*|girme(sem|zsem|dim|mek)|kac\s+kere)|\bdevam\s+lazim|\blab\w*\b.*\bdevam",
          ekle="devam durumu zorunlulugu", sil=r"\b(sinir|limit|hakk|hakki|hakkim)\w*", etiket="devam"),
    # ---- RAPOR: sağlık raporu (mazeret) / staj raporu
    Kural(r"\b(hasta\w*|doktor\w*|saglik\w*|heyet\w*|raporlu\w*)\b|\brapor\w*\s+(aldim|aldi|var|aldik)\b",
          ekle="mazeret hakli gecerli nedenler", sil=r"\brapor\w*", etiket="rapor_saglik",
          haric=r"\b(izin|dondur|ara\s+ver|askerlik|maddi|ailevi|staj)\w*"),
    # ---- Sınava girememek (mazeret)
    Kural(r"\b(sinav|vize|final|ara sinav)\w*\b.*\b(giremedi\w*|girmedi\w*|katilamadi\w*|kacirdi\w*|giremeyece\w*)|\b(giremedi|katilamadi|kacirdi)\w*\b.*\b(sinav|vize|final)\w*",
          ekle="mazeret sinavi hakli gecerli", etiket="sinav_giremedim"),
    Kural(r"sinav\s+kagid\w*|kagidimi\s+gor\w*", ekle="itiraz sinav belgeleri tekrar inceleyerek", etiket="sinav_kagidi"),
    Kural(r"tekrar\s+sinav|sinav\w*\s+tekrar|ikinci\s+sinav|telafi\w*|ek\s+sinav", ekle="dsinav ff", etiket="tekrar_sinav"),
    # ---- GÖRÜŞ: görüşmek (buluşmak) / görüş (fikir)
    Kural(r"\bgorus(ebil|mek|mem|me|ecegim|tum|turme|melisin|meliyim|sem)\w*", sil=r"\bgorus\w*", etiket="gorusme"),
    # ---- LİSANS: yazılım lisansı
    Kural(r"\blisans\w*\b.*\b(yazilim|matlab|office|windows|autocad|solidworks|spss|bilgisayar|program)\w*|\b(yazilim|matlab|office|windows|autocad|solidworks|spss)\w*\b.*\blisans",
          ekle="yazilim lisanslari", etiket="lisans_yazilim"),
    # ---- Sınav adları
    Kural(r"\bfinal\w*", ekle="yariyil sonu sinavi", sil=r"\bfinal\w*", etiket="final"),
    Kural(r"\b(vize\w*|midterm\w*|ara\s+sinav\w*)", ekle="ara sinav yariyil ici", sil=r"\b(vize|midterm)\w*", etiket="vize"),
    Kural(r"\b(but|butunleme\w*|butler|bute)\b", ekle="dsinav ff", sil=r"\bbut\w*", etiket="butunleme"),
    Kural(r"\bmazeret\w*", ekle="mazeret sinavi", etiket="mazeret", haric=r"\b(kayit|kayd|kaydi)\w*"),
    # ---- Günlük dil -> yönetmelik dili
    Kural(r"\b(harc\w*|katkipayi\w*)", ekle="katkipayi ogrenim ucreti harc", etiket="harc"),
    Kural(r"\b(gano|agno|gno|gpa|ortalama\w*)\b", ekle="agirlikli genel not ortalamasi", etiket="ortalama"),
    Kural(r"erasmus\w*", ekle="degisim programi erasmus", etiket="erasmus"),
    Kural(r"\b(online|uzaktan|cevrimici|evden|internetten)\b", ekle="cevrim ici", sil=r"\b(online|uzaktan|cevrimici|evden|internetten)\b",
          etiket="online"),
    Kural(r"\b(final|vize|sinav|kayit|ekle\w*|add\w*)\w*\s+(hafta|gun)\w*", sil=r"\b(hafta|gun)\w*", etiket="zaman_dilimi"),
    # "Vize haftası ne zaman?", "Ders kayıtları ne zaman başlıyor?" -> tarihler akademik takvimdedir
    Kural(r"\b(vize|final|ara\s+sinav|sinavlar|kayitlar|ders\s+kayd\w*|ders\s+secim\w*|ekle\w*\s+cikar\w*|adddrop|butunleme|donem|tatil)\w*\b"
          r"(\s+\w+)?\s+ne\s+zaman\b(?!\s+kadar)", ekle="akademik takvim tarihleri", etiket="takvim"),
    Kural(r"\b(wifi|kablosuz|internet\w*|eduroam\w*)", ekle="eduroam kablosuz ag", etiket="wifi"),
    Kural(r"\b(mail\w*|eposta\w*|outlook|webmail)", ekle="kurumsal eposta", etiket="eposta"),
    Kural(r"\bsifre\w*|\bparola\w*", ekle="sifre sifirlama", etiket="sifre"),
    Kural(r"\bhoca\w*", ekle="ogretim elemani", sil=r"\bhoca\w*", etiket="hoca", zayif=True),
    Kural(r"\balttan\b", ekle="ders tekrari", etiket="alttan"),
    Kural(r"\b(not|notu|notum|notumu|notuma|notlarim)\b.*\b(yukselt\w*|artir\w*)|\b(yukselt\w*|artir\w*)\b.*\bnot", ekle="ders tekrari ortalamasini yukseltmek", etiket="not_yukselt"),
    Kural(r"\b(okuma|ogrenim|egitim)\s+sure\w*|\bkac\s+(yil|sene)\w*|\ben\s+fazla\s+\w*\s*(yil|sene)|\bbitirme\s+sure\w*|\b\d+\s+(yil|sene)\w*\b.*\bbitir\w*",
          ekle="ogretim suresi azami yil", etiket="sure"),
    Kural(r"\b(okul\w*|universite\w*)\b.*\bbitir\w*|\bbitir\w*\b.*\b(yil|sene)\w*", ekle="azami bitirme suresi", etiket="sure",
          haric=r"\bbitirme\s+(proje|tez|calisma|ders)"),
    Kural(r"\bsene\w*", ekle="yil", etiket="sene"),
    Kural(r"\buza(r|ma|yacak|tir|ti)\w*|\bsure\w*\s+uza", ekle="ogretim suresinden sayilir", etiket="sure_uzama"),
    Kural(r"\bbitirme\s+(proje|tez|ders|calisma)\w*", ekle="bitirme calismasi", etiket="bitirme"),
    Kural(r"\b(toefl|ielts|yds|yokdil|pte|cambridge)\b", ekle="ingilizce yeterlik esdeger sinav belgeleyen",
          sil=r"\b(toefl|ielts|yds|yokdil|pte|cambridge)\b", etiket="dil_sinavi"),
    Kural(r"\blab\w*", ekle="laboratuvar uygulamali", etiket="lab"),
    Kural(r"\bkac\s+(ders|kredi|akts)\w*|\b(ders|kredi|akts)\w*\s+(yuk|limit|sinir)\w*|\bfazla\s+(ders|kredi|akts)\w*"
          r"|\ben\s+(az|cok|fazla)\s+(\w+\s+)?(ders|kredi|akts)\w*|\b\d+\s+(akts|kredi)\b",
          ekle="kredi yuku akts azami", etiket="kredi_yuku", haric=r"\b(tekrar|yaz okul|baska universite|lisansustu|yuksek lisans|500|bitirme|staj|mezun)\w*"),
    Kural(r"\b(aa|ba|bb|cb|cc|dc|dd)\b.*\b(kac|puan|karsilig\w*|eder|nedir)\b|\b(kac|puan)\b.*\b(aa|ba|bb|cb|cc|dc|dd)\b",
          ekle="harf notlari karsiliklari dortluk sistem", etiket="harf_notu", haric=r"\b(gec\w*|tekrar\w*|basari\w*)"),
    Kural(r"ortalama\w*\s+(gir|katil|dahil|say|etki)\w*", ekle="ortalamaya dahil edilmez", sil=r"\b(gir|katil|dahil|etki)\w*",
          etiket="ortalamaya_dahil"),
    Kural(r"\b(aa|ba|bb|cb|cc)\b.*\btekrar\w*|\btekrar\w*\b.*\b(aa|ba|bb|cb|cc)\b|\bgect\w*\s+(ders\w*)\b.*\btekrar",
          ekle="basarili oldugu dersleri tekrar ortalamasini yukseltmek", etiket="basarili_ders_tekrar"),
    Kural(r"\bders\s+not(lar)?\w*\b.*\b(bul|indir|paylas|pdf|slayt|kaynak|fotokopi|sunum)\w*", sil=r"\bnot\w*|\bders\w*", etiket="ders_notu"),
    Kural(r"\b(son\s+gun|son\s+tarih|ne\s+zamana\s+kadar|en\s+gec)\b", ekle="en gec suresi bitimine kadar", sil=r"\bson\s+(gun|tarih)\w*", etiket="son_tarih"),
    Kural(r"\byurt\w*\b.*\b(cik\w*|ayril\w*|terk\w*)", ekle="yurttan ayrilma", etiket="yurt_ayrilma"),
    Kural(r"\bstaj\w*\b.*\b(bol\w*|parca\w*|ara\s+ver\w*|aralik\w*)|\b(bol\w*|parca\w*)\b.*\bstaj", ekle="ara verilmeden tam zamanli",
          sil=r"\b(bol|parca)\w*", etiket="staj_bolme"),
    Kural(r"\bstaj\w*\s+not\w*|\bstaj\w*\b.*\b(degerlendir\w*|basarili sayil\w*)", ekle="yeterli yetersiz degerlendirilmesi", etiket="staj_notu"),
    Kural(r"\b(kacta|kaca kadar)\b|\b(acilis|kapanis|calisma)\s+saat\w*|\bsaat\s+kac\w*|\bne\s+zaman\s+(acik|kapali)\b",
          sil=r"\b(kacta|kaca|acik|kapali|acilis|kapanis|saat\w*)\b", etiket="saat_sorusu"),
    Kural(r"\b(kagit|toner)\w*\b.*\b(sikis\w*|takil\w*|bitti)|\byazici\w*\b.*\b(sikis\w*|takil\w*)", ekle="bilgisayar ve yazici arizalari",
          etiket="yazici_ariza"),
    Kural(r"\b(para\w*)\b", ekle="ucret", etiket="para"),
    Kural(r"\b(yatir\w*|ode\w*)\b", ekle="odenir", etiket="odeme"),
    Kural(r"yuksek\s*lisans\s+ders\w*|lisansustu\s+ders\w*|master\s+ders\w*", ekle="lisansustu ders 500 kodlu", etiket="lisansustu"),
    Kural(r"\b(part\s*time|yari\s+zamanli|calisiyorum|calisiyor|is\s+buldum|isde\s+calis\w*)\b", ekle="calisan isde ucretle", etiket="calisma"),
    Kural(r"\bcalistigim\s+(sirket|yer|kurum|firma|isyer)\w*|\bkendi\s+isyer\w*|\bisyerim\w*", ekle="ucret mukabili calistigi kurum",
          etiket="calistigi_yer"),
    Kural(r"\b(kongre|sempozyum|konferans|calistay)\w*", ekle="gorevlendirme bilimsel toplanti", etiket="gorevlendirme"),
    Kural(r"\b(projektor|projeksiyon|akilli\s+tahta|ses\s+sistem|mikrofon|hoparlor|perde)\w*", ekle="derslik cihazlari projeksiyon ses sistemi",
          etiket="derslik"),
    Kural(r"\b(bozuk\w*|bozul\w*|calismiyor\w*|calismaz)\b", ekle="ariza", etiket="ariza"),
    Kural(r"\b(klima|isitma|kalorifer|havalandirma|petek)\w*", ekle="iklimlendirme klima", etiket="klima"),
    Kural(r"\b(priz|elektrik|lamba|aydinlatma|isik|isig|musluk|tesisat)\w*", ekle="elektrik aydinlatma tesisat", etiket="elektrik", rol="akademisyen"),
    Kural(r"\b(izin|izne|izni)\w*", ekle="yillik izin", etiket="izin_yillik", rol="akademisyen",
          haric=r"\b(dondur|ogrenci)\w*"),
    Kural(r"\b(bilgisayar|yazici|laptop|monitor)\w*\b.*\b(acilm\w*|bozul\w*|calism\w*|ariza\w*|bozuk)|\b(acilm|bozul|ariza)\w*\b.*\b(bilgisayar|yazici)\w*",
          ekle="bilgisayar ve yazici arizalari", etiket="bilgisayar_ariza"),
    Kural(r"\b1\s*\.?\s*sinif\w*|\bbirinci\s+sinif\w*", ekle="ilk iki yariyil birinci", etiket="sinif1"),
    Kural(r"\b4\s*\.?\s*sinif\w*|\bdorduncu\s+sinif\w*|\bson\s+sinif\w*", ekle="dorduncu sinif", etiket="sinif4"),
    Kural(r"\bkimlik\w*|ogrenci\s+kart\w*|\bkart(im|imi|imin)\b", ekle="kimlik karti", etiket="kimlik"),
    Kural(r"\bdiploma\w*\b.*\b(kayb\w*|kaybol\w*|kaybet\w*)|\b(kayb\w*|kaybet\w*)\b.*\bdiploma", ekle="diploma kaybi ikinci nusha", etiket="diploma_kayip"),
    Kural(r"\bdepozit\w*", ekle="depozito iade", etiket="depozito"),
    Kural(r"\bgeri\s+(al|ver|ode|yatir)\w*|\bparami\s+geri", ekle="iade edilir", sil=r"\bgeri\b", etiket="iade"),
    Kural(r"\btekrar\s+basvur\w*|\byeniden\s+basvur\w*", ekle="sonraki donem basvuru", sil=r"\b(tekrar|yeniden)\b", etiket="tekrar_basvuru"),
    Kural(r"\bbelge\w*\b.*\b(yaz\s+yurd|yurt)\w*|\byurt\w*\b.*\bbelge\w*", ekle="gerekli belgeler basvuru", etiket="yurt_belge"),
]
_KURAL_DESENLERI = [(re.compile(k.desen), re.compile(k.sil) if k.sil else None, k) for k in KURALLAR]


@dataclass
class Anlam:
    metin: str                        # arama için kullanılacak (sadeleştirilmiş + eklenmiş) metin
    ozgun: str = ""                   # sadece sorunun kendi kelimeleri (eklenenler hariç)
    etiketler: set = field(default_factory=set)
    eklenen: list = field(default_factory=list)
    zayif_eklenen: list = field(default_factory=list)  # konu sayılmayan eklemeler
    zorunlu_eklenen: list = field(default_factory=list)  # bir kelimenin YERİNE geçen eklemeler (madde bunları içermeli)
    kapsanan: set = field(default_factory=set)  # bir kuralın anlamlandırdığı kelimeler ("konferans" -> görevlendirme)
    silindi: bool = False             # eş sesli/anlamsız bir kelime aramadan çıkarıldı mı


def anla(soru: str, rol: str = "ogrenci") -> Anlam:
    """Soruyu aramaya hazırlar: eş sesli kelimelerin anlamını seçer, yönetmelik dilini ekler."""
    katli = birlestir(katla(soru))
    katli = re.sub(r"[^a-z0-9\s]", " ", katli)
    katli = re.sub(r"\s+", " ", katli).strip()
    orijinal = katli
    etiketler, eklenen, zayif_eklenen, zorunlu_eklenen, silindi = set(), [], [], [], False
    kapsanan = set()
    for desen, sil, kural in _KURAL_DESENLERI:
        if kural.rol and kural.rol != rol:
            continue
        if any(e in etiketler for e in kural.engel):
            continue
        if kural.haric and re.search(kural.haric, orijinal):
            continue
        if desen.search(orijinal):
            etiketler.add(kural.etiket)
            if kural.ekle and not kural.zayif:
                for m in desen.finditer(orijinal):
                    kelimeler_ = m.group(0).split()
                    # Uzun eşleşmenin ortasındaki kelimeler ("yurtta MİSAFİR kalabilir") kuralca açıklanmış sayılmaz
                    kapsanan.update(w for w in kelimeler_ if len(kelimeler_) <= 2 or desen.search(w))
            degisti = False
            if sil:
                yeni = sil.sub(" ", katli)
                degisti = yeni.split() != katli.split()
                silindi = silindi or degisti
                katli = yeni
            if kural.ekle:
                eklenen.append(kural.ekle)
                if kural.zayif:
                    zayif_eklenen.append(kural.ekle)
                elif degisti:
                    zorunlu_eklenen.append(kural.ekle)
    # Aynı kelime ailesinden iki ayrı anlam seçildiyse ilk (daha özel) kural geçerlidir
    # Anlamı hiçbir kurala uymayan "kal-" kelimesi (kalmak: başarısız olmak / konaklamak / geriye kalmak)
    # aranmaz; yoksa "kalan derslerim" sorusu "yurtta kalabilir" maddesine bağlanabilir.
    if not any(e.startswith("kal_") for e in etiketler):
        katli = re.sub(r"\bkal(abil|ir|mak|mam|di|dim|dik|sam|irsam|an|acak|ma|dig)\w*", " ", katli)
    if "yaz_yazmak" in etiketler and "yaz_donem" in etiketler:
        etiketler.discard("yaz_donem")
        eklenen = [e for e in eklenen if e != "yaz donemi ogretimi"]
    metin = re.sub(r"\s+", " ", " ".join([katli] + eklenen)).strip()
    return Anlam(metin=metin, ozgun=re.sub(r"\s+", " ", katli).strip(), etiketler=etiketler, eklenen=eklenen,
                 zayif_eklenen=zayif_eklenen, zorunlu_eklenen=zorunlu_eklenen, silindi=silindi, kapsanan=kapsanan)


# ---------------------------------------------------------------------------
# Sohbet niyetleri: selamlaşma, teşekkür, vedalaşma, "sen kimsin?"
# ---------------------------------------------------------------------------
_SELAM = r"(selam\w*|merhaba\w*|mrb|slm|meraba|hey|hi|hello|selamun aleykum|sa|as|gunaydin|iyi aksamlar|iyi geceler|tunaydin|hayirli \w+)"
_NASILSIN = r"(nasilsin\w*|naber|ne haber|nasil gidiyor|iyi misin|ne var ne yok)"
_TESEKKUR = r"(tesekkur\w*|tsk\w*|tsklr|sagol\w*|sag ol\w*|sag olun|eyvallah|eline saglik|cok iyi|harika|super|mukemmel|cok yardimci oldun|yardimin icin)"
_VEDA = r"(gorusuruz|gorusmek uzere|hosca kal\w*|hoscakal\w*|bay bay|bye|kendine iyi bak|iyi gunler|iyi calismalar)"
_KIMSIN = r"(sen kimsin|kimsin|adin ne|ismin ne|ne yapabilirsin|neler yapabilirsin|ne ise yar\w*|neye yar\w*|neler sorabilirim|ne sorabilirim|hangi konularda\w*|nasil kullan\w*|yardim eder misin|yardim|bana yardim et|neler biliyorsun|ne biliyorsun|pupa kim\w*|pupa ne\w*)"
_ONAY = r"(tamam\w*|anladim|anlasildi|ok|okey|peki|olur|tamamdir|hmm|evet|aynen|guzel|iyi)"
_HAKARET = r"(salak\w*|aptal\w*|gerizekali\w*|mal misin|beceriksiz\w*|ise yaramaz\w*|aptalsin|salaksin)"
_DOLGU = r"(cok|ederim|ediyorum|asistan|gishe|pupa|sana|size|sen|siz|de|da|ya|ok|cok cok|canim|dostum|kanka|hocam|abi|abla|ben de|sen de|siz de|acaba|peki|bu arada|bir de)"


def _yalnizca(desen: str, metin: str) -> bool:
    """Mesaj sadece bu desen (+ dolgu kelimeleri) mi?"""
    kalan = re.sub(rf"\b{desen}\b", " ", metin)
    kalan = re.sub(rf"\b{_DOLGU}\b", " ", kalan)
    return not kalan.strip()


def niyet_bul(soru: str) -> tuple[str | None, str]:
    """(niyet, selamı atılmış soru). Niyet: selam | nasilsin | tesekkur | veda | kimsin | onay | hakaret | None.
    "Merhaba, kaydımı nasıl dondururum?" -> ("selam_soru", "kaydımı nasıl dondururum?")"""
    m = re.sub(r"[^a-z0-9\s]", " ", katla(soru))
    m = re.sub(r"\s+", " ", m).strip()
    if not m:
        return None, soru
    for ad, desen in (("tesekkur", _TESEKKUR), ("veda", _VEDA), ("nasilsin", _NASILSIN), ("selam", _SELAM),
                      ("onay", _ONAY)):
        if _yalnizca(desen, m):
            return ad, soru
    if _yalnizca(rf"({_TESEKKUR}|{_ONAY}|{_VEDA}|{_SELAM}|{_NASILSIN})", m):  # "anladım teşekkürler", "selam nasılsın"
        if re.search(rf"\b{_VEDA}\b", m):
            return "veda", soru
        if re.search(rf"\b{_TESEKKUR}\b", m):
            return "tesekkur", soru
        return ("nasilsin" if re.search(rf"\b{_NASILSIN}\b", m) else "selam"), soru
    if re.fullmatch(rf"({_SELAM}\s*)*\s*{_NASILSIN}", m) or re.fullmatch(rf"{_SELAM}\s+{_NASILSIN}.*", m) and len(m.split()) <= 5:
        return "nasilsin", soru
    if _yalnizca(_KIMSIN, re.sub(rf"^({_SELAM}\s+)+", "", m)):
        return "kimsin", soru
    if len(m.split()) <= 4 and re.search(rf"\b{_HAKARET}\b", m):
        return "hakaret", soru
    # Başta selam, ardından gerçek soru
    bas = re.match(rf"^({_SELAM}\s+)+", m)
    if bas:
        # Orijinal sorudan selam kelimelerini at
        temiz = re.sub(r"^\W*(selam\w*|merhaba\w*|mrb|slm|günaydın|gunaydin|iyi akşamlar|iyi aksamlar|sa|hey)\b[\s,!.]*", "",
                       soru.strip(), flags=re.IGNORECASE)
        return "selam_soru", temiz or soru
    # Sonda teşekkür ("... teşekkürler") olan sorular normal sorudur
    return None, soru


def sohbet_cevabi(niyet: str, rol: str) -> dict:
    siz = rol == "akademisyen"
    ornekler = (["Projeksiyon arızasını nasıl bildiririm?", "Yıllık izin talebi ne zaman yapılır?",
                 "Kongre için görevlendirme ne zaman istenir?"] if siz else
                ["Kayıt dondurmak için ne gerekiyor?", "Devamsızlık sınırı nedir?", "Yazın yurtta kalabilir miyim?"])
    tanitim = ("Ben Pupa, Gebze Teknik Üniversitesi'nin maskotu ve asistanıyım. " +
               ("Arıza, bilgi işlem ve personel işlemleriyle ilgili sorularınızı üniversitenin kendi metinlerinden, kaynağıyla cevaplarım. "
                if siz else
                "Kayıt, sınav, not, staj, burs, yatay geçiş ve yurt gibi konulardaki sorularını yönetmeliklerden, kaynağıyla cevaplarım. ") +
               ("Emin olmadığım bir şeyi uydurmam; sorunuzu doğru birime iletmeyi öneririm."
                if siz else "Emin olmadığım bir şeyi uydurmam; sorunu doğru birime iletmeni öneririm."))
    metinler = {
        "selam": ("Merhaba! Size nasıl yardımcı olabilirim?" if siz else "Merhaba! Sana nasıl yardımcı olabilirim?"),
        "nasilsin": ("İyiyim, teşekkür ederim! Size nasıl yardımcı olabilirim?" if siz
                     else "İyiyim, teşekkürler! Sana nasıl yardımcı olabilirim?"),
        "tesekkur": ("Rica ederim! Başka bir sorunuz olursa buradayım." if siz
                     else "Rica ederim! Başka bir sorun olursa buradayım."),
        "veda": ("Görüşmek üzere, iyi çalışmalar!" if siz else "Görüşmek üzere, kolay gelsin!"),
        "kimsin": tanitim,
        "onay": ("Başka bir sorunuz olursa yazabilirsiniz." if siz else "Başka bir sorun olursa yazabilirsin."),
        "hakaret": ("Bazen istediğiniz cevabı veremeyebiliyorum. Sorunuzu farklı kelimelerle yazarsanız ya da "
                    "personele iletirseniz yardımcı olmaya çalışırım." if siz else
                    "Bazen istediğin cevabı veremeyebiliyorum. Sorunu farklı kelimelerle yazarsan ya da "
                    "personele iletirsen yardımcı olmaya çalışırım."),
    }
    oneriler = ornekler if niyet in ("selam", "nasilsin", "kimsin", "hakaret") else []
    return {"cevap": metinler[niyet], "oneriler": oneriler}


# Yönetmeliklerde cevabı olamayacak görüş / öneri soruları ("hangi hoca daha iyi")
_GORUS = r"\b(hangi hoca\w*|en iyi hoca\w*|en kolay|en zor|tavsiye\w*|onerir misin|sence|sizce|yorumun|fikrin)\b"


# Bölüm, ders ve yazılım adları sorunun konusu değil ayrıntısıdır ("bilgisayar mühendisliğine geçmek",
# "matematikten kaldım", "MATLAB lisansı"): hazır cevap eşleşmesinde az ağırlık alırlar.
ALAN_ADLARI = {kok(katla(w)) for w in """
matematik fizik kimya biyoloji mimarlık mühendislik mühendisliği bilgisayar elektronik makine malzeme endüstri çevre inşaat harita
moleküler işletme ekonomi iktisat programlama calculus lineer istatistik diferansiyel analiz algoritma türkçe tarih
edebiyat felsefe hukuk tıp şehir planlama tasarım matlab autocad solidworks spss office windows ansys python labview
mathematica excel word
""".split()}


def gorus_sorusu_mu(soru: str) -> bool:
    return bool(re.search(_GORUS, katla(soru)))
