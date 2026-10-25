"""
Gishe asistanı: öğrenci ve akademisyen sorularını üniversitenin kendi metinlerine dayanarak cevaplar.

Bir soru gelince sırasıyla (her adım bir öncekinin cevap veremediği durumda devreye girer):
  1. Sohbet mi?  "Merhaba", "teşekkürler", "sen kimsin?" gibi mesajlara kısa sohbet cevabı (dil.py).
  2. Soruyu anla: Türkçe karaktersiz yazım, kısaltmalar ("büt", "GANO") ve EŞ SESLİ kelimeler
     ("yazın yurtta kalmak" ile "dilekçe yazmak", "dersten kalmak" ile "yurtta kalmak") çözülür (dil.py).
  3. Sık sorulan soru mu?  Soru, yönetmelik maddelerinden yazılmış hazır cevaplardan birine (sss.txt)
     yeterince benziyorsa cevap anında ve kaynağıyla verilir.
  4. RAG ("bul, sonra cevapla"): "yonetmelikler" klasöründeki maddeler arasında en ilgilileri bulunur,
     yapay zekâ modeline (Ollama üzerinden Qwen) verilir ve modelden SADECE bu maddelere dayanarak
     cevap vermesi istenir. Model cevabı denetlenir: metinde olmayan bir sayı yazdıysa, metne dayanmıyorsa,
     kaçamak cevap verdiyse veya Türkçe dışında bir dile kaydıysa cevap gösterilmez; yerine maddenin soruyla
     ilgili cümleleri aynen alıntılanır.
  5. İlgili madde yoksa asistan uydurmaz: "emin değilim" der, benzer soruları önerir ve soruyu doğru birime
     talep olarak iletmeyi teklif eder.

Model tamamen yerelde çalışır: Ollama servisi aynı docker compose içindedir ve model ağırlıkları Docker imajı
derlenirken indirilir. Hiçbir bulut yapay zekâ API'si çağrılmaz. Model hazır değilse (servis açılıyor, bilgisayar
yavaş vb.) asistan "yedek moda" geçer: sık sorulan sorular ve madde alıntılarıyla çalışmaya devam eder.
"""
import logging
import math
import re
import time
from pathlib import Path

import httpx

import ayarlar
import dil
from dil import benzerlik, katla, kokler, kucult  # noqa: F401  (kucult eski kodla uyum için dışarı açık)

log = logging.getLogger("gishe.asistan")

OLLAMA_URL = ayarlar.OLLAMA_URL
MODEL = ayarlar.MODEL
KLASOR = Path(__file__).parent / "yonetmelikler"
SSS_DOSYASI = Path(__file__).parent / "sss.txt"

DURUM = {"hazir": False, "model": MODEL, "mesaj": "Yapay zekâ modeli kontrol ediliyor…"}

# Talebi hangi birime yönlendireceğimizi belirleyen anahtar kelimeler (sıra önemli, sadeleştirilmiş yazım).
# Öğrenci ve akademisyen için ayrı kurallar var, çünkü baktıkları birimler farklı.
BILGI_ISLEM_KELIMELERI = ["eposta", "mail", "sifre", "parola", "internet", "wifi", "eduroam", "kablosuz", "ag baglant",
                          "lisans yenile", "yazilim", "obs", "moodle", "sistem", "giris yapamiyorum"]
YONLENDIRME = {
    "ogrenci": [
        (["yurt", "barinma", "pansiyon", "yatak"], "Barınma Birimi"),
        (["harc", "iade", "odeme", "dekont", "borc", "katkipayi"], "Strateji Geliştirme"),
        (["intibak", "muafiyet", "staj", "yonetim kurulu", "ders icerik"], "Fakülte Sekreterliği"),
        (BILGI_ISLEM_KELIMELERI, "Bilgi İşlem"),
    ],
    "akademisyen": [
        (["ariza", "projeksiyon", "projektor", "klima", "isitma", "kalorifer", "priz", "elektrik",
          "lamba", "tesisat", "musluk", "kapi", "kilit", "asansor", "tamir", "akilli tahta", "havalandirma"], "Yapı İşleri"),
        (BILGI_ISLEM_KELIMELERI + ["bilgisayar", "yazici", "lisans"], "Bilgi İşlem"),
        (["izin", "gorevlendirme", "maas", "kadro", "sozlesme", "rapor", "sgk", "hizmet belgesi", "kongre"],
         "Personel Daire Başkanlığı"),
    ],
}
VARSAYILAN_BIRIM = {"ogrenci": "Öğrenci İşleri", "akademisyen": "Fakülte Sekreterliği"}


def yonlendir(metin: str, rol: str = "ogrenci") -> str:
    """Konuya ve talep edenin rolüne göre talebin gideceği birimi tahmin eder.
    1) Açık anahtar kelime kuralları (ör. "harç" -> Strateji Geliştirme),
    2) yoksa yönetmeliklerde GÜÇLÜ bir eşleşme varsa o maddenin birimi (asistanın kaynak gösterdiği
       madde ile talebin gittiği birim aynı olsun diye),
    3) o da yoksa rolün varsayılan birimi."""
    m = dil.birlestir(katla(metin)) + " "
    for kelimeler, birim in YONLENDIRME.get(rol, []):
        if any(k in m for k in kelimeler):
            return birim
    sonuc = ara_puanli(metin, rol, adet=1)
    if sonuc and sonuc[0]["guclu"]:
        return sonuc[0]["parca"]["birim"]
    return VARSAYILAN_BIRIM.get(rol, "Öğrenci İşleri")


# ---------------------------------------------------------------------------
# Yönetmelikleri yükleme
# ---------------------------------------------------------------------------
def yonetmelikleri_yukle() -> list[dict]:
    """Her .txt dosyasının başında BAŞLIK:, BİRİM: ve KİTLE: satırları bulunur,
    ardından boş satırla ayrılmış maddeler gelir.
    KİTLE: ogrenci | akademisyen | ortak  (bu metni kimin asistanı kullanabilir)"""
    parcalar = []
    for dosya in sorted(KLASOR.glob("*.txt")):
        bloklar = re.split(r"\n\s*\n", dosya.read_text(encoding="utf-8").strip())
        baslik, birim, kitle = dosya.stem, "Öğrenci İşleri", "ogrenci"
        for satir in bloklar[0].splitlines():
            if ":" in satir:
                anahtar, deger = satir.split(":", 1)
                anahtar = kucult(anahtar.strip())
                if anahtar == "başlık":
                    baslik = deger.strip()
                elif anahtar == "birim":
                    birim = deger.strip()
                elif anahtar == "kitle":
                    kitle = kucult(deger.strip())
        for blok in bloklar[1:]:
            blok = blok.strip()
            ilk_satir = blok.splitlines()[0]
            # "Madde 19 – Yarıyıl izni (kayıt dondurma) (bölüm 1/2)" -> "Madde 19 – Yarıyıl izni (kayıt dondurma)"
            madde = re.sub(r"\s*\(bölüm \d+/\d+\)\s*$", "", ilk_satir).strip()
            parcalar.append({
                "metin": blok,
                "govde": "\n".join(blok.splitlines()[1:]).strip() or blok,
                "dosya_basligi": baslik,
                "kaynak": f"{baslik}, {madde}",
                "birim": birim,
                "kitle": kitle,
            })
    return parcalar


PARCALAR = yonetmelikleri_yukle()

