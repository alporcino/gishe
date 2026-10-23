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
# Gerçek kullanımda DEMO_MODU=false yapılır.
DEMO_MODU = _evet_hayir("DEMO_MODU", True)
# Demo hesaplarının şifresi depoda yazmaz. .env'de verilmezse her kurulumda rastgele üretilir.
DEMO_SIFRE = os.getenv("DEMO_SIFRE", "").strip() or None
