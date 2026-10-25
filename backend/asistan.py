"""
Gishe asistanı: Öğrenci ve akademisyen sorularını üniversitenin yönetmeliklerine dayanarak cevaplar.

Nasıl çalışır? (Bu yönteme RAG denir: "bul, sonra cevapla")
  1. "yonetmelikler" klasöründeki metinler maddelere bölünür.
  2. Soru gelince en ilgili maddeler basit bir kelime eşleştirmesiyle bulunur.
  3. Bu maddeler ve soru yapay zekâ modeline (Ollama üzerinden Qwen) verilir.
     Modelden SADECE bu maddelere dayanarak cevap vermesi istenir.
  4. İlgili madde yoksa, en iyi madde sorunun tamamını karşılamıyorsa (ör. soru iki ayrı konuyu
     birleştiriyorsa) veya model emin değilse asistan uydurmaz; "emin değilim" der ve soruyu
     doğru birime talep olarak iletmeyi önerir.

Model tamamen yerelde çalışır: Ollama servisi aynı docker compose içindedir ve model
ağırlıkları Docker imajı derlenirken indirilir. Hiçbir bulut yapay zekâ API'si çağrılmaz.

Model hazır değilse (servis açılıyor, bilgisayar yavaş vb.) asistan "yedek moda"
geçer: en ilgili yönetmelik maddesini doğrudan gösterir. Böylece uygulama çökmez.
"""
import logging
import math
import re
import time
from pathlib import Path

import httpx

import ayarlar

log = logging.getLogger("gishe.asistan")

OLLAMA_URL = ayarlar.OLLAMA_URL
MODEL = ayarlar.MODEL
KLASOR = Path(__file__).parent / "yonetmelikler"

DURUM = {"hazir": False, "model": MODEL, "mesaj": "Yapay zekâ modeli kontrol ediliyor…"}

# Aramada önemsiz sayılan kelimeler
DURAKLAR = set("""
ve ile bir bu şu o için mi mı mu mü ne neden nasıl nedir neler nerede nereden hangi kim
ben benim bana sen senin biz var yok olarak olur olursa gibi daha de da ki ya veya ama
çok en her kadar sonra önce olan ise istiyorum isterim lazım gerekiyor gerekir acaba
miyim mıyım muyum müyüm misin mısın merhaba lütfen teşekkürler öğrenci öğrenciyim
üniversite üniversitede okul yapmalıyım yapabilirim yapılır edebilir alabilir
söyler söyle söyleyebilir anlat anlatır anlatabilir misiniz musun müsün hakkında bilgi
nedir neler nelerdir ister istiyor istersem gerek gerekli şey şeyler hangisi kaç
gtü gebze teknik ise olarak eğer mi
alabilirim alınır alınabilir nereden yapmalıyım yapılmalı zaman olmalı olmalıyım edilir edilmeli
""".split())

# Talebi hangi birime yönlendireceğimizi belirleyen anahtar kelimeler (sıra önemli).
# Öğrenci ve akademisyen için ayrı kurallar var, çünkü baktıkları birimler farklı.
BILGI_ISLEM_KELIMELERI = ["e-posta", "eposta", "mail", "şifre", "parola", "internet", "wifi", "wi-fi",
                          "eduroam", "ağ ", "lisans", "yazılım", "obs", "moodle", "sistem", "giriş yapamıyorum"]
YONLENDIRME = {
    "ogrenci": [
        (["yurt", "barınma", "pansiyon", "yatak"], "Barınma Birimi"),
        (["harç", "iade", "ödeme", "dekont", "borç"], "Strateji Geliştirme"),
        (["intibak", "muafiyet", "staj", "yönetim kurulu", "ders içerik"], "Fakülte Sekreterliği"),
        (BILGI_ISLEM_KELIMELERI, "Bilgi İşlem"),
    ],
    "akademisyen": [
        (["arıza", "projeksiyon", "projektör", "klima", "ısıtma", "kalorifer", "priz", "elektrik",
          "lamba", "tesisat", "musluk", "kapı", "kilit", "asansör", "tamir"], "Yapı İşleri"),
        (BILGI_ISLEM_KELIMELERI + ["bilgisayar", "yazıcı"], "Bilgi İşlem"),
        (["izin", "görevlendirme", "maaş", "kadro", "sözleşme", "rapor", "sgk"], "Personel Daire Başkanlığı"),
    ],
}
VARSAYILAN_BIRIM = {"ogrenci": "Öğrenci İşleri", "akademisyen": "Fakülte Sekreterliği"}