# Kelime ağırlıkları: bir kelime ailesi (ilk 4 harf) ne kadar az maddede geçiyorsa o kadar belirleyicidir.
# "burs", "yatay", "akts" ağır; "ders", "zaman" gibi her yerde geçenler hafif sayılır.
_AILE: dict[str, int] = {}
for _p in PARCALAR:
    _sayim: dict[str, int] = {}
    for _k in kokler(_p["metin"]):
        _sayim[_k] = _sayim.get(_k, 0) + 1
    # Metnin (dosyanın) başlığı her maddenin konusudur: "Yan Dal Programı Yönergesi"nin her maddesi yan dalla ilgilidir,
    # İşletme Fakültesi staj yönergesinin her maddesi İşletme stajıyla ilgilidir.
    # (Kelime ağırlıkları yalnızca maddenin kendi metninden hesaplanır; başlık kelimeleri ağırlığı değiştirmez.)
    for _a in {x[:4] for x in _sayim}:
        _AILE[_a] = _AILE.get(_a, 0) + 1
    _dosya = set(kokler(_p["dosya_basligi"])) - {"gtu", "ornek", "lisans", "onlisa", "progra"}
    for _k in _dosya:
        _sayim.setdefault(_k, 1)
    _p["sayim"] = _sayim
    _p["kokler"] = frozenset(_sayim)
    _p["baslik_kokleri"] = set(kokler(_p["metin"].splitlines()[0])) | _dosya
_N = max(1, len(PARCALAR))
BILINMEYEN_AGIRLIK = 2.5  # metinlerde hiç geçmeyen kelime ("futbol"): konu dışı soruları ayırt etmeye yardım eder


# Öğrencinin günlük dili ile yönetmelik dili arasındaki köprü (eş anlamlılar).
# Soruda soldaki kelime geçerse, maddede sağdakilerden biri de (biraz daha zayıf) eşleşme sayılır.
_ES_ANLAMLI_HAM = {
    "akts": ["kredi"], "kredi": ["akts"],
    "devamsızlık": ["devam"], "yoklama": ["devam"],
    "bırakmak": ["çıkarma"], "çekilmek": ["çıkarma"],
    "erasmus": ["değişim"], "değişim": ["erasmus"],
    "agno": ["ortalama"], "gano": ["ortalama"], "gno": ["ortalama"],
    "harf": ["notlar"], "mezun": ["mezuniyet", "diploma"], "diploma": ["mezuniyet"],
    "hazırlık": ["İngilizce"], "çap": ["ciftanadal"],
    "dönem": ["yarıyıl"], "yarıyıl": ["dönem"],
    "harç": ["katkipayi"], "katkipayi": ["harç"],
    "online": ["çevrim"], "hastalık": ["mazeret"], "hasta": ["mazeret"],
    "bölüm": ["program"], "sınav": ["sınavı"], "belge": ["belgesi"],
    "şirket": ["kurum", "işletme"], "firma": ["kurum", "işletme"], "iş": ["kurum"],
    "kaybetmek": ["kaybı"], "bozuk": ["arıza"], "bozuldu": ["arıza"], "çalışmıyor": ["arıza"],
    "yanmıyor": ["arıza"], "giremiyorum": ["şifre"], "açılmıyor": ["arıza"], "para": ["ücret"],
    "yatırmak": ["ödenir"], "sene": ["yıl"], "çıkmak": ["ayrılma"], 
    "çalıştığım": ["çalıştığı"], "katılmak": ["katılmak"],
}
ES_ANLAMLI = {dil.kok(katla(k)): [dil.kok(katla(x)) for x in v] for k, v in _ES_ANLAMLI_HAM.items()}


def es_anlamlilar(kok: str) -> list[str]:
    return [x for anahtar, liste in ES_ANLAMLI.items() if benzerlik(kok, anahtar) >= 1.0 for x in liste]


def agirlik(kok: str) -> float:
    adet = _AILE.get(kok[:4], 0)
    if not adet:
        return BILINMEYEN_AGIRLIK
    return max(0.3, math.log((_N + 1) / (adet + 0.5)))


def _eslesme(s: str, hedefler, esler: list[str]) -> float:
    """s kökünün hedef kökler içindeki en iyi eşleşmesi (eş anlamlılar 0.8 sayılır)."""
    en = 0.0
    for t in hedefler:
        b = benzerlik(s, t)
        if b < 1.0 and esler:
            b = max(b, 0.8 * max(benzerlik(x, t) for x in esler))
        if b > en:
            en = b
            if en >= 1.0:
                break
    return en


# Bir maddenin soruyu "güçlü" karşılaması için: sorudaki, yönetmeliklerde geçen (bilinen) kelimelerin
# ağırlıkça en az bu oranı AYNI maddede bulunmalı ve belirleyici (ağır) bir bilinen kelime eksik olmamalı.
# Örnek: "Bursum kesilirse yurt ücreti değişir mi?" -> en iyi madde bursu anlatıyor ama "yurt" ve "ücret"
# o maddede yok. Soru iki konuyu birleştiriyor; asistan "emin değilim" der ve personele iletmeyi önerir.
# Yönetmeliklerde hiç geçmeyen kelimelerden ("kantin", "vegan") birden fazlası varsa soru büyük
# ihtimalle metinlerin konusu dışındadır; tek bir eşleşen kelime ("yemek") yüzünden "emin" denmez.
GUCLU_ESIK = 0.60
BELIRLEYICI_AGIRLIK = 2.0
# Metinlerde çok geçtiği için ağırlığı düşük çıkan ama sorunun KONUSUNU belirleyen kelimeler.
# Soruda geçiyorsa maddede de geçmeli; hazır sorudaysa kullanıcının sorusunda da geçmeli.
KONU_KELIMELERI = {dil.kok(katla(w)) for w in """staj burs yurt yatay yandal erasmus hazırlık mezun dondurma devam
eduroam eposta şifre katkipayi harç dsinav tekders bitirme lisansüstü diploma itiraz mazeret ortalama izin
görevlendirme projeksiyon klima yazıcı""".split()}
EN_FAZLA_BILINMEYEN = 1


def _bilinmeyen_isimler(anlam: dil.Anlam) -> set[str]:
    """Metinlerde hiç geçmeyen, fiil olmayan ve hiçbir anlam kuralının açıklamadığı kelimeler ("misafir", "tören")."""
    return {dil.kok(w) for w in dil.kelimeler(anlam.ozgun)
            if w not in dil.DURAKLAR and w not in anlam.kapsanan and dil.kok(w) not in dil._DURAK_KOKLERI
            and not _AILE.get(dil.kok(w)[:4]) and not dil.fiil_gibi(w)
            and not any(b.endswith(dil.kok(w)) for b in _BIRLESIK)}


# Birleştirilmiş kelimelerin parçaları ("ikinci dal" -> "dal", yandal/anadal içinde geçer)
_BIRLESIK = ("yandal", "anadal", "ciftanadal")


