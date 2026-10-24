"""
Gishe arka uç ayarları.

Tüm ayarlar ortam değişkenlerinden okunur; koda gömülü port, adres veya model adı yoktur.
Değerler depo kökündeki .env dosyasından gelir (örnek: .env.example). Bir değer verilmezse
aşağıdaki güvenli varsayılan kullanılır. Hatalı bir değer uygulamayı çökertmez, varsayılana düşer.
"""
import logging
import os

log = logging.getLogger("gishe.ayarlar")


def _metin(ad: str, varsayilan: str) -> str:
    deger = os.getenv(ad, "").strip()
    return deger or varsayilan


def _sayi(ad: str, varsayilan: float, en_az: float, en_cok: float) -> float:
    ham = os.getenv(ad, "").strip()
    if not ham:
        return varsayilan
    try:
        deger = float(ham)
    except ValueError:
        log.warning("%s sayı olmalı ('%s' verildi); varsayılan %s kullanılıyor.", ad, ham, varsayilan)
        return varsayilan
    return min(max(deger, en_az), en_cok)


def _evet_hayir(ad: str, varsayilan: bool) -> bool:
    ham = os.getenv(ad, "").strip().lower()
    if not ham:
        return varsayilan
    return ham in ("1", "true", "evet", "yes", "acik", "açık", "on")


def _liste(ad: str, varsayilan: str) -> list[str]:
    return [x.strip().rstrip("/") for x in _metin(ad, varsayilan).split(",") if x.strip()]


# Veritabanı dosyasının klasörü (Docker'da kalıcı bir birime bağlanır)
VERI_KLASORU = _metin("VERI_KLASORU", "/app/veri")

# Yapay zekâ servisi (Ollama) ve model
OLLAMA_URL = _metin("OLLAMA_URL", "http://ollama:11434").rstrip("/")
MODEL = _metin("MODEL", "qwen2.5:3b")
MODEL_ZAMAN_ASIMI = _sayi("MODEL_ZAMAN_ASIMI", 120, 10, 600)          # saniye
MODEL_EN_FAZLA_TOKEN = int(_sayi("MODEL_EN_FAZLA_TOKEN", 220, 32, 1024))  # CPU'da hız için cevap uzunluğu sınırı

# Tarayıcıdan API'ye doğrudan erişebilecek adresler (CORS)
CORS_KAYNAKLARI = _liste("CORS_KAYNAKLARI", "http://localhost:3000,http://127.0.0.1:3000")

# Oturum
OTURUM_SAAT = _sayi("OTURUM_SAAT", 12, 1, 24 * 7)
GUVENLI_CEREZ = _evet_hayir("GUVENLI_CEREZ", False)  # HTTPS arkasında yayınlanırsa true yapılmalı

# Demo modu: giriş ekranında örnek hesaplar listelenir ve şifresiz demo girişi açılır.
# GÜVENLİ VARSAYILAN: kapalı. Sunum için docker-compose.yml bunu açar (DEMO_MODU=true);
# uygulama başka bir yolla kurulursa demo girişi kendiliğinden açık OLMAZ.
DEMO_MODU = _evet_hayir("DEMO_MODU", False)
# Demo hesaplarının şifresi depoda yazmaz. .env'de verilmezse her kurulumda rastgele üretilir.
DEMO_SIFRE = os.getenv("DEMO_SIFRE", "").strip() or None

# Giriş denemesi sınırı: bir hesaba bu süre içinde bu kadar hatalı şifre girilirse hesap geçici olarak kilitlenir
GIRIS_DENEME_SINIRI = int(_sayi("GIRIS_DENEME_SINIRI", 10, 3, 100))
GIRIS_KILIT_DAKIKA = int(_sayi("GIRIS_KILIT_DAKIKA", 15, 1, 24 * 60))


def _tarih_listesi(ad: str) -> list[str]:
    import datetime as dt
    gecerli = []
    for x in _liste(ad, ""):
        try:
            dt.date.fromisoformat(x)
            gecerli.append(x)
        except ValueError:
            log.warning("%s içinde hatalı tarih: '%s' (YYYY-AA-GG olmalı); yok sayıldı.", ad, x)
    return gecerli


# Resmî tatillere ek olarak iş günü sayılmayacak günler (idari izin vb.), virgülle: 2026-10-30,2027-05-20
EK_TATILLER = _tarih_listesi("EK_TATILLER")

# ---- E-posta bildirimi (isteğe bağlı). SMTP_SUNUCU boşsa e-posta gönderilmez; uygulama içi işaretler yine çalışır.
SMTP_SUNUCU = _metin("SMTP_SUNUCU", "")
SMTP_PORT = int(_sayi("SMTP_PORT", 587, 1, 65535))
SMTP_KULLANICI = _metin("SMTP_KULLANICI", "")
SMTP_SIFRE = os.getenv("SMTP_SIFRE", "")
SMTP_GONDEREN = _metin("SMTP_GONDEREN", SMTP_KULLANICI or "gishe@localhost")
SMTP_GUVENLIK = _metin("SMTP_GUVENLIK", "starttls").lower()  # starttls | ssl | yok
if SMTP_GUVENLIK not in ("starttls", "ssl", "yok"):
    log.warning("SMTP_GUVENLIK 'starttls', 'ssl' veya 'yok' olmalı ('%s' verildi); starttls kullanılıyor.", SMTP_GUVENLIK)
    SMTP_GUVENLIK = "starttls"
# E-postadaki bağlantı: kullanıcıların uygulamayı açtığı adres
UYGULAMA_URL = _metin("UYGULAMA_URL", "http://localhost:3000").rstrip("/")

# Sonuçlanan bir talebi talep sahibi kaç gün içinde "çözülmedi" diyerek yeniden açabilir
YENIDEN_ACMA_GUN = int(_sayi("YENIDEN_ACMA_GUN", 30, 1, 365))
