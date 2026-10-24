"""
Gishe e-posta bildirimleri: talep sahibine "talebinde yeni gelişme var" e-postası.

- İsteğe bağlıdır. .env içinde SMTP_SUNUCU boşsa hiçbir e-posta gönderilmez (demo varsayılanı);
  kullanıcı yine uygulama içindeki "Yeni gelişme" işaretlerini görür.
- E-posta arka planda gönderilir; SMTP sunucusu yavaşsa veya hata verirse istek beklemez, uygulama çökmez.
- KVKK: e-postada mesajın içeriği YER ALMAZ; sadece talep numarası, konu, ne olduğu ve uygulamanın
  bağlantısı bulunur. Ayrıntı yalnızca giriş yapılarak görülür.
"""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

import ayarlar

log = logging.getLogger("gishe.bildirim")


def acik_mi() -> bool:
    return bool(ayarlar.SMTP_SUNUCU)


def _gonder(alici: str, konu: str, metin: str):
    mesaj = EmailMessage()
    mesaj["From"] = ayarlar.SMTP_GONDEREN
    mesaj["To"] = alici
    mesaj["Subject"] = konu
    mesaj.set_content(metin)
    try:
        if ayarlar.SMTP_GUVENLIK == "ssl":
            sunucu = smtplib.SMTP_SSL(ayarlar.SMTP_SUNUCU, ayarlar.SMTP_PORT, timeout=15,
                                      context=ssl.create_default_context())
        else:
            sunucu = smtplib.SMTP(ayarlar.SMTP_SUNUCU, ayarlar.SMTP_PORT, timeout=15)
        with sunucu:
            if ayarlar.SMTP_GUVENLIK == "starttls":
                sunucu.starttls(context=ssl.create_default_context())
            if ayarlar.SMTP_KULLANICI:
                sunucu.login(ayarlar.SMTP_KULLANICI, ayarlar.SMTP_SIFRE)
            sunucu.send_message(mesaj)
        log.info("Bildirim e-postası gönderildi.")  # alıcı adresi loglanmaz (KVKK)
    except Exception as hata:
        log.warning("Bildirim e-postası gönderilemedi: %s", hata)


def talep_gelismesi(alici: str, talep_no: str, talep_konu: str, ne_oldu: str):
    """Talep sahibine kısa bir bildirim gönderir. SMTP ayarlı değilse sessizce hiçbir şey yapmaz."""
    if not acik_mi() or not alici:
        return
    konu = f"[Gishe] #{talep_no} talebinizde yeni gelişme"
    metin = (
        f"Merhaba,\n\n"
        f"#{talep_no} numaralı \"{talep_konu}\" talebinizde yeni bir gelişme var:\n"
        f"  {ne_oldu}\n\n"
        f"Ayrıntıyı görmek ve yanıt vermek için Gishe'ye giriş yapın:\n"
        f"  {ayarlar.UYGULAMA_URL}\n\n"
        f"Bu e-posta otomatik gönderilmiştir, lütfen yanıtlamayın."
    )
    threading.Thread(target=_gonder, args=(alici, konu, metin), daemon=True).start()