def ara_puanli(soru: str, rol: str = "ogrenci", adet: int = 3, anlam: dil.Anlam | None = None) -> list[dict]:
    """Soruyla en ilgili maddeleri puanlarıyla döndürür (sadece bu rolün görebileceği metinlerden).
    Her sonuç: {"parca", "sira", "kapsam", "guclu", "eksik"}.
    - kapsam: sorudaki kelimelerin ağırlıkça ne kadarı maddede karşılandı (0-1).
    - guclu: madde soruyu tek başına karşılıyor mu (bkz. GUCLU_ESIK, EN_FAZLA_BILINMEYEN).
    - eksik: maddede karşılanmayan, yönetmeliklerde geçen belirleyici kelimeler.
    Kapsam %40'ın altındaysa madde hiç listelenmez; asistan uydurmasın diye. Sıralamada kelimenin
    maddede kaç kez geçtiği ve madde başlığında olup olmadığı da hesaba katılır."""
    anlam = anlam or dil.anla(soru, rol)
    agirliklar = agirlikli_kokler(anlam)
    soru_kokleri = list(agirliklar)
    if not soru_kokleri:
        return []
    bilinen = {s for s in soru_kokleri if _AILE.get(s[:4])}
    bilinmeyen_sayisi = len(soru_kokleri) - len(bilinen)
    esler = {s: es_anlamlilar(s) for s in soru_kokleri}
    toplam = sum(agirliklar.values())
    bilinen_toplam = sum(agirliklar[s] for s in bilinen)
    # Metinlerde hiç geçmeyen isimler ("misafir", "tören") genelde sorunun asıl konusudur
    bilinmeyen_isimler = _bilinmeyen_isimler(anlam)
    # Bir kelimenin yerine geçen yönetmelik ifadeleri ("büt" -> "D sınavı"): maddede en az yarısı bulunmalı
    zorunlu = [{s: agirlik(s) for s in kokler(e)} for e in anlam.zorunlu_eklenen]
    ozgun_kokler = set(kokler(anlam.ozgun))
    puanli = []
    for p in PARCALAR:
        if p["kitle"] not in ("ortak", rol):
            continue
        kapsam = sira = bilinen_kapsam = 0.0
        eksik, baslikta_sayisi = [], 0
        for s, a in agirliklar.items():
            guc, tekrar = 0.0, 0
            adaylar = [(s, 1.0)] + [(x, 0.8) for x in esler[s]]
            for kk, n in p["sayim"].items():
                b = max(benzerlik(aday, kk) * carpan for aday, carpan in adaylar)
                if b > guc:
                    guc, tekrar = b, n
                elif b == guc and b:
                    tekrar += n
            if guc:
                baslikta = any(benzerlik(aday, x) >= 1.0 for aday, _ in adaylar for x in p["baslik_kokleri"])
                baslikta_sayisi += baslikta
                kapsam += a * guc
                sira += a * guc * (1.5 if baslikta else 1.0) * (1 + 0.35 * math.log(1 + tekrar))
                if s in bilinen:
                    bilinen_kapsam += a * guc
            # Kısmi kök eşleşmesi (ör. "unuttum" ~ "unutan", 0.4) eksik sayılmaz ama kapsama az katkı verir
            if guc < 0.4 and s in bilinen and (a >= BELIRLEYICI_AGIRLIK or (s in KONU_KELIMELERI and s in ozgun_kokler)):
                eksik.append(s)
        if kapsam >= 0.40 * toplam:
            oran = bilinen_kapsam / bilinen_toplam if bilinen_toplam else 0.0
            # Kısa sorularda (en fazla 2 bilinen kelime) hepsi karşılanmalı:
            # "Yurt başvurusu" sorusu "Yurt içi görevlendirme" maddesine sadece "yurt" ile bağlanmasın.
            esik = 0.78 if len(bilinen) <= 2 else GUCLU_ESIK
            guclu = oran >= esik and not eksik and bilinmeyen_sayisi <= EN_FAZLA_BILINMEYEN
            # Tek anlamlı kelimeli sorular ("öğrenci belgesi nereden alınır?" -> sadece "belge") hiçbir maddeye
            # güçlü bağlanmaz: tek kelime, sorunun ne istediğini söylemeye yetmez.
            if guclu and len(bilinen) <= 1:
                guclu = False
            if guclu and any(_kapsama(k, p["sayim"]) < 0.5 for k in zorunlu if k):
                guclu = False
            # Çok güçlü: kelimelerin büyük kısmı aynı maddede ve soruda metinlerin dışında kalan bir isim yok.
            # Model yokken madde yalnızca bu durumda alıntılanır.
            eslesen_agirlik = sum(agirlik(s) for s in bilinen if _eslesme(s, p["sayim"], esler[s]) >= 0.8)
            konu_eslesti = any(s in KONU_KELIMELERI and _eslesme(s, p["sayim"], esler[s]) >= 0.8 for s in ozgun_kokler)
            cok_guclu = (guclu and oran >= 0.85 and not bilinmeyen_isimler and baslikta_sayisi >= 1
                         and (eslesen_agirlik >= 3.5 or konu_eslesti))
            puanli.append({"parca": p, "sira": sira, "kapsam": round(kapsam / toplam, 3),
                           "guclu": guclu, "cok_guclu": cok_guclu, "eksik": eksik})
    # Soruyu güçlü karşılayan maddeler her zaman önce gelir, sonra puana göre
    puanli.sort(key=lambda x: (x["cok_guclu"], x["guclu"], x["sira"]), reverse=True)
    return puanli[:adet]


def ara(soru: str, rol: str = "ogrenci", adet: int = 3) -> list[dict]:
    """Geriye uyumluluk için: sadece maddeleri döndürür."""
    return [x["parca"] for x in ara_puanli(soru, rol, adet)]


def kaynaklari_topla(parcalar: list[dict]) -> list[str]:
    """Aynı maddenin bölümleri tek kaynak olarak gösterilir."""
    return list(dict.fromkeys(p["kaynak"] for p in parcalar))


# ---------------------------------------------------------------------------
# Sık sorulan sorular (sss.txt)
# ---------------------------------------------------------------------------
EKLENEN_CARPANI = 0.5  # soruda olmayan, anlam çözmenin eklediği kelimeler daha az belirleyicidir


def agirlikli_kokler(anlam: dil.Anlam, sadece_ozgun: bool = False, alan_adi_hafif: bool = False) -> dict[str, float]:
    """Sorunun kökleri ve ağırlıkları. Sorunun kendi kelimeleri tam, anlam çözmenin eklediği
    yönetmelik kelimeleri yarım ağırlık alır (eklenen uzun ifadeler eşleşmeye baskın çıkmasın)."""
    ozgun = set(kokler(anlam.ozgun))
    # Metinlerde hiç geçmeyen ama çekimli fiile benzeyen kelimeler ("gidince", "uzar") sorunun konusu değildir
    fiiller = {dil.kok(w) for w in dil.kelimeler(anlam.ozgun)
               if (dil.fiil_gibi(w) or w in anlam.kapsanan) and not _AILE.get(dil.kok(w)[:4])}
    sonuc = {}
    for s in dict.fromkeys(kokler(anlam.ozgun if sadece_ozgun else anlam.metin)):
        a = agirlik(s) * (1.0 if s in ozgun else EKLENEN_CARPANI)
        if s in fiiller:
            a = min(a, 1.0)
        if alan_adi_hafif and s in dil.ALAN_ADLARI:
            a = min(a, 0.3)
        sonuc[s] = a
    return sonuc


def _kok_kumesi(metin: str, rol: str) -> dict[str, float]:
    """Hazır sorunun kökleri. Yönetmeliklerde hiç geçmeyen kelimeleri ("gidersem", "buluyor") sorunun
    söyleniş biçimidir, konusu değil: az ağırlık alırlar. (Kullanıcının sorusunda ise bu tür kelimeler
    ağırdır, çünkü sorunun metinlerin konusu dışında olduğunu gösterebilirler: "mezuniyet töreni".)"""
    return {s: (a if _AILE.get(s[:4]) else min(a, 0.5))
            for s, a in agirlikli_kokler(dil.anla(metin, rol), alan_adi_hafif=True).items()}