# ---------------------------------------------------------------------------
# Metin işleme
# ---------------------------------------------------------------------------
def kucult(metin: str) -> str:
    """Türkçe'ye uygun küçük harfe çevirme (I -> ı, İ -> i)."""
    return metin.replace("I", "ı").replace("İ", "i").lower()


def kokler(metin: str) -> list[str]:
    """Kelimeleri bulur, önemsizleri atar, her kelimenin ilk 6 harfini 'kök' olarak tutar.
    Türkçe eklemeli bir dil olduğu için ön ek karşılaştırması iyi çalışır:
    'yurtta', 'yurtlarda' -> 'yurt…'. Eşleşmenin gücü ortak ön ekin uzunluğuna göre ölçülür."""
    kelimeler = re.findall(r"[a-zçğıöşü0-9]+", kucult(metin))
    return [k[:6] for k in kelimeler if len(k) > 2 and k not in DURAKLAR]


def benzerlik(a: str, b: str) -> float:
    """İki kökün benzerliği: 0 (yok), 0.4 (sadece ilk 4 harf ortak, ör. sınır/sınıf), 1 (güçlü eşleşme)."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    kisa = min(len(a), len(b))
    if n >= 5 or (n == kisa and kisa >= 3):
        return 1.0
    return 0.4 if n >= 4 else 0.0


def eslesir(a: str, b: str) -> bool:
    return benzerlik(a, b) >= 1.0


def yonlendir(metin: str, rol: str = "ogrenci") -> str:
    """Konuya ve talep edenin rolüne göre talebin gideceği birimi tahmin eder.
    1) Açık anahtar kelime kuralları (ör. "harç" -> Strateji Geliştirme),
    2) yoksa yönetmeliklerde GÜÇLÜ bir eşleşme varsa o maddenin birimi (asistanın kaynak gösterdiği
       madde ile talebin gittiği birim aynı olsun diye),
    3) o da yoksa rolün varsayılan birimi."""
    m = kucult(metin) + " "
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
                "kaynak": f"{baslik}, {madde}",
                "birim": birim,
                "kitle": kitle,
                "kokler": set(kokler(blok)),
            })
    return parcalar


PARCALAR = yonetmelikleri_yukle()

# Kelime ağırlıkları: bir kelime ailesi (ilk 4 harf) ne kadar az maddede geçiyorsa o kadar belirleyicidir.
# "burs", "yatay", "akts" ağır; "ders", "alabilir", "zaman" gibi her yerde geçenler hafif sayılır.
_AILE: dict[str, int] = {}
for _p in PARCALAR:
    _sayim: dict[str, int] = {}
    for _k in kokler(_p["metin"]):
        _sayim[_k] = _sayim.get(_k, 0) + 1
    _p["sayim"] = _sayim
    _p["kokler"] = frozenset(_sayim)
    _p["baslik_kokleri"] = set(kokler(_p["metin"].splitlines()[0]))
    for _a in {x[:4] for x in _sayim}:
        _AILE[_a] = _AILE.get(_a, 0) + 1
_N = max(1, len(PARCALAR))
BILINMEYEN_AGIRLIK = 1.5  # metinlerde hiç geçmeyen kelime ("futbol"): konu dışı soruları ayırt etmeye yardım eder


# Öğrencinin günlük dili ile yönetmelik dili arasındaki köprü (eş anlamlılar).
# Soruda soldaki kelime geçerse, maddede sağdakilerden biri de eşleşme sayılır.
ES_ANLAMLI = {
    "akts": ["kredi", "yükü"], "kredi": ["akts"],
    "devams": ["devam"], "devamsız": ["devam"],
    "dondur": ["izin", "yarıyıl"], "kaydım": ["kayıt"],
    "bırakm": ["çıkarm", "ekleme"], "bırakı": ["çıkarm"], "add": ["ekleme"], "drop": ["çıkarm"],
    "erasmu": ["değişi"], "değişi": ["erasmu"],
    "ortala": ["ortalam", "agno", "gno"], "agno": ["ortala"], "gno": ["ortala"],
    "harf": ["notlar"], "kaldım": ["başarı", "tekrar"], "kalırs": ["başarı", "tekrar"],
    "geçme": ["başarı"], "geçer": ["başarı"],
    "mezun": ["mezuni", "diplom"], "diplom": ["mezuni"],
    "transk": ["not", "transk"], "hazırl": ["ingili", "hazırl"],
    "yaz": ["yaz"], "çap": ["çift"], "çift": ["çift"],
    "sınırı": ["devam", "fazla", "azami"], "sınır": ["devam", "fazla", "azami"],
}


def es_anlamlilar(kok: str) -> list[str]:
    return [x for anahtar, liste in ES_ANLAMLI.items() if benzerlik(kok, anahtar) >= 1.0 for x in liste]


def agirlik(kok: str) -> float:
    adet = _AILE.get(kok[:4], 0)
    if not adet:
        return BILINMEYEN_AGIRLIK
    return max(0.3, math.log((_N + 1) / (adet + 0.5)))


# Bir maddenin soruyu "güçlü" karşılaması için: sorudaki, yönetmeliklerde geçen (bilinen) kelimelerin
# ağırlıkça en az bu oranı AYNI maddede bulunmalı ve belirleyici (ağır) bir bilinen kelime eksik olmamalı.
# Örnek: "Bursum kesilirse yurt ücreti değişir mi?" -> en iyi madde bursu anlatıyor ama "yurt" ve "ücret"
# o maddede yok. Soru iki konuyu birleştiriyor; asistan "emin değilim" der ve personele iletmeyi önerir.
# Yönetmeliklerde hiç geçmeyen kelimelerden ("kantin", "vegan") birden fazlası varsa soru büyük
# ihtimalle metinlerin konusu dışındadır; tek bir eşleşen kelime ("yemek") yüzünden "emin" denmez.
GUCLU_ESIK = 0.60
BELIRLEYICI_AGIRLIK = 2.0
EN_FAZLA_BILINMEYEN = 1


def ara_puanli(soru: str, rol: str = "ogrenci", adet: int = 3) -> list[dict]:
    """Soruyla en ilgili maddeleri puanlarıyla döndürür (sadece bu rolün görebileceği metinlerden).
    Her sonuç: {"parca", "sira", "kapsam", "guclu", "eksik"}.
    - kapsam: sorudaki kelimelerin ağırlıkça ne kadarı maddede karşılandı (0-1).
    - guclu: madde soruyu tek başına karşılıyor mu (bkz. GUCLU_ESIK, EN_FAZLA_BILINMEYEN).
    - eksik: maddede karşılanmayan, yönetmeliklerde geçen belirleyici kelimeler.
    Kapsam %40'ın altındaysa madde hiç listelenmez; asistan uydurmasın diye. Sıralamada kelimenin
    maddede kaç kez geçtiği ve madde başlığında olup olmadığı da hesaba katılır."""
    soru_kokleri = list(dict.fromkeys(kokler(soru)))
    if not soru_kokleri:
        return []
    agirliklar = {s: agirlik(s) for s in soru_kokleri}
    bilinen = {s for s in soru_kokleri if _AILE.get(s[:4])}
    bilinmeyen_sayisi = len(soru_kokleri) - len(bilinen)
    esler = {s: es_anlamlilar(s) for s in soru_kokleri}
    toplam = sum(agirliklar.values())
    bilinen_toplam = sum(agirliklar[s] for s in bilinen)
    puanli = []
    for p in PARCALAR:
        if p["kitle"] not in ("ortak", rol):
            continue
        kapsam = sira = bilinen_kapsam = 0.0
        eksik = []
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
                kapsam += a * guc
                sira += a * guc * (1.5 if baslikta else 1.0) * (1 + 0.35 * math.log(1 + tekrar))
                if s in bilinen:
                    bilinen_kapsam += a * guc
            # Kısmi kök eşleşmesi (ör. "unuttum" ~ "unutan", 0.4) eksik sayılmaz ama kapsama az katkı verir
            if guc < 0.4 and s in bilinen and a >= BELIRLEYICI_AGIRLIK:
                eksik.append(s)
        if kapsam >= 0.40 * toplam:
            oran = bilinen_kapsam / bilinen_toplam if bilinen_toplam else 0.0
            # Kısa sorularda (en fazla 2 bilinen kelime) hepsi karşılanmalı:
            # "Yurt başvurusu" sorusu "Yurt içi görevlendirme" maddesine sadece "yurt" ile bağlanmasın.
            esik = 0.78 if len(bilinen) <= 2 else GUCLU_ESIK  # eş anlamlı eşleşme (0.8) yeterli
            puanli.append({
                "parca": p, "sira": sira, "kapsam": round(kapsam / toplam, 3),
                "guclu": oran >= esik and not eksik and bilinmeyen_sayisi <= EN_FAZLA_BILINMEYEN,
                "eksik": eksik,
            })
    puanli.sort(key=lambda x: x["sira"], reverse=True)
    return puanli[:adet]


def ara(soru: str, rol: str = "ogrenci", adet: int = 3) -> list[dict]:
    """Geriye uyumluluk için: sadece maddeleri döndürür."""
    return [x["parca"] for x in ara_puanli(soru, rol, adet)]


def kaynaklari_topla(parcalar: list[dict]) -> list[str]:
    """Aynı maddenin bölümleri tek kaynak olarak gösterilir."""
    return list(dict.fromkeys(p["kaynak"] for p in parcalar))


# ---------------------------------------------------------------------------
# Yapay zekâ modeli
# ---------------------------------------------------------------------------
SISTEM_MESAJI = """Sen Gebze Teknik Üniversitesi'nin öğrenci işleri asistanı Gishe'sin.
Görevin, kullanıcının sorusunu YALNIZCA sana verilen numaralı yönetmelik, yönerge ve bilgi metinlerine dayanarak cevaplamak.
Kurallar:
- Kısa, net ve samimi Türkçe kullan (en fazla 5 cümle). Sayıları, süreleri ve koşulları metindeki gibi aynen ver.
- Metinlerde olmayan hiçbir bilgiyi ekleme, tahmin yürütme, genel bilgi verme.
- Metin soruyu kısmen cevaplıyorsa, bildiğin kısmı söyle ve gerisi için ilgili birime başvurulmasını öner.
- Cevabın en sonuna, dayandığın metinlerin numaralarını köşeli parantezle yaz. Örnek: [1] veya [1][3]
- Soru bu metinlerle hiç cevaplanamıyorsa yalnızca BILMIYORUM yaz."""


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
        httpx.post(f"{OLLAMA_URL}/api/generate", json={"model": MODEL, "prompt": "", "keep_alive": "24h"},
                   timeout=ayarlar.MODEL_ZAMAN_ASIMI).raise_for_status()
    except Exception as hata:  # ısınma başarısız olsa da ilk soruda yüklenir
        log.info("Model ısınma isteği tamamlanamadı: %s", hata)
    DURUM.update(hazir=True, mesaj=f"Yapay zekâ hazır ({MODEL}, yerelde çalışıyor).")
    log.info("Yapay zekâ hazır: %s", MODEL)


def modele_sor(soru: str, parcalar: list[dict]) -> str:
    maddeler = "\n\n".join(f"[{i}] {p['kaynak']}\n{p['metin']}" for i, p in enumerate(parcalar, 1))
    yanit = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "keep_alive": "24h",
            # CPU'da makul sürede cevap için: kısa bağlam, sınırlı cevap uzunluğu
            "options": {"temperature": 0.1, "num_ctx": 3072, "num_predict": ayarlar.MODEL_EN_FAZLA_TOKEN},
            "messages": [
                {"role": "system", "content": SISTEM_MESAJI},
                {"role": "user", "content": f"YÖNETMELİK MADDELERİ:\n{maddeler}\n\nKULLANICININ SORUSU: {soru}"},
            ],
        },
        timeout=ayarlar.MODEL_ZAMAN_ASIMI,
    )
    yanit.raise_for_status()
    return yanit.json()["message"]["content"].strip()


def kaynak_ayikla(cevap: str, parcalar: list[dict]) -> tuple[str, list[str]]:
    """Modelin cevabın sonuna yazdığı [1][3] gibi numaraları okuyup metinden siler.
    Model numara yazmadıysa (küçük modeller bazen unutur) verilen tüm maddeler kaynak sayılır."""
    numaralar = [int(n) for n in re.findall(r"\[(\d)\]", cevap) if 1 <= int(n) <= len(parcalar)]
    temiz = re.sub(r"\s*(\[\d\]\s*)+", " ", cevap).strip()
    secilen = [parcalar[n - 1] for n in dict.fromkeys(numaralar)] or parcalar
    return temiz, kaynaklari_topla(secilen)


def emin_degilim(soru: str, rol: str, ilgili: list[dict] | None = None) -> dict:
    birim = yonlendir(soru, rol)
    return {
        "cevap": ("Bu konuda yönetmeliklerde net bir hüküm bulamadım. Yanlış bilgi vermemek için "
                  f"sorunu ilgili birime ({birim}) iletebilirim; yanıtı Taleplerim'de görürsün."),
        "kaynak": None,
        "kaynaklar": [],
        # Soruyu tam karşılamasa da göz atılabilecek maddeler (kaynak olarak SUNULMAZ)
        "ilgili": kaynaklari_topla(ilgili or [])[:2],
        "emin": False,
        "birim": birim,
        "kip": "bulunamadi",
    }


def cevapla(soru: str, rol: str = "ogrenci") -> dict:
    sonuclar = ara_puanli(soru, rol)
    parcalar = [x["parca"] for x in sonuclar]
    if not sonuclar:
        return emin_degilim(soru, rol)
    en_iyi = sonuclar[0]
    # Madde soruyu tam karşılamıyorsa "Personele ilet" doğru birime gitsin
    birim = en_iyi["parca"]["birim"] if en_iyi["guclu"] else yonlendir(soru, rol)

    if DURUM["hazir"]:
        # Madde soruyu güçlü karşılıyorsa modele sadece güçlü maddeler verilir: ilgisiz maddeler
        # (ör. "yurt" kelimesi yüzünden gelen "yurt dışı staj") küçük modeli şaşırtıp BILMIYORUM dedirtmesin.
        modele = [x["parca"] for x in sonuclar if x["guclu"]] if en_iyi["guclu"] else parcalar
        try:
            cevap = modele_sor(soru, modele)
            if not cevap or _bilmiyorum_mu(cevap):
                # Arama soruyu karşılayan maddeyi bulduysa model çekinse de madde gösterilir (uydurma değil, metnin kendisi)
                if en_iyi["guclu"]:
                    return madde_cevabi(en_iyi["parca"], birim, "madde")
                return emin_degilim(soru, rol, parcalar)
            parcalar = modele
            metin, kaynaklar = kaynak_ayikla(cevap, parcalar)
            # Model cevap verse bile tek bir madde soruyu tam karşılamıyorsa kullanıcı uyarılır
            return {"cevap": metin, "kaynak": kaynaklar[0], "kaynaklar": kaynaklar, "ilgili": [],
                    "emin": en_iyi["guclu"], "birim": birim, "kip": "yapay_zeka"}
        except Exception as hata:
            log.warning("Model cevap veremedi, yedek moda geçildi: %s", hata)  # soru metni loglanmaz (KVKK)

    # Yedek mod: model yok. Madde ancak soruyu güçlü karşılıyorsa "cevap" olarak gösterilir.
    if not en_iyi["guclu"]:
        return emin_degilim(soru, rol, parcalar)
    return madde_cevabi(en_iyi["parca"], birim)


def _bilmiyorum_mu(cevap: str) -> bool:
    """Model "BILMIYORUM" dediyse True. Uzun bir cevabın içinde geçen tek bir "bilmiyorum" sayılmaz."""
    k = kucult(cevap).replace("ı", "i").strip(" .!\n")
    return k.startswith("bilmiyorum") or ("bilmiyorum" in k and len(k) < 60)


def madde_cevabi(parca: dict, birim: str, kip: str = "yedek") -> dict:
    """Soruyu güçlü karşılayan maddeyi olduğu gibi cevap olarak gösterir."""
    return {
        "cevap": "Sorunla en ilgili yönetmelik maddesi:\n\n" + parca["metin"],
        "kaynak": parca["kaynak"],
        "kaynaklar": [parca["kaynak"]],
        "ilgili": [],
        "emin": True,
        "birim": birim,
        "kip": kip,  # yedek: model hazır değil · madde: model kısa cevap üretemedi
    }