def sss_yukle() -> list[dict]:
    """sss.txt dosyasını okur. Kaynağı yönetmeliklerde bulunamayan cevap yüklenmez (uydurma olmasın)."""
    if not SSS_DOSYASI.exists():
        return []
    kaynaklar = {p["kaynak"]: p for p in PARCALAR}
    girdiler = []
    metin = "\n".join(s for s in SSS_DOSYASI.read_text(encoding="utf-8").splitlines() if not s.lstrip().startswith("#"))
    for no, blok in enumerate(re.split(r"\n\s*\n", metin.strip()), 1):
        g = {"sorular": [], "cevap": [], "kaynaklar": [], "tur": "sss", "birim": None, "kitle": None}
        for satir in blok.splitlines():
            if ":" not in satir:
                continue
            anahtar, deger = satir.split(":", 1)
            anahtar, deger = anahtar.strip().upper(), deger.strip()
            if anahtar == "S":
                g["sorular"].append(deger)
            elif anahtar == "C":
                g["cevap"].append(deger)
            elif anahtar == "K":
                eslesen = [k for k in kaynaklar if deger in k]
                if len(eslesen) != 1:
                    log.warning("sss.txt %d. blok: '%s' kaynağı %d maddeyle eşleşti; blok atlandı.", no, deger, len(eslesen))
                    g["hata"] = True
                else:
                    g["kaynaklar"].append(eslesen[0])
            elif anahtar == "T":
                g["tur"] = deger.lower()
            elif anahtar == "B":
                g["birim"] = deger
            elif anahtar == "R":
                g["kitle"] = deger.lower()
        if g.get("hata") or not g["sorular"] or not g["cevap"]:
            continue
        if g["tur"] != "yonlendir" and not g["kaynaklar"]:
            log.warning("sss.txt %d. blok kaynaksız; atlandı.", no)
            continue
        ilk = kaynaklar[g["kaynaklar"][0]] if g["kaynaklar"] else None
        g["birim"] = g["birim"] or (ilk["birim"] if ilk else "Öğrenci İşleri")
        g["kitle"] = g["kitle"] or (ilk["kitle"] if ilk else "ogrenci")
        g["cevap"] = " ".join(g["cevap"])
        roller = ["ogrenci", "akademisyen"] if g["kitle"] == "ortak" else [g["kitle"]]
        g["varyantlar"] = {r: [_kok_kumesi(s, r) for s in g["sorular"]] for r in roller}
        girdiler.append(g)
    return girdiler


def _kapsama(kaynak: dict[str, float], hedef: dict[str, float]) -> float:
    """kaynak köklerinin (ağırlıkça) ne kadarı hedefte var: 0-1."""
    toplam = sum(kaynak.values())
    if not toplam:
        return 0.0
    return sum(a * _eslesme(s, hedef, es_anlamlilar(s)) for s, a in kaynak.items()) / toplam


def _agir_eksik(kaynak: dict[str, float], hedef: dict[str, float], esik: float = BELIRLEYICI_AGIRLIK) -> bool:
    return any(a >= esik and _eslesme(s, hedef, es_anlamlilar(s)) < 0.4 for s, a in kaynak.items())


KONU_AGIRLIGI = 2.0
_FAKULTELER = {"isletme": "İşletme", "muhendislik": "Mühendislik", "mimarlik": "Mimarlık", "fen": "Fen", "temel bilimler": "Temel Bilimler"}


def _fakulte(anlam: dil.Anlam) -> str | None:
    for anahtar, ad in _FAKULTELER.items():
        if re.search(rf"\b{anahtar}\w*", anlam.ozgun):
            return ad
    return None


def _konu_kokleri(anlam: dil.Anlam) -> set[str]:
    """Sorunun konusunu taşıyan kökler: yönetmeliklerde geçen ağır (belirleyici) kelimeler ve anlam çözmenin
    eklediği yönetmelik kelimeleri. Bölüm/ders adları ve "hoca" gibi zayıf eklemeler konu sayılmaz."""
    zayif = set(kokler(" ".join(anlam.zayif_eklenen))) - set(kokler(anlam.ozgun))
    anlamli = set(kokler(" ".join(e for e in anlam.eklenen if e not in anlam.zayif_eklenen)))
    konu = {k for k in kokler(anlam.ozgun)
            if (agirlik(k) >= KONU_AGIRLIGI and _AILE.get(k[:4])) or k in KONU_KELIMELERI} | anlamli
    return konu - zayif - dil.ALAN_ADLARI


def sss_puanla(soru, rol: str) -> list[tuple[float, float, dict]]:
    """Her SSS girdisi için (benzerlik F1, sorunun kapsanma oranı, girdi); en benzerden başlayarak.
    Soru hem eklenen yönetmelik kelimeleriyle hem de sadece kendi kelimeleriyle karşılaştırılır ve
    iyi olanı alınır: anlam çözmenin eklediği kelimeler eşleşmeye yardım eder ama asla zarar vermez."""
    if isinstance(soru, dil.Anlam):
        temsiller = [agirlikli_kokler(soru, alan_adi_hafif=True)]
        if not soru.silindi:  # kelime silinmediyse sorunun kendi kelimeleri de ayrıca denenir
            temsiller.append(agirlikli_kokler(soru, sadece_ozgun=True, alan_adi_hafif=True))
        temsiller = [t for t in temsiller if t]
        konu = _konu_kokleri(soru)
    else:
        temsiller = [soru]
        konu = {k for k in soru if agirlik(k) >= KONU_AGIRLIGI}
    sonuc = []
    fakulte = _fakulte(soru) if isinstance(soru, dil.Anlam) else None
    for g in SSS:
        if rol not in g["varyantlar"]:
            continue
        if fakulte and any("Fakültesi" in k and fakulte not in k for k in g["kaynaklar"]):
            continue  # "İşletme Fakültesinde staj" sorusuna Mühendislik Fakültesi'nin hazır cevabı verilmez
        en_f, en_r = 0.0, 0.0
        for soru_kokleri in temsiller:
            for v in g["varyantlar"][rol]:
                r = _kapsama(soru_kokleri, v)   # sorunun ne kadarı bu soruda var
                p = _kapsama(v, soru_kokleri)   # bu sorunun ne kadarı soruda var
                f = 2 * p * r / (p + r) if p + r else 0.0
                # Sorunun konusunu taşıyan (ağır) kelimelerden en az biri hazır soruda olmalı:
                # "Ders notlarını nereden bulurum?" sadece "bulmak" fiiliyle "Staj yerini kim buluyor?" sayılmasın.
                if not any(_eslesme(k, v, es_anlamlilar(k)) >= 0.8 for k in konu):
                    f = 0.0
                # Hazır sorudaki belirleyici (ağır) bir kelime soruda hiç yoksa benzerlik düşürülür:
                # "Yemekhane menüsü ne?" ile "Yemek bursu nedir?" aynı soru değildir ("burs" eksik).
                if _agir_eksik(v, soru_kokleri, esik=1.6):
                    f *= 0.75
                # Hazır sorunun konusu ("staj", "burs", "yurt"...) kullanıcının sorusunda yoksa aynı soru değildir
                if any(k in KONU_KELIMELERI and _eslesme(k, soru_kokleri, es_anlamlilar(k)) < 0.8 for k in v):
                    f *= 0.6
                if f > en_f:
                    en_f, en_r = f, r
        sonuc.append((en_f, en_r, g))
    sonuc.sort(key=lambda x: x[0], reverse=True)
    return sonuc


SSS = sss_yukle()
SSS_ESIK = 0.62           # bu benzerliğin üstünde hazır cevap verilir
SSS_KAPSAMA_ESIK = 0.60   # ve sorunun en az bu kadarı hazır sorunun içinde olmalı
SSS_DESTEKLI_ESIK = 0.35       # arama aynı maddeyi ÇOK GÜÇLÜ bulduysa bu benzerlik yeterli
SSS_ZAYIF_DESTEK_ESIK = 0.40   # arama aynı maddeyi ilk sırada güçlü bulduysa ve sorunun en az yarısı hazır soruda varsa
ONERI_ESIK = 0.30         # "Bunu mu demek istedin?" önerileri için


# ---------------------------------------------------------------------------
# Yapay zekâ modeli
# ---------------------------------------------------------------------------
SISTEM_MESAJI = {
    "ogrenci": """Sen Pupa'sın: Gebze Teknik Üniversitesi'nin maskotu ve öğrencilere yardım eden asistanı.
Öğrencinin sorusunu YALNIZCA sana verilen numaralı yönetmelik metinlerine dayanarak cevaplarsın.

Kurallar:
1. Cevabı metinden çıkar. Metinde olmayan bilgi, sayı, tarih veya kural ekleme; tahmin yürütme.
2. Öğrenciye "sen" diye hitap et. Kısa, açık ve samimi bir Türkçe kullan; en fazla 4 cümle yaz.
3. Sayıları, yüzdeleri, süreleri ve notları metinde yazdığı gibi aynen kullan.
4. Metin soruyu cevaplıyorsa doğrudan cevap ver; "daha fazla bilgi gerekir" gibi kaçamak cümleler kurma.
5. Koşulları metindeki gibi koru: "en az", "en fazla", "-den önce", "-den sonra", "edilir", "edilmez" ifadelerini tersine çevirme.
6. Metin sorunun yalnızca bir kısmını cevaplıyorsa o kısmı söyle, kalanı için ilgili birime başvurmasını öner.
7. Metinler soruyla ilgisizse yalnızca BILMIYORUM yaz.
8. Örneklerdeki bilgileri kullanma; sadece bu sorunun METİNLER kısmını kullan.
9. Cevabın sonuna dayandığın metnin numarasını köşeli parantezle yaz, örneğin [1]. Metinlerden ya da madde numaralarından söz etme.
10. Sadece Türkçe yaz.""",
    "akademisyen": """Sen Pupa'sın: Gebze Teknik Üniversitesi'nin maskotu ve akademik personele yardım eden asistanı.
Kullanıcının sorusunu YALNIZCA sana verilen numaralı yönerge ve rehber metinlerine dayanarak cevaplarsın.

Kurallar:
1. Cevabı metinden çıkar. Metinde olmayan bilgi, sayı, tarih veya kural ekleme; tahmin yürütme.
2. Kullanıcıya "siz" diye hitap et. Kısa, açık ve nazik bir Türkçe kullan; en fazla 4 cümle yaz.
3. Sayıları ve süreleri metinde yazdığı gibi aynen kullan.
4. Metin soruyu cevaplıyorsa doğrudan cevap ver; kaçamak cümleler kurma.
5. Metinler soruyla ilgisizse yalnızca BILMIYORUM yaz.
6. Cevabın sonuna dayandığın metnin numarasını köşeli parantezle yaz, örneğin [1].
7. Sadece Türkçe yaz.""",
}

# Küçük modeller örnekten çok daha iyi öğrenir: her istekte önce iki örnek soru-cevap gösterilir
# (biri metinden cevaplanabilen, biri cevaplanamayan). Bu kısım her istekte aynı olduğu için Ollama onu
# önbellekten kullanır, cevap süresini uzatmaz.
ORNEKLER = {
    "ogrenci": [
        ("METİNLER:\n[1] Eğitim-Öğretim Yönetmeliği, Madde 29 – Mazeret sınavı\n(1) Haklı ve geçerli nedenlerle sınavlarına "
         "giremeyen öğrencilere, ilgili yönetim kurulu kararlarıyla aynı yarıyıl içinde dersi veren öğretim elemanının "
         "belirleyeceği gün ve saatte kullanılmak üzere mazeret sınav hakkı verilir. Öğrencilerin mazeret sınavına "
         "girebilmeleri için sınav tarihinden itibaren 5 iş günü içerisinde mazeret dilekçelerini kayıtlı oldukları bölüm "
         "başkanlığına teslim etmeleri gerekir.\n\nSORU: Hastaydım vizeye giremedim, ne yapmalıyım?",
         "Haklı ve geçerli bir nedenle sınava giremediysen mazeret sınavı hakkı isteyebilirsin. Bunun için sınav tarihinden "
         "itibaren 5 iş günü içinde mazeret dilekçeni bölüm başkanlığına teslim etmelisin; sınav aynı yarıyıl içinde yapılır. [1]"),
        ("METİNLER:\n[1] Eğitim-Öğretim Yönetmeliği, Madde 9 – Kimlik kartı\n(1) Kesin kayıtlarını yaptıran öğrencilere, "
         "Üniversite tarafından öğrenci olduklarını belirten fotoğraflı bir kimlik kartı verilir.\n\nSORU: Kütüphane kaçta kapanıyor?",
         "BILMIYORUM"),
    ],
    "akademisyen": [
        ("METİNLER:\n[1] Teknik Hizmetler Yönergesi, Madde 2 – Derslik cihazları\nDersliklerdeki projeksiyon, ses sistemi ve "
         "akıllı tahta arızaları Yapı İşleri'ne bildirilir. Ders saatini etkileyen arızalara aynı gün, diğer arızalara en geç "
         "iki iş günü içinde müdahale edilir.\n\nSORU: Derste projeksiyon görüntü vermiyor, ne yapayım?",
         "Projeksiyon arızasını Yapı İşleri'ne bildirebilirsiniz. Ders saatini etkileyen arızalara aynı gün müdahale edilir. [1]"),
        ("METİNLER:\n[1] Personel İşlemleri Rehberi, Madde 7 – Hizmet belgesi\nHizmet belgesi e-Devlet üzerinden alınabilir."
         "\n\nSORU: Otopark kartımı nereden alırım?",
         "BILMIYORUM"),
    ],
}


# Örnek metinlerin AYIRT EDİCİ kelimeleri ("fotoğraflı", "kimlik", "kütüphane"); yaygın kelimeler sayılmaz
_ORNEK_KOKLERI = {k for rol in ORNEKLER for kullanici, cevap in ORNEKLER[rol] for k in kokler(kullanici + " " + cevap)
                  if agirlik(k) >= 3.0}


def _model_yuklu_mu() -> bool:
    yanit = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    yanit.raise_for_status()
    adlar = {m.get("name") for m in yanit.json().get("models", [])}
    adlar |= {a.split(":")[0] + ":latest" for a in adlar if ":" not in a}
    return MODEL in adlar or (":" not in MODEL and f"{MODEL}:latest" in adlar)


def modeli_hazirla():
    """Uygulama açılırken arka planda çalışır: Ollama'yı bekler, modelin imajda olduğunu
    doğrular ve ilk soruda beklememek için modeli bir kez belleğe yükler. Model indirmez."""
    for _ in range(90):  # en fazla ~7,5 dakika bekler
        try:
            yuklu = _model_yuklu_mu()
            break
        except Exception:
            DURUM.update(hazir=False, mesaj="Yapay zekâ servisi (Ollama) açılıyor, bekleniyor…")
            time.sleep(5)
    else:
        DURUM.update(hazir=False, mesaj="Yapay zekâ servisine ulaşılamadı. Asistan yedek modda (yönetmelik araması) çalışıyor.")
        log.warning("Ollama'ya ulaşılamadı: %s", OLLAMA_URL)
        return

    if not yuklu:
        DURUM.update(hazir=False, mesaj=f"{MODEL} modeli bulunamadı. Asistan yedek modda çalışıyor. "
                                         "MODEL ayarını değiştirdiyseniz 'docker compose up --build' ile yeniden derleyin.")
        log.warning("%s modeli Ollama'da yok.", MODEL)
        return

    DURUM.update(hazir=False, mesaj=f"{MODEL} belleğe yükleniyor (ilk açılışta bir dakika kadar sürebilir)…")
    try:
        # Sadece modeli yüklemek yetmez: sistem mesajı ve örnekler de bir kez işlenirse ilk soru hızlanır
        _sohbet_istegi(_mesajlar("Merhaba", [PARCALAR[0]], "ogrenci"), en_fazla_token=1)
    except Exception as hata:  # ısınma başarısız olsa da ilk soruda yüklenir
        log.info("Model ısınma isteği tamamlanamadı: %s", hata)
    DURUM.update(hazir=True, mesaj=f"Yapay zekâ hazır ({MODEL}, yerelde çalışıyor).")
    log.info("Yapay zekâ hazır: %s", MODEL)


def _mesajlar(soru: str, parcalar: list[dict], rol: str) -> list[dict]:
    rol = rol if rol in SISTEM_MESAJI else "ogrenci"
    maddeler = "\n\n".join(f"[{i}] {p['kaynak']}\n{p['govde']}" for i, p in enumerate(parcalar, 1))
    mesajlar = [{"role": "system", "content": SISTEM_MESAJI[rol]}]
    for kullanici, asistan_cevabi in ORNEKLER[rol]:
        mesajlar += [{"role": "user", "content": kullanici}, {"role": "assistant", "content": asistan_cevabi}]
    mesajlar.append({"role": "user", "content": f"METİNLER:\n{maddeler}\n\nSORU: {soru}"})
    return mesajlar


def _sohbet_istegi(mesajlar: list[dict], en_fazla_token: int | None = None) -> str:
    yanit = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "keep_alive": "24h",
            # CPU'da makul sürede cevap için: kısa bağlam, sınırlı cevap uzunluğu; düşük sıcaklık = daha tutarlı
            "options": {"temperature": 0.1, "top_p": 0.9, "repeat_penalty": 1.1, "num_ctx": 3072,
                        "num_predict": en_fazla_token or ayarlar.MODEL_EN_FAZLA_TOKEN},
            "messages": mesajlar,
        },
        timeout=ayarlar.MODEL_ZAMAN_ASIMI,
    )
    yanit.raise_for_status()
    return yanit.json()["message"]["content"].strip()


def modele_sor(soru: str, parcalar: list[dict], rol: str = "ogrenci") -> str:
    return _sohbet_istegi(_mesajlar(soru, parcalar, rol))


# ---------------------------------------------------------------------------
# Model cevabının denetimi
# ---------------------------------------------------------------------------
def _bilmiyorum_mu(cevap: str) -> bool:
    """Model "BILMIYORUM" dediyse True. Uzun bir cevabın içinde geçen tek bir "bilmiyorum" sayılmaz."""
    k = katla(cevap).strip(" .!\n")
    return k.startswith("bilmiyorum") or ("bilmiyorum" in k and len(k) < 60)


# Küçük modelin metin elindeyken verdiği kaçamak cevaplar (cevap değil, cevap vermeme)
KACAMAK = ("daha fazla bilgi", "bilgi sunabil", "yeterli bilgi", "net bir bilgi", "bilgi bulunmamakta",
           "bilgi verilmemis", "belirtilmemis", "emin degilim", "ilgili birime danis", "metinlerde yer almamakta",
           "metinde yer almiyor", "metinlerde bulunmamaktadir", "bu konuda bilgi")


def _kacamak_mi(cevap: str) -> bool:
    k = katla(cevap)
    return any(x in k for x in KACAMAK) and len(k) < 200


_YABANCI_YAZI = re.compile(r"[Ѐ-ӿ؀-ۿ぀-ヿ㐀-鿿가-힯]")


_SAYI_KELIMELERI = {"bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
                    "on": 10, "onbes": 15, "yirmi": 20, "otuz": 30, "kirk": 40, "elli": 50, "yuz": 100}


def _sayilar(metin: str) -> set[str]:
    """Metindeki sayılar, karşılaştırılabilir biçimde: "2,00" -> "2", "%70" -> "70", "3.50" -> "3.5", "iki" -> "2".
    ("bir" sayılmaz: Türkçede çoğunlukla belirsizlik sözcüğüdür: "bir dilekçe".)"""
    katli = katla(metin).replace("on bes", "onbes")
    ekler = [str(d) for k, d in _SAYI_KELIMELERI.items() if k != "bir" and re.search(rf"\b{k}\b", katli)]
    sonuc = set()
    for s in re.findall(r"\d+(?:[.,]\d+)?", metin) + ekler:
        s = s.replace(",", ".")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        sonuc.add(s.lstrip("0") or "0")
    return sonuc


def _dayaniyor_mu(cevap: str, parcalar: list[dict]) -> bool:
    """Cevap verilen maddelere gerçekten dayanıyor mu? Maddede de geçen en az 2 farklı kelime kökü içermeli
    ve cevabın anlamlı kelimelerinin en az %30'u maddelerde geçmeli.
    "Bilgi sunabilmem için daha fazla bilgi gerekmektedir" gibi metinden bağımsız cümleler elenir."""
    cevap_kokleri = set(kokler(re.sub(r"\[\d\]", " ", cevap)))
    if not cevap_kokleri:
        return False
    madde_kokleri = {kk for p in parcalar for kk in p["sayim"]}
    ortak = {c for c in cevap_kokleri if any(benzerlik(c, m) >= 1.0 for m in madde_kokleri)}
    return len(ortak) >= 2 and len(ortak) / len(cevap_kokleri) >= 0.30


def denetle(cevap: str, parcalar: list[dict], soru: str) -> tuple[bool, str, str]:
    """Model cevabını denetler ve temizler: (geçti mi, temiz cevap, geçmediyse sebebi)."""
    temiz = re.sub(r"^\s*(cevap|yanıt|yanit)\s*:\s*", "", cevap.strip(), flags=re.IGNORECASE)
    if not temiz or _bilmiyorum_mu(temiz):
        return False, "", "bilmiyorum"
    if _YABANCI_YAZI.search(temiz):
        return False, "", "yabanci_dil"
    if _kacamak_mi(temiz):
        return False, "", "kacamak"
    # Maddelerdeki sayılar (fıkra numaraları "(2)" ve madde numaraları hariç)
    madde_metni = re.sub(r"\(\d+\)|\bMadde\s+\d+|\b\d+\s*/\s*\d+\b", " ", " ".join(p["metin"] for p in parcalar))
    uydurma = _sayilar(re.sub(r"\[\d\]", " ", temiz)) - _sayilar(madde_metni + " " + soru)
    if uydurma:
        return False, "", "uydurma_sayi:" + ",".join(sorted(uydurma))
    # Model, talimattaki ÖRNEK metinlerden bilgi taşıdıysa ("fotoğraflı kimlik kartı") cevap geçersizdir
    madde_kokleri = {k for p in parcalar for k in p["sayim"]}
    sizan = {k for k in kokler(temiz) if k in _ORNEK_KOKLERI and k not in madde_kokleri}
    if len(sizan) >= 2:
        return False, "", "ornekten_sizinti"
    # "[1] ve [2] metinlerinde belirtilmiştir" gibi metinle ilgili açıklama cümleleri atılır
    cumleler = re.split(r"(?<=[.!?])\s+", temiz)
    temiz = " ".join(c for c in cumleler if not re.search(r"\bmet(i)?n\w*|\bverilen\s+bilgi|\bmadde\s+\d+'\w*\s+(gore|göre|ögren|öğren)",
                                                            c, flags=re.IGNORECASE)) or temiz
    if not _dayaniyor_mu(temiz, parcalar):
        return False, "", "dayanaksiz"
    temiz = re.sub(r"\b(metin|madde)\s*\[\d\]\s*'?(e|a|ye|ya|de|da)?\s*göre,?\s*", "Yönetmeliğe göre ", temiz, flags=re.IGNORECASE)
    if len(temiz) > 700:  # çok uzun cevabı cümle sonunda kes
        kes = max(temiz.rfind(". ", 0, 700), temiz.rfind("! ", 0, 700))
        temiz = temiz[: kes + 1] if kes > 200 else temiz[:700] + "…"
    return True, temiz, ""


def kaynak_ayikla(cevap: str, parcalar: list[dict]) -> tuple[str, list[str]]:
    """Modelin cevabın sonuna yazdığı [1][3] gibi numaraları okuyup metinden siler.
    Model numara yazmadıysa (küçük modeller bazen unutur) verilen tüm maddeler kaynak sayılır."""
    numaralar = [int(n) for n in re.findall(r"\[(\d)\]", cevap) if 1 <= int(n) <= len(parcalar)]
    temiz = re.sub(r"\s*(\[\d\]\s*)+", " ", cevap).strip()
    secilen = [parcalar[n - 1] for n in dict.fromkeys(numaralar)] or parcalar
    return temiz, kaynaklari_topla(secilen)


# ---------------------------------------------------------------------------
# Alıntı: model yoksa veya cevabı denetimden geçmediyse maddenin soruyla ilgili cümleleri
# ---------------------------------------------------------------------------
def _cumleler(govde: str) -> list[str]:
    parcalar = re.split(r"(?<=[.;:])\s+(?=[(A-ZÇĞİÖŞÜa-zçğıöşü0-9])|\n+", govde)
    return [p.strip() for p in parcalar if len(p.strip()) > 15]


def alinti(parca: dict, soru_kokleri: dict[str, float], en_fazla: int = 420) -> str:
    """Maddenin soruyla en ilgili 1-2 cümlesi (metindeki sırasıyla)."""
    cumleler = _cumleler(parca["govde"])
    if not cumleler:
        return parca["govde"][:en_fazla]
    puanlar = [(_kapsama(soru_kokleri, {k: 1.0 for k in kokler(c)}), i) for i, c in enumerate(cumleler)]
    puanlar.sort(reverse=True)
    secilen = [puanlar[0][1]]
    for puan, i in puanlar[1:3]:
        if puan >= 0.6 * puanlar[0][0] and sum(len(cumleler[j]) for j in secilen) + len(cumleler[i]) <= en_fazla:
            secilen.append(i)
    metin = " ".join(cumleler[i] for i in sorted(secilen))
    return metin if len(metin) <= en_fazla + 200 else metin[: en_fazla + 200].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------
# Cevap kalıpları
# ---------------------------------------------------------------------------
def _cevap(cevap, kip, emin, birim, kaynaklar=(), ilgili=(), oneriler=()) -> dict:
    kaynaklar = list(kaynaklar)
    return {"cevap": cevap, "kaynak": kaynaklar[0] if kaynaklar else None, "kaynaklar": kaynaklar,
            "ilgili": list(ilgili), "emin": emin, "birim": birim, "kip": kip, "oneriler": list(oneriler)}


def _oneriler(puanlar: list[tuple[float, float, dict]], haric: dict | None = None, adet: int = 3) -> list[str]:
    """Soruya kısmen benzeyen sık sorulan soruların ilk söylenişleri ("Bunu mu demek istedin?")."""
    return [g["sorular"][0] for f, _, g in puanlar if f >= ONERI_ESIK and g is not haric][:adet]


def emin_degilim(soru: str, rol: str, ilgili: list[dict] | None = None, oneriler=(), metin: str | None = None) -> dict:
    birim = yonlendir(soru, rol)
    siz = rol == "akademisyen"
    metin = metin or ("Bu konuda yönetmeliklerde net bir hüküm bulamadım. Yanlış bilgi vermemek için " +
                      (f"sorunuzu ilgili birime ({birim}) iletebilirim; yanıtı Taleplerim'de görürsünüz." if siz else
                       f"sorunu ilgili birime ({birim}) iletebilirim; yanıtı Taleplerim'de görürsün."))
    # Soruyu tam karşılamasa da göz atılabilecek maddeler (kaynak olarak SUNULMAZ)
    return _cevap(metin, "bulunamadi", False, birim, ilgili=kaynaklari_topla(ilgili or [])[:2], oneriler=oneriler)


def madde_cevabi(parca: dict, birim: str, kip: str, soru_kokleri: dict[str, float]) -> dict:
    """Soruyu güçlü karşılayan maddeden, soruyla ilgili cümleleri aynen alıntılar."""
    metin = "Yönetmelikte bu konuda şöyle yazıyor: “" + alinti(parca, soru_kokleri) + "”"
    return _cevap(metin, kip, True, birim, kaynaklar=[parca["kaynak"]])


def _secenek(anlam: dil.Anlam, puanlar, rol: str, birim: str, en_fazla_kelime: int, en_az_secenek: int = 2) -> dict | None:
    """Çok kısa ve genel bir soruya, ilgili birkaç hazır soruyu seçenek olarak sunar."""
    if not puanlar or len(set(kokler(anlam.ozgun))) > en_fazla_kelime:
        return None
    tam = [x for x in puanlar if x[1] >= 0.99 and x[0] > 0]
    if len(tam) < en_az_secenek:
        return None
    siz = rol == "akademisyen"
    return _cevap("Bu konuda birkaç farklı şey sorulabiliyor. Hangisini " + ("öğrenmek istersiniz?" if siz else "merak ediyorsun?"),
                  "secenek", True, birim, oneriler=[x[2]["sorular"][0] for x in tam[:4]])


SOHBET_NIYETLERI = {"selam", "nasilsin", "tesekkur", "veda", "kimsin", "onay", "hakaret"}


def cevapla(soru: str, rol: str = "ogrenci") -> dict:
    baslangic = time.monotonic()
    sonuc = _cevapla(soru, rol)
    log.info("Asistan: kip=%s emin=%s süre=%.1f sn", sonuc["kip"], sonuc["emin"], time.monotonic() - baslangic)  # soru loglanmaz (KVKK)
    return sonuc


def _cevapla(soru: str, rol: str) -> dict:
    varsayilan_birim = VARSAYILAN_BIRIM.get(rol, "Öğrenci İşleri")
    # 1. Sohbet
    niyet, soru = dil.niyet_bul(soru)
    if niyet in SOHBET_NIYETLERI:
        s = dil.sohbet_cevabi(niyet, rol)
        return _cevap(s["cevap"], "sohbet", True, varsayilan_birim, oneriler=s["oneriler"])
    onek = "Merhaba! " if niyet == "selam_soru" else ""

    def ekle(c: dict) -> dict:
        if onek:
            c["cevap"] = onek + c["cevap"]
        return c

    if dil.gorus_sorusu_mu(soru):
        return ekle(emin_degilim(soru, rol, metin=(
            "Bu bir görüş ya da tercih sorusu; yönetmeliklerde böyle bir değerlendirme yer almaz, "
            "bu yüzden yorum yapmam doğru olmaz.")))

    # 2. Soruyu anla
    anlam = dil.anla(soru, rol)
    soru_kokleri = agirlikli_kokler(anlam)
    if not soru_kokleri:
        return ekle(emin_degilim(soru, rol, metin=("Sorunu tam anlayamadım. Biraz daha ayrıntılı yazar mısın? "
                                                   "Örneğin: \"Kayıt dondurmak için ne gerekiyor?\"" if rol != "akademisyen" else
                                                   "Sorunuzu tam anlayamadım. Biraz daha ayrıntılı yazar mısınız?")))

    # Soruda kendi kelimesinden hiçbiri kalmadıysa (hepsi eş sesli/görüş kelimesi olarak elendi) ve anlamı
    # taşıyan bir ekleme de yoksa cevap uydurulmaz ("Hocamla nasıl görüşebilirim?")
    if not kokler(anlam.ozgun) and len(anlam.eklenen) == len(anlam.zayif_eklenen):
        return ekle(emin_degilim(soru, rol))

    # 3. Sık sorulan sorular
    puanlar = sss_puanla(anlam, rol)
    if puanlar:
        f, r, g = puanlar[0]
        # Çok kısa, genel soru ("burs", "staj", "yatay geçiş") ve birçok hazır soruya uyuyorsa: hangisini kastettiğini sor
        if f < 0.9:
            secenek = _secenek(anlam, puanlar, rol, varsayilan_birim, en_fazla_kelime=2, en_az_secenek=3)
            if secenek:
                return ekle(secenek)
        if f >= SSS_ESIK and r >= SSS_KAPSAMA_ESIK:
            if g["tur"] == "yonlendir":
                return ekle(_cevap(g["cevap"], "yonlendir", False, g["birim"]))
            return ekle(_cevap(g["cevap"], "sss", True, g["birim"], kaynaklar=g["kaynaklar"]))
        # Tek kelimelik genel soru ("burs", "staj"): hangi konuyu kastettiğini sor
        secenek = _secenek(anlam, puanlar, rol, varsayilan_birim, en_fazla_kelime=1)
        if secenek:
            return ekle(secenek)

    # 4. RAG: en ilgili maddeler
    sonuclar = ara_puanli(soru, rol, anlam=anlam)
    parcalar = [x["parca"] for x in sonuclar]
    if not sonuclar or anlam.etiketler & {"kredi_kyk", "saat_sorusu", "ders_notu"}:
        return ekle(emin_degilim(soru, rol, parcalar, oneriler=_oneriler(puanlar)))
    en_iyi = sonuclar[0]
    birim = en_iyi["parca"]["birim"] if en_iyi["guclu"] else yonlendir(soru, rol)

    # Arama ile hazır cevap aynı maddeyi gösteriyorsa (iki bağımsız yöntem uyuşuyorsa) hazır cevap verilir.
    # Hazır cevap cümlesi tam aynı olmasa da kaynak maddesi doğrulanmış olur.
    guclu_kaynaklar = [x["parca"]["kaynak"] for x in sonuclar if x["guclu"]][:2]
    cok_guclu_kaynaklar = [x["parca"]["kaynak"] for x in sonuclar if x["cok_guclu"]][:2]
    if guclu_kaynaklar and not _bilinmeyen_isimler(anlam):
        for f, r, g in puanlar[:6]:
            if g["tur"] != "sss" or not g["kaynaklar"]:
                continue
            if (f >= SSS_DESTEKLI_ESIK and set(g["kaynaklar"]) & set(cok_guclu_kaynaklar)) or \
               (f >= SSS_ZAYIF_DESTEK_ESIK and r >= 0.5 and g["kaynaklar"][0] == guclu_kaynaklar[0]):
                return ekle(_cevap(g["cevap"], "sss", True, g["birim"], kaynaklar=g["kaynaklar"]))

    # İki kelimelik genel soru ("yatay geçiş", "yaz okulu"): arama da tek bir maddeyi göstermediyse seçenek sun
    secenek = _secenek(anlam, puanlar, rol, VARSAYILAN_BIRIM.get(rol, "Öğrenci İşleri"), en_fazla_kelime=2)
    if secenek and not en_iyi["cok_guclu"]:
        return ekle(secenek)

    if en_iyi["guclu"]:
        # Modele sadece soruyu güçlü karşılayan maddeler verilir (en fazla 2): ilgisiz maddeler
        # (ör. "yurt" kelimesi yüzünden gelen "yurt dışı staj") küçük modeli şaşırtmasın.
        if en_iyi["cok_guclu"]:
            # Çok güçlü maddeye odaklan: aynı maddenin bölümleri + en fazla bir başka çok güçlü madde
            modele = [x["parca"] for x in sonuclar if x["parca"]["kaynak"] == en_iyi["parca"]["kaynak"]]
            modele += [x["parca"] for x in sonuclar if x["cok_guclu"] and x["parca"] not in modele][:max(0, 2 - len(modele))]
        else:
            modele = [x["parca"] for x in sonuclar if x["guclu"]][:2]
        if _bilinmeyen_isimler(anlam):
            # Soruda metinlerde hiç geçmeyen bir isim var ("misafir"): madde sorunun asıl konusunu içermiyor
            return ekle(emin_degilim(soru, rol, modele, oneriler=_oneriler(puanlar)))
        if DURUM["hazir"]:
            try:
                ham = modele_sor(soru, modele, rol)
                gecti, temiz, sebep = denetle(ham, modele, soru)
                if gecti:
                    metin, kaynaklar = kaynak_ayikla(temiz, modele)
                    c = _cevap(metin, "yapay_zeka", True, birim, kaynaklar=kaynaklar)
                    c["alinti"] = alinti(en_iyi["parca"], soru_kokleri)  # kullanıcı özeti maddenin kendisiyle karşılaştırabilsin
                    return ekle(c)
                log.info("Model cevabı denetimden geçmedi (%s).", sebep)
                # Model "bilmiyorum" dedi ya da cevabı denetimden geçmedi. Madde soruyu çok güçlü karşılıyorsa
                # (model yanılmış olabilir) ilgili cümleler alıntılanır; değilse modelin çekincesine güvenilir.
                if en_iyi["cok_guclu"]:
                    return ekle(madde_cevabi(en_iyi["parca"], birim, "alinti", soru_kokleri))
                return ekle(emin_degilim(soru, rol, modele, oneriler=_oneriler(puanlar)))
            except Exception as hata:
                log.warning("Model cevap veremedi, yedek moda geçildi: %s", hata)  # soru metni loglanmaz (KVKK)
        # Yedek mod (model yok): madde ancak soruyu çok güçlü karşılıyorsa alıntılanır
        if en_iyi["cok_guclu"]:
            return ekle(madde_cevabi(en_iyi["parca"], birim, "yedek", soru_kokleri))
        return ekle(emin_degilim(soru, rol, modele, oneriler=_oneriler(puanlar)))

    # 5. Soruyu tam karşılayan madde yok. Yakın bir madde varsa model kısmi bir cevap deneyebilir;
    #    bu cevap "kısmen emin" olarak işaretlenir ve personele iletme seçeneği sunulur.
    if DURUM["hazir"] and en_iyi["kapsam"] >= 0.60 and len(en_iyi["eksik"]) <= 1 and not _bilinmeyen_isimler(anlam):
        try:
            modele = parcalar[:2]
            ham = modele_sor(soru, modele, rol)
            gecti, temiz, sebep = denetle(ham, modele, soru)
            if gecti:
                metin, kaynaklar = kaynak_ayikla(temiz, modele)
                c = _cevap(metin, "yapay_zeka", False, birim, kaynaklar=kaynaklar, oneriler=_oneriler(puanlar))
                c["alinti"] = alinti(en_iyi["parca"], soru_kokleri)
                return ekle(c)
        except Exception as hata:
            log.warning("Model cevap veremedi: %s", hata)
    return ekle(emin_degilim(soru, rol, parcalar, oneriler=_oneriler(puanlar)))
