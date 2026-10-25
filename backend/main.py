"""
Gishe – Üniversite talep ve destek sistemi: arka uç (backend) API'si

Bu servis sadece API sunar; arayüz ayrı bir servistir (frontend/). Görevleri:
  1. Veritabanını (SQLite) kurmak ve örnek verilerle doldurmak
  2. Kullanıcı girişini ve ROL KONTROLÜNÜ yapmak
  3. Arayüzün kullandığı API adreslerini (/api/...) ve durum adresini (/health) sunmak
  4. Yapay zekâ asistanını (yerel Ollama + Qwen) iş mantığıyla birleştirmek

Temel kurallar (projenin fikri):
  - Kullanıcının rolünü (öğrenci / akademisyen / personel) kullanıcı SEÇEMEZ.
    Rol, giriş yapan hesabın veritabanındaki kaydından gelir ve her istekte
    SUNUCUDA kontrol edilir. Tarayıcıda oynamak işe yaramaz.
  - Her birim belirli bir kitleye hizmet eder (öğrenci, akademisyen veya ortak).
    Öğrenci, sadece akademisyenlere bakan bir birime talep açamaz.
  - Her talebin her an bir "sahibi" (birimi) vardır: "Şu an kimde?"
  - Talep başka birime aktarılırken GEREKÇE ZORUNLUDUR ve talep sahibi bunu görür.
  - Her birimin bir hedef yanıt süresi (iş günü) vardır; aşılırsa işaretlenir.
  - Talep sahibi, birimin her işleminden haberdar olur ("Yeni gelişme" işareti, isteğe bağlı e-posta).
  - Sonuçlanan talep puanlanabilir; çözülmediyse gerekçe yazılarak yeniden açılabilir.
"""
import datetime as dt
import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import asistan
import ayarlar
import bildirim
import tatiller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gishe")

TR = ZoneInfo("Europe/Istanbul")
VERI = Path(ayarlar.VERI_KLASORU)
VERI.mkdir(parents=True, exist_ok=True)
DB_YOLU = VERI / "gishe.db"
OTURUM_SURESI = dt.timedelta(hours=ayarlar.OTURUM_SAAT)

DURUMLAR = ["Yeni", "İnceleniyor", "Bilgi bekleniyor", "Sonuçlandı"]
ROL_ADI = {"ogrenci": "Öğrenci", "akademisyen": "Akademisyen", "personel": "Personel"}

# (id, ad, bağlı olduğu daire, hedef yanıt süresi - iş günü, hizmet verdiği kitle)
# kitle: "ogrenci" | "akademisyen" | "ortak"
BIRIMLER = [
    (1, "Öğrenci İşleri", "Öğrenci İşleri Daire Başkanlığı", 3, "ogrenci"),
    (2, "Barınma Birimi", "Sağlık, Kültür ve Spor Daire Başkanlığı", 3, "ogrenci"),
    (3, "Fakülte Sekreterliği", "Mühendislik Fakültesi", 5, "ortak"),
    (4, "Strateji Geliştirme", "Strateji Geliştirme Daire Başkanlığı", 5, "ogrenci"),
    (5, "Bilgi İşlem", "Bilgi İşlem Daire Başkanlığı", 2, "ortak"),
    (6, "Yapı İşleri", "Yapı İşleri ve Teknik Daire Başkanlığı", 2, "akademisyen"),
    (7, "Personel Daire Başkanlığı", "Personel Daire Başkanlığı", 5, "akademisyen"),
]

# Test hesapları: her rolden üçer tane. Kişiler KURGUSALDIR, gerçek kişilerle ilgisi yoktur.
# Şifreler koda gömülü DEĞİLDİR: her hesabın şifresi kendi ortam değişkeninden okunur
# (ör. OGRENCI1_SIFRE). Örnek değerler .env.example'dadır; docker compose bu dosyayı varsayılan olarak
# yükler, .env varsa onun değerleri geçerli olur. Değişken boşsa hesaba rastgele şifre verilir (girişe kapanır).
# (id, ad, e-posta, rol, açıklama, birim_id - sadece personel için, şifre değişkeni)
KULLANICILAR = [
    (1, "Elif Yıldırım", "e.yildirim2026@gtu.edu.tr", "ogrenci", "Mimarlık · 1. sınıf", None, "OGRENCI1_SIFRE"),
    (2, "Mert Kaya", "m.kaya2025@gtu.edu.tr", "ogrenci", "İnşaat Mühendisliği · 2. sınıf", None, "OGRENCI2_SIFRE"),
    (3, "Zeynep Aksoy", "z.aksoy2024@gtu.edu.tr", "ogrenci", "Moleküler Biyoloji ve Genetik · 3. sınıf", None,
     "OGRENCI3_SIFRE"),
    (4, "Dr. Öğr. Üyesi Selin Ergüven", "selin.erguven@gtu.edu.tr", "akademisyen", "Bilgisayar Mühendisliği", None,
     "AKADEMISYEN1_SIFRE"),
    (5, "Prof. Dr. Tarık Bozdağ", "tarik.bozdag@gtu.edu.tr", "akademisyen", "İnşaat Mühendisliği", None,
     "AKADEMISYEN2_SIFRE"),
    (6, "Doç. Dr. Nihan Karaca", "nihan.karaca@gtu.edu.tr", "akademisyen", "Elektronik Mühendisliği", None,
     "AKADEMISYEN3_SIFRE"),
    (11, "Gökhan Şeker", "gokhan.seker@gtu.edu.tr", "personel", "Öğrenci İşleri", 1, "PERSONEL1_SIFRE"),
    (12, "Derya Uçar", "derya.ucar@gtu.edu.tr", "personel", "Barınma Birimi", 2, "PERSONEL2_SIFRE"),
    (16, "Serkan Avcı", "serkan.avci@gtu.edu.tr", "personel", "Yapı İşleri", 6, "PERSONEL3_SIFRE"),
]
# Test hesaplarına e-posta bildirimi GÖNDERİLMEZ: adresler gerçek alan adında ama kişiler kurgusal.
TEST_EPOSTALAR = {h[2] for h in KULLANICILAR}


# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------
def simdi() -> dt.datetime:
    """Türkiye saatiyle şu anki zaman."""
    return dt.datetime.now(TR).replace(tzinfo=None, microsecond=0)


class Baglanti(sqlite3.Connection):
    """"with baglan() as con:" bloğu bitince işlemi kaydeder (hata varsa geri alır) VE bağlantıyı kapatır.
    (sqlite3'ün kendi "with" desteği bağlantıyı kapatmaz; kapatılmayan bağlantılar birikir.)"""

    def __exit__(self, *hata):
        try:
            return super().__exit__(*hata)
        finally:
            self.close()


def baglan() -> sqlite3.Connection:
    con = sqlite3.connect(DB_YOLU, factory=Baglanti, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


# OWASP 2023 önerisi: PBKDF2-HMAC-SHA256 için en az 600.000 tur. Eski kayıtlar (100.000 tur)
# ilk başarılı girişte otomatik olarak yeni tur sayısıyla yeniden özetlenir.
SIFRE_TUR = 600_000
ESKI_SIFRE_TUR = 100_000


def sifre_ozeti(sifre: str, tuz: bytes, tur: int = SIFRE_TUR) -> str:
    """Şifre veritabanına asla düz yazılmaz; tuzlanıp özetlenir (PBKDF2)."""
    return hashlib.pbkdf2_hmac("sha256", sifre.encode(), tuz, tur).hex()


def is_gunu_say(bas: dt.datetime, son: dt.datetime) -> int:
    """İki zaman arasında kaç iş günü geçtiğini sayar (hafta sonu ve resmî tatiller hariç)."""
    gun = 0
    d = bas.date()
    while d < son.date():
        d += dt.timedelta(days=1)
        if tatiller.is_gunu_mu(d):
            gun += 1
    return gun


def birim_getir(con, birim_id: int):
    b = con.execute("SELECT * FROM birimler WHERE id=?", (birim_id,)).fetchone()
    if not b:
        raise HTTPException(404, "Birim bulunamadı.")
    return b


def birim_id_bul(con, ad: str) -> Optional[int]:
    b = con.execute("SELECT id FROM birimler WHERE ad=?", (ad,)).fetchone()
    return b["id"] if b else None


def hizmet_verir(birim, rol: str) -> bool:
    """Bu birim bu roldeki kullanıcıların talebini kabul eder mi?"""
    return birim["kitle"] in ("ortak", rol)


# ---------------------------------------------------------------------------
# Veritabanı
# ---------------------------------------------------------------------------
SEMA = """
CREATE TABLE IF NOT EXISTS birimler (
    id INTEGER PRIMARY KEY,
    ad TEXT NOT NULL,
    daire TEXT NOT NULL,
    hedef_gun INTEGER NOT NULL,
    kitle TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kullanicilar (
    id INTEGER PRIMARY KEY,
    ad TEXT NOT NULL,
    eposta TEXT NOT NULL UNIQUE,
    rol TEXT NOT NULL CHECK (rol IN ('ogrenci', 'akademisyen', 'personel')),
    aciklama TEXT NOT NULL,
    birim_id INTEGER REFERENCES birimler(id),
    sifre_tuz TEXT NOT NULL,
    sifre_ozet TEXT NOT NULL,
    sifre_tur INTEGER NOT NULL DEFAULT 600000
);
CREATE TABLE IF NOT EXISTS oturumlar (
    anahtar TEXT PRIMARY KEY,
    kullanici_id INTEGER NOT NULL REFERENCES kullanicilar(id),
    bitis TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS talepler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    talep_eden_id INTEGER NOT NULL REFERENCES kullanicilar(id),
    birim_id INTEGER NOT NULL REFERENCES birimler(id),
    kategori TEXT NOT NULL DEFAULT '',
    konu TEXT NOT NULL,
    aciklama TEXT NOT NULL DEFAULT '',
    konum TEXT NOT NULL DEFAULT '',
    durum TEXT NOT NULL DEFAULT 'Yeni',
    olusturma TEXT NOT NULL,
    birime_gelis TEXT NOT NULL,   -- talep şu anki birime ne zaman geldi
    guncelleme TEXT NOT NULL,
    talep_eden_gordu INTEGER,     -- talep sahibinin gördüğü son olayın numarası ("Yeni gelişme" için)
    birim_gordu INTEGER,          -- birim personelinin gördüğü son olayın numarası
    sonuclanma TEXT,              -- talep ne zaman sonuçlandı (yeniden açma süresi için)
    puan INTEGER CHECK (puan BETWEEN 1 AND 5),  -- talep sahibinin memnuniyet puanı
    degerlendirme TEXT NOT NULL DEFAULT ''
);
-- Talebin "yolculuğu": her adım buraya bir satır olarak yazılır
CREATE TABLE IF NOT EXISTS olaylar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    talep_id INTEGER NOT NULL REFERENCES talepler(id),
    tur TEXT NOT NULL,            -- olusturuldu | aktarildi | mesaj_talep_eden | mesaj_birim | durum
                                  -- | degerlendirme | yeniden_acildi
    baslik TEXT NOT NULL,
    metin TEXT NOT NULL DEFAULT '',
    kimden TEXT NOT NULL DEFAULT '',
    zaman TEXT NOT NULL
);
-- Asistan istatistiği. KVKK gereği soru metni SAKLANMAZ, sadece zaman ve sonuç.
CREATE TABLE IF NOT EXISTS asistan_sayaci (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zaman TEXT NOT NULL,
    emin INTEGER NOT NULL
);
"""


def olay_ekle(con, talep_id, tur, baslik, metin="", kimden="", zaman=None):
    zaman = zaman or simdi()
    con.execute(
        "INSERT INTO olaylar (talep_id, tur, baslik, metin, kimden, zaman) VALUES (?,?,?,?,?,?)",
        (talep_id, tur, baslik, metin, kimden, zaman.isoformat()),
    )
    con.execute("UPDATE talepler SET guncelleme=? WHERE id=?", (zaman.isoformat(), talep_id))


def talep_olustur(con, talep_eden_id, birim_id, konu, aciklama, yonlendirme_notu,
                  kategori="", konum="", zaman=None) -> int:
    zaman = zaman or simdi()
    z = zaman.isoformat()
    cur = con.execute(
        "INSERT INTO talepler (talep_eden_id, birim_id, kategori, konu, aciklama, konum, durum, "
        "olusturma, birime_gelis, guncelleme) VALUES (?,?,?,?,?,?, 'Yeni', ?,?,?)",
        (talep_eden_id, birim_id, kategori, konu, aciklama, konum, z, z, z),
    )
    tid = cur.lastrowid
    olay_ekle(con, tid, "olusturuldu", "Talep oluşturuldu", yonlendirme_notu, "Sistem", zaman)
    con.execute("UPDATE talepler SET talep_eden_gordu=(SELECT MAX(id) FROM olaylar WHERE talep_id=?) WHERE id=?",
                (tid, tid))
    return tid


def talebi_aktar(con, talep_id, yeni_birim_id, gerekce, zaman=None):
    zaman = zaman or simdi()
    t = con.execute("SELECT birim_id FROM talepler WHERE id=?", (talep_id,)).fetchone()
    eski = birim_getir(con, t["birim_id"])["ad"]
    yeni = birim_getir(con, yeni_birim_id)["ad"]
    con.execute(
        "UPDATE talepler SET birim_id=?, birime_gelis=?, durum='Yeni', birim_gordu=NULL WHERE id=?",
        (yeni_birim_id, zaman.isoformat(), talep_id),
    )
    olay_ekle(con, talep_id, "aktarildi", f"Aktarıldı: {yeni}", gerekce, f"{eski} → {yeni}", zaman)


def durum_degistir(con, talep_id, yeni_durum, kimden, zaman=None):
    zaman = zaman or simdi()
    sonuclanma = zaman.isoformat() if yeni_durum == "Sonuçlandı" else None
    con.execute("UPDATE talepler SET durum=?, sonuclanma=? WHERE id=?", (yeni_durum, sonuclanma, talep_id))
    olay_ekle(con, talep_id, "durum", f"Durum: {yeni_durum}", "", kimden, zaman)


def ornek_veri(con):
    """Sunum için gerçekçi örnek veriler. Zamanlar 'şimdi'ye göre ayarlanır."""
    con.executemany("INSERT INTO birimler VALUES (?,?,?,?,?)", BIRIMLER)
    hesaplari_esitle(con)
    n = simdi()

    def once(**k):
        return n - dt.timedelta(**k)

    # --- Öğrenci talepleri ---
    # 1) Tasarımdaki örnek: birimden birime gönderilen yaz yurdu başvurusu
    t = talep_olustur(con, 1, 1, "Yaz dönemi yurt başvurusu",
                      "Yaz okulunda ders alacağım, yaz boyunca yurtta kalmak istiyorum.",
                      "Talep eden birimi kendisi seçti: Öğrenci İşleri", zaman=once(days=2, hours=6))
    talebi_aktar(con, t, 2, "Yaz yurdu başvuruları SKS'ye bağlı Barınma Birimi'nin yetkisinde.",
                 once(days=2, hours=2))
    olay_ekle(con, t, "mesaj_birim", "Barınma Birimi mesaj gönderdi",
              "Başvurunuzu değerlendirebilmemiz için gelir durumu belgesi gerekiyor.",
              "Barınma Birimi", once(days=1, hours=22))
    durum_degistir(con, t, "Bilgi bekleniyor", "Barınma Birimi", once(days=1, hours=22))
    olay_ekle(con, t, "mesaj_talep_eden", "Talep eden yanıt verdi",
              "Gelir belgemi e-Devlet'ten aldım, belgeyi yanıt olarak ekledim.", "Elif Yıldırım", once(days=1, hours=9))
    durum_degistir(con, t, "İnceleniyor", "Barınma Birimi", once(hours=5))

    # 2) Sonuçlanmış basit bir talep
    t = talep_olustur(con, 1, 1, "İngilizce öğrenci belgesi",
                      "Erasmus başvurusu için İngilizce öğrenci belgesine ihtiyacım var.",
                      "Otomatik yönlendirme: Öğrenci İşleri", zaman=once(days=6))
    olay_ekle(con, t, "mesaj_birim", "Öğrenci İşleri mesaj gönderdi",
              "Belgeniz hazırlandı, Öğrenci İşleri gişesinden teslim alabilirsiniz.",
              "Öğrenci İşleri", once(days=5))
    durum_degistir(con, t, "Sonuçlandı", "Öğrenci İşleri", once(days=5))

    # 3) Yeni gelmiş kayıt dondurma talebi
    talep_olustur(con, 2, 1, "Kayıt dondurma",
                  "Sağlık sorunum nedeniyle bu dönem kaydımı dondurmak istiyorum. Raporum var.",
                  "Otomatik yönlendirme: Öğrenci İşleri", zaman=once(days=1, hours=2))

    # 4) Hedef süreyi aşmış talep
    t = talep_olustur(con, 3, 1, "İngilizce not dökümü (transkript)",
                      "Yüksek lisans başvurusu için İngilizce transkript lazım.",
                      "Otomatik yönlendirme: Öğrenci İşleri", zaman=once(days=7))
    durum_degistir(con, t, "İnceleniyor", "Öğrenci İşleri", once(days=6))

    # 5) Harç iadesi
    talep_olustur(con, 2, 4, "Harç iadesi",
                  "Fazladan yatırdığım harç ücretinin iadesini istiyorum.",
                  "Otomatik yönlendirme: Strateji Geliştirme", zaman=once(hours=3))

    # 6) Öğrenciden Bilgi İşlem'e (ortak birim)
    talep_olustur(con, 3, 5, "Öğrenci e-postama giriş yapamıyorum",
                  "Şifremi sıfırladım ama hâlâ giriş yapamıyorum.",
                  "Otomatik yönlendirme: Bilgi İşlem", kategori="Bilgi işlem", zaman=once(hours=20))

    # --- Akademisyen talepleri ---
    # 7) Projeksiyon arızası: önce yanlış birime gitmiş, gerekçeyle aktarılmış
    t = talep_olustur(con, 4, 5, "B-204 projeksiyon görüntü vermiyor",
                      "Bilgisayar bağlanıyor ama projeksiyon 'sinyal yok' diyor. Yarın 09.00'da dersim var.",
                      "Talep eden birimi kendisi seçti: Bilgi İşlem", kategori="Teknik arıza",
                      konum="Mühendislik Fakültesi B Blok, B-204", zaman=once(days=1, hours=5))
    talebi_aktar(con, t, 6, "Bilgisayar ve ağ sorunsuz; projeksiyon cihazının kendisi Yapı İşleri'nin sorumluluğunda.",
                 once(days=1, hours=4))
    olay_ekle(con, t, "mesaj_birim", "Yapı İşleri mesaj gönderdi",
              "Teknisyen atandı. Yarın 08.30'da sınıfta olacak, dersinizden önce çözülmesi hedefleniyor.",
              "Yapı İşleri", once(hours=20))
    durum_degistir(con, t, "İnceleniyor", "Yapı İşleri", once(hours=20))

    # 8) Yazılım lisansı: sonuçlanmış
    t = talep_olustur(con, 4, 5, "MATLAB lisans yenileme",
                      "Laboratuvar bilgisayarlarındaki MATLAB lisansının süresi doldu.",
                      "Otomatik yönlendirme: Bilgi İşlem", kategori="Bilgi işlem",
                      konum="Bilgisayar Laboratuvarı 2", zaman=once(days=4))
    olay_ekle(con, t, "mesaj_birim", "Bilgi İşlem mesaj gönderdi",
              "Lisans yenilendi, laboratuvardaki 30 bilgisayarda etkinleştirildi.", "Bilgi İşlem", once(days=3))
    durum_degistir(con, t, "Sonuçlandı", "Bilgi İşlem", once(days=3))

    # 9) Klima arızası: hedef süre aşılmış
    t = talep_olustur(con, 5, 6, "Ofis kliması çalışmıyor",
                      "Klima açılıyor ama soğutmuyor.", "Otomatik yönlendirme: Yapı İşleri",
                      kategori="Teknik arıza", konum="İnşaat Mühendisliği, Oda 312", zaman=once(days=5))

    # 10) Personel işleri
    talep_olustur(con, 5, 7, "Kongre için görevlendirme",
                  "Kasım ayındaki ulusal kongre için 3 günlük görevlendirme talep ediyorum.",
                  "Otomatik yönlendirme: Personel Daire Başkanlığı", kategori="Personel işleri",
                  zaman=once(hours=6))

    # 11) Laboratuvarda elektrik arızası (üçüncü akademisyen)
    talep_olustur(con, 6, 6, "Laboratuvar prizlerinde elektrik yok",
                  "Deney masalarındaki prizlerin hiçbirinde elektrik yok, sigorta kapalı görünmüyor.",
                  "Otomatik yönlendirme: Yapı İşleri", kategori="Teknik arıza",
                  konum="Elektronik Mühendisliği, Devre Laboratuvarı", zaman=once(hours=4))

    # MATLAB talebi: akademisyen sonuçtan memnun, değerlendirmiş (personel panelindeki memnuniyet için)
    con.execute("UPDATE talepler SET puan=5, degerlendirme=? WHERE konu='MATLAB lisans yenileme'",
                ("Hızlı çözüldü, teşekkürler.",))
    olay_ekle(con, 8, "degerlendirme", "Talep sahibi değerlendirdi: 5/5", "Hızlı çözüldü, teşekkürler.",
              "Dr. Öğr. Üyesi Selin Ergüven", once(days=2, hours=20))

    # Görülme zamanları: herkes taleplerine bakmış sayılır, demo için iki istisna:
    #  - Elif, yurt talebindeki son gelişmeyi (İnceleniyor) henüz görmedi -> "Yeni gelişme"
    #  - Öğrenci İşleri, Mert'in yeni kayıt dondurma talebine henüz bakmadı -> "Yeni"
    son = "(SELECT MAX(o.id) FROM olaylar o WHERE o.talep_id = talepler.id)"
    con.execute(f"UPDATE talepler SET talep_eden_gordu={son}, birim_gordu={son}")
    con.execute("UPDATE talepler SET talep_eden_gordu=(SELECT MAX(o.id) FROM olaylar o WHERE o.talep_id = "
                "talepler.id AND o.tur='mesaj_talep_eden') WHERE konu='Yaz dönemi yurt başvurusu'")
    con.execute("UPDATE talepler SET birim_gordu=NULL WHERE konu='Kayıt dondurma'")


def sutun_ekle(con, tablo: str, sutun: str, tanim: str):
    """Eski sürümle oluşturulmuş veritabanına (kalıcı Docker birimi) yeni sütunu ekler; veri kaybolmaz."""
    if sutun not in {r["name"] for r in con.execute(f"PRAGMA table_info({tablo})")}:
        con.execute(f"ALTER TABLE {tablo} ADD COLUMN {sutun} {tanim}")


def gocler(con):
    # Eski kayıtların şifresi 100.000 turla özetlenmişti
    sutun_ekle(con, "kullanicilar", "sifre_tur", f"INTEGER NOT NULL DEFAULT {ESKI_SIFRE_TUR}")
    # Bildirim ve değerlendirme sütunları
    for sutun, tanim in [("talep_eden_gordu", "INTEGER"), ("birim_gordu", "INTEGER"), ("sonuclanma", "TEXT"),
                         ("puan", "INTEGER"), ("degerlendirme", "TEXT NOT NULL DEFAULT ''")]:
        sutun_ekle(con, "talepler", sutun, tanim)


def hesaplari_esitle(con):
    """Test hesaplarını veritabanına yazar ve şifrelerini ortam değişkenlerinden günceller.
    Her açılışta çalışır: .env'de şifre değiştirilirse ya da boşaltılırsa yeniden başlatınca geçerli olur.
    Eski sürümden kalan, artık listede olmayan ve talebi bulunmayan hesaplar silinir."""
    gecerli = [h[0] for h in KULLANICILAR]
    yer = ",".join("?" * len(gecerli))
    eskiler = [r["id"] for r in con.execute(
        f"SELECT id FROM kullanicilar WHERE id NOT IN ({yer}) "
        "AND id NOT IN (SELECT talep_eden_id FROM talepler)", gecerli)]
    for kid in eskiler:
        con.execute("DELETE FROM oturumlar WHERE kullanici_id=?", (kid,))
        con.execute("DELETE FROM kullanicilar WHERE id=?", (kid,))

    eksik = []
    for kid, ad, eposta, rol, aciklama, birim_id, degisken in KULLANICILAR:
        sifre = ayarlar.hesap_sifresi(degisken)
        var = con.execute("SELECT id FROM kullanicilar WHERE id=?", (kid,)).fetchone()
        if var:
            con.execute("UPDATE kullanicilar SET ad=?, eposta=?, rol=?, aciklama=?, birim_id=? WHERE id=?",
                        (ad, eposta, rol, aciklama, birim_id, kid))
        if not sifre:
            eksik.append(degisken)
            sifre = secrets.token_urlsafe(24)  # şifre verilmedi: rastgele şifre, kimse giremez
        tuz = secrets.token_bytes(16)
        if var:
            con.execute("UPDATE kullanicilar SET sifre_tuz=?, sifre_ozet=?, sifre_tur=? WHERE id=?",
                        (tuz.hex(), sifre_ozeti(sifre, tuz), SIFRE_TUR, kid))
        else:
            con.execute(
                "INSERT INTO kullanicilar (id, ad, eposta, rol, aciklama, birim_id, sifre_tuz, sifre_ozet, sifre_tur) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (kid, ad, eposta, rol, aciklama, birim_id, tuz.hex(), sifre_ozeti(sifre, tuz), SIFRE_TUR))
    if eksik:
        log.warning("Şifresi tanımlanmamış test hesapları (girişe kapalı): %s", ", ".join(eksik))


def kur(sifirla: bool = False):
    if sifirla and DB_YOLU.exists():
        DB_YOLU.unlink()
    with baglan() as con:
        con.executescript(SEMA)
        gocler(con)
        if con.execute("SELECT COUNT(*) FROM birimler").fetchone()[0] == 0:
            ornek_veri(con)
        else:
            hesaplari_esitle(con)


# ---------------------------------------------------------------------------
# Giriş ve yetki
# ---------------------------------------------------------------------------
def kullanici_ozet(k) -> dict:
    return {
        "id": k["id"], "ad": k["ad"], "eposta": k["eposta"], "rol": k["rol"],
        "rol_adi": ROL_ADI[k["rol"]], "aciklama": k["aciklama"], "birim_id": k["birim_id"],
    }


def aktif_kullanici(request: Request) -> dict:
    """Her korumalı API isteğinde çalışır: çerezdeki oturum anahtarından kullanıcıyı bulur.
    Kullanıcının rolü TARAYICIDAN DEĞİL, veritabanından gelir."""
    anahtar = request.cookies.get("oturum")
    if not anahtar:
        raise HTTPException(401, "Giriş yapmanız gerekiyor.")
    with baglan() as con:
        k = con.execute(
            "SELECT k.* FROM oturumlar o JOIN kullanicilar k ON k.id = o.kullanici_id "
            "WHERE o.anahtar=? AND o.bitis > ?", (anahtar, simdi().isoformat())).fetchone()
    if not k:
        raise HTTPException(401, "Oturumunuzun süresi doldu, lütfen tekrar giriş yapın.")
    return kullanici_ozet(k)


def rol_gerekli(*roller):
    def kontrol(kullanici: dict = Depends(aktif_kullanici)) -> dict:
        if kullanici["rol"] not in roller:
            raise HTTPException(403, "Bu işlem için yetkiniz yok.")
        return kullanici
    return kontrol


def talebe_erisim(con, talep_id: int, kullanici: dict) -> dict:
    """Talebi, sadece talep eden kişi ve talebin şu an bulunduğu birimin personeli görebilir."""
    t = talep_getir(con, talep_id)
    if kullanici["rol"] == "personel":
        if t["birim_id"] != kullanici["birim_id"]:
            raise HTTPException(403, "Bu talep sizin biriminizde değil.")
    elif t["talep_eden_id"] != kullanici["id"]:
        raise HTTPException(403, "Bu talebi görüntüleme yetkiniz yok.")
    return t


# ---------------------------------------------------------------------------
# Talep verisini arayüze uygun hâle getirme
# ---------------------------------------------------------------------------
# son_birim_olayi: birimin talep sahibini ilgilendiren son işleminin numarası (mesaj, durum, aktarma)
# son_talep_eden_olayi: talep sahibinin birimi ilgilendiren son işleminin numarası (mesaj, yeniden açma, değerlendirme)
# Olay numaraları sürekli arttığı için "gördüğü son numaradan büyük" = görmediği gelişme (aynı saniyede de doğru).
TALEP_SORGU = """
SELECT t.*, b.ad AS birim_ad, b.daire, b.hedef_gun,
       k.ad AS talep_eden_ad, k.rol AS talep_eden_rol, k.aciklama AS talep_eden_aciklama,
       (SELECT MAX(o.id) FROM olaylar o WHERE o.talep_id = t.id
          AND o.tur IN ('mesaj_birim', 'durum', 'aktarildi') AND o.kimden <> 'Sistem') AS son_birim_olayi,
       (SELECT MAX(o.id) FROM olaylar o WHERE o.talep_id = t.id
          AND o.tur IN ('mesaj_talep_eden', 'yeniden_acildi', 'degerlendirme')) AS son_talep_eden_olayi
FROM talepler t
JOIN birimler b ON b.id = t.birim_id
JOIN kullanicilar k ON k.id = t.talep_eden_id
"""


def yeniden_acilabilir(r) -> bool:
    if r["durum"] != "Sonuçlandı":
        return False
    if not r["sonuclanma"]:  # eski sürümden kalan kayıt: sonuçlanma zamanı bilinmiyor, izin ver
        return True
    return simdi() - dt.datetime.fromisoformat(r["sonuclanma"]) <= dt.timedelta(days=ayarlar.YENIDEN_ACMA_GUN)


def talep_ozet(r) -> dict:
    acik = r["durum"] != "Sonuçlandı"
    gecen = is_gunu_say(dt.datetime.fromisoformat(r["birime_gelis"]), simdi())
    # "Yeni gelişme": karşı tarafın son işlemi, bu tarafın gördüğü son olaydan sonra mı?
    son_birim, gordu = r["son_birim_olayi"], r["talep_eden_gordu"] or 0
    son_talep_eden, birim_gordu = r["son_talep_eden_olayi"] or 0, r["birim_gordu"]
    return {
        "id": r["id"],
        "no": f"GS-{2400 + r['id']}",
        "kategori": r["kategori"],
        "konu": r["konu"],
        "aciklama": r["aciklama"],
        "konum": r["konum"],
        "durum": r["durum"],
        "birim_id": r["birim_id"],
        "birim": r["birim_ad"],
        "daire": r["daire"],
        "hedef_gun": r["hedef_gun"],
        "talep_eden_id": r["talep_eden_id"],
        "talep_eden": r["talep_eden_ad"],
        "talep_eden_rol": r["talep_eden_rol"],
        "talep_eden_rol_adi": ROL_ADI[r["talep_eden_rol"]],
        "talep_eden_aciklama": r["talep_eden_aciklama"],
        "olusturma": r["olusturma"],
        "birime_gelis": r["birime_gelis"],
        "guncelleme": r["guncelleme"],
        "gecen_gun": gecen,
        "kalan_gun": (r["hedef_gun"] - gecen) if acik else None,
        "suresi_asti": acik and gecen > r["hedef_gun"],
        "yeni_gelisme": bool(son_birim and son_birim > gordu),
        # Birime yeni geldiyse (birim_gordu boş) ya da talep sahibi yeni bir şey yaptıysa
        "birimde_yeni": birim_gordu is None or son_talep_eden > birim_gordu,
        "sonuclanma": r["sonuclanma"],
        "puan": r["puan"],
        "degerlendirme": r["degerlendirme"],
        "yeniden_acilabilir": yeniden_acilabilir(r),
    }


def talep_getir(con, talep_id: int) -> dict:
    r = con.execute(TALEP_SORGU + " WHERE t.id=?", (talep_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Talep bulunamadı.")
    return talep_ozet(r)


def talep_detayi(con, talep_id: int) -> dict:
    talep = talep_getir(con, talep_id)
    talep["olaylar"] = [dict(r) for r in con.execute(
        "SELECT * FROM olaylar WHERE talep_id=? ORDER BY zaman, id", (talep_id,))]
    return talep


# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------
@asynccontextmanager
async def yasam_dongusu(app):
    kur()
    log.info("Veritabanı hazır: %s", DB_YOLU)
    # Yapay zekâ modelini arka planda yokla ve belleğe al (model imajın içinde hazır gelir)
    threading.Thread(target=asistan.modeli_hazirla, daemon=True).start()
    yield


app = FastAPI(
    title="Gishe API",
    description="Üniversite talep ve destek sistemi. Arayüz ayrı servistir (varsayılan http://localhost:3000).",
    version="1.0.0",
    lifespan=yasam_dongusu,
)

# Arayüz tarayıcıda farklı bir adresten (port 3000) çalıştığı için API'ye erişimine izin verilir.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ayarlar.CORS_KAYNAKLARI,
    allow_credentials=True,          # oturum çerezi için
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ----------------------------------------------------------------- Hata yönetimi
# Hatalı veya eksik girdi uygulamayı çökertmez; kullanıcıya anlaşılır bir Türkçe mesaj döner.
ALAN_ADI = {"eposta": "E-posta", "sifre": "Şifre", "konu": "Konu", "aciklama": "Açıklama", "metin": "Mesaj",
            "gerekce": "Gerekçe", "birim_id": "Birim", "durum": "Durum", "soru": "Soru",
            "puan": "Puan", "yorum": "Yorum"}


@app.exception_handler(RequestValidationError)
async def girdi_hatasi(request: Request, hata: RequestValidationError):
    alanlar = []
    for h in hata.errors():
        yer = [str(x) for x in h.get("loc", []) if x != "body"]
        if yer:
            alanlar.append(ALAN_ADI.get(yer[-1], yer[-1]))
    mesaj = "Gönderilen bilgiler eksik veya hatalı."
    if alanlar:
        mesaj += " Kontrol edin: " + ", ".join(dict.fromkeys(alanlar)) + "."
    return JSONResponse(status_code=422, content={"detail": mesaj})


@app.exception_handler(Exception)
async def beklenmeyen_hata(request: Request, hata: Exception):
    log.exception("Beklenmeyen hata: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={
        "detail": "Beklenmeyen bir hata oluştu. Lütfen biraz sonra tekrar deneyin."})


# ----------------------------------------------------------------- Durum
@app.get("/")
def kok():
    return {"ad": "Gishe API", "belgeler": "/docs", "durum": "/health"}


@app.get("/health")
def saglik():
    """Servisin ve bağlı bileşenlerin durumu. Docker sağlık kontrolü de bunu kullanır."""
    try:
        with baglan() as con:
            con.execute("SELECT 1").fetchone()
        veritabani = "çalışıyor"
    except Exception:
        veritabani = "ulaşılamıyor"
    return {
        "durum": "ok" if veritabani == "çalışıyor" else "sorunlu",
        "veritabani": veritabani,
        "yapay_zeka": dict(asistan.DURUM),
        "demo_modu": ayarlar.DEMO_MODU,
    }


# ----------------------------------------------------------------- Giriş / çıkış
class Giris(BaseModel):
    eposta: str
    sifre: str


def oturum_ac(con, k, response: Response) -> dict:
    anahtar = secrets.token_urlsafe(32)
    con.execute("DELETE FROM oturumlar WHERE bitis < ?", (simdi().isoformat(),))
    con.execute("INSERT INTO oturumlar VALUES (?,?,?)",
                (anahtar, k["id"], (simdi() + OTURUM_SURESI).isoformat()))
    con.commit()
    response.set_cookie("oturum", anahtar, httponly=True, samesite="lax", secure=ayarlar.GUVENLI_CEREZ,
                        max_age=int(OTURUM_SURESI.total_seconds()))
    return kullanici_ozet(k)


# Hatalı giriş sayacı (e-posta başına). Arka uç nginx'in arkasında olduğu için IP'ye göre değil
# hesaba göre sınırlanır: bir hesaba kaba kuvvetle şifre denenmesini engeller.
_HATALI_GIRIS: dict[str, list[dt.datetime]] = {}
_GIRIS_KILIDI = threading.Lock()


def _hatali_denemeler(eposta: str) -> list[dt.datetime]:
    sinir = simdi() - dt.timedelta(minutes=ayarlar.GIRIS_KILIT_DAKIKA)
    liste = [z for z in _HATALI_GIRIS.get(eposta, []) if z > sinir]
    _HATALI_GIRIS[eposta] = liste
    return liste


@app.post("/api/giris")
def giris(istek: Giris, response: Response):
    eposta = istek.eposta.strip().lower()[:120]
    if not eposta or not istek.sifre:
        raise HTTPException(400, "E-posta ve şifre gerekli.")
    with _GIRIS_KILIDI:
        if len(_hatali_denemeler(eposta)) >= ayarlar.GIRIS_DENEME_SINIRI:
            raise HTTPException(429, f"Çok fazla hatalı deneme yapıldı. {ayarlar.GIRIS_KILIT_DAKIKA} dakika sonra tekrar deneyin.")
    with baglan() as con:
        k = con.execute("SELECT * FROM kullanicilar WHERE eposta=?", (eposta,)).fetchone()
        tuz = bytes.fromhex(k["sifre_tuz"]) if k else b"bos-tuz-zamanlama-icin"
        tur = k["sifre_tur"] if k else SIFRE_TUR
        # Hesap yoksa da özet hesaplanır: cevap süresinden hesabın var olup olmadığı anlaşılmasın
        ozet = sifre_ozeti(istek.sifre[:200], tuz, tur)
        dogru = k is not None and hmac.compare_digest(ozet, k["sifre_ozet"])
        if not dogru:
            with _GIRIS_KILIDI:
                _hatali_denemeler(eposta).append(simdi())
            # Hangi bilginin yanlış olduğunu söylemiyoruz (hesap tahminini zorlaştırır)
            raise HTTPException(401, "E-posta veya şifre hatalı.")
        with _GIRIS_KILIDI:
            _HATALI_GIRIS.pop(eposta, None)
        if tur != SIFRE_TUR:  # eski özet: şifre doğru girildi, güçlü özetle yenile
            yeni_tuz = secrets.token_bytes(16)
            con.execute("UPDATE kullanicilar SET sifre_tuz=?, sifre_ozet=?, sifre_tur=? WHERE id=?",
                        (yeni_tuz.hex(), sifre_ozeti(istek.sifre[:200], yeni_tuz), SIFRE_TUR, k["id"]))
        return oturum_ac(con, k, response)


@app.post("/api/cikis")
def cikis(request: Request, response: Response):
    anahtar = request.cookies.get("oturum")
    if anahtar:
        with baglan() as con:
            con.execute("DELETE FROM oturumlar WHERE anahtar=?", (anahtar,))
            con.commit()
    response.delete_cookie("oturum")
    return {"tamam": True}


@app.get("/api/ben")
def ben(kullanici: dict = Depends(aktif_kullanici)):
    return kullanici


# ----------------------------------------------------------------- Birimler
@app.get("/api/birimler")
def birimler(kullanici: dict = Depends(aktif_kullanici)):
    """Öğrenci ve akademisyen sadece kendilerine hizmet veren birimleri görür.
    Personel, aktarma yapabilmek için tüm birimleri görür."""
    with baglan() as con:
        liste = [dict(r) for r in con.execute("SELECT * FROM birimler ORDER BY id")]
    if kullanici["rol"] != "personel":
        liste = [b for b in liste if hizmet_verir(b, kullanici["rol"])]
    return liste


# ----------------------------------------------------------------- Talepler
@app.get("/api/talepler")
def talep_listesi(kullanici: dict = Depends(aktif_kullanici)):
    """Rolüne göre: talep eden kendi taleplerini, personel kendi biriminin taleplerini görür."""
    with baglan() as con:
        if kullanici["rol"] == "personel":
            satirlar = con.execute(TALEP_SORGU + " WHERE t.birim_id=?", (kullanici["birim_id"],))
        else:
            satirlar = con.execute(TALEP_SORGU + " WHERE t.talep_eden_id=?", (kullanici["id"],))
        liste = [talep_ozet(r) for r in satirlar]
    if kullanici["rol"] == "personel":
        # Süresi aşanlar en üstte, sonra en uzun bekleyen
        liste.sort(key=lambda t: (t["durum"] == "Sonuçlandı", not t["suresi_asti"], t["birime_gelis"]))
    else:
        liste.sort(key=lambda t: t["guncelleme"], reverse=True)
    return liste


def goruldu(con, talep_id: int, kullanici: dict):
    """Talebe bakan taraf için "yeni gelişme" işaretini kaldırır."""
    sutun = "birim_gordu" if kullanici["rol"] == "personel" else "talep_eden_gordu"
    con.execute(f"UPDATE talepler SET {sutun}=(SELECT MAX(id) FROM olaylar WHERE talep_id=?) WHERE id=?",
                (talep_id, talep_id))


@app.get("/api/talepler/{talep_id}")
def talep_detay(talep_id: int, kullanici: dict = Depends(aktif_kullanici)):
    with baglan() as con:
        talebe_erisim(con, talep_id, kullanici)
        goruldu(con, talep_id, kullanici)
        return talep_detayi(con, talep_id)


def talep_sahibine_bildir(con, t: dict, ne_oldu: str):
    """Talep sahibine (isteğe bağlı) e-posta bildirimi gönderir."""
    if not bildirim.acik_mi():
        return
    k = con.execute("SELECT eposta FROM kullanicilar WHERE id=?", (t["talep_eden_id"],)).fetchone()
    if k and k["eposta"] not in TEST_EPOSTALAR:  # kurgusal test hesaplarına e-posta gitmez
        bildirim.talep_gelismesi(k["eposta"], t["no"], t["konu"], ne_oldu)


class YeniTalep(BaseModel):
    konu: str
    aciklama: str = ""
    birim_id: Optional[int] = None
    kategori: str = ""
    konum: str = ""


@app.post("/api/talepler")
def talep_ekle(istek: YeniTalep, kullanici: dict = Depends(rol_gerekli("ogrenci", "akademisyen"))):
    konu = istek.konu.strip()[:120]
    if len(konu) < 3:
        raise HTTPException(400, "Konu en az 3 karakter olmalı.")
    rol = kullanici["rol"]
    with baglan() as con:
        if istek.birim_id:
            birim = birim_getir(con, istek.birim_id)
            if not hizmet_verir(birim, rol):
                raise HTTPException(403, f"{birim['ad']} {ROL_ADI[rol].lower()} taleplerine bakmıyor.")
            birim_id, notu = birim["id"], f"Talep eden birimi kendisi seçti: {birim['ad']}"
        else:
            ad = asistan.yonlendir(f"{konu} {istek.aciklama}", rol)
            birim_id, notu = birim_id_bul(con, ad), f"Otomatik yönlendirme: {ad}"
        tid = talep_olustur(con, kullanici["id"], birim_id, konu, istek.aciklama.strip()[:2000], notu,
                            kategori=istek.kategori.strip()[:40], konum=istek.konum.strip()[:120])
        con.commit()
        return talep_detayi(con, tid)


class Mesaj(BaseModel):
    metin: str


@app.post("/api/talepler/{talep_id}/mesaj")
def mesaj_gonder(talep_id: int, istek: Mesaj, kullanici: dict = Depends(aktif_kullanici)):
    """Mesajın kimden geldiğini kullanıcı seçmez; rolünden anlaşılır."""
    metin = istek.metin.strip()[:2000]
    if not metin:
        raise HTTPException(400, "Mesaj boş olamaz.")
    with baglan() as con:
        t = talebe_erisim(con, talep_id, kullanici)
        if t["durum"] == "Sonuçlandı":
            raise HTTPException(400, "Sonuçlanmış talebe mesaj gönderilemez.")
        if kullanici["rol"] == "personel":
            olay_ekle(con, talep_id, "mesaj_birim", f"{t['birim']} mesaj gönderdi", metin, t["birim"])
            if t["durum"] == "Yeni":
                durum_degistir(con, talep_id, "İnceleniyor", t["birim"])
            talep_sahibine_bildir(con, t, f"{t['birim']} size bir mesaj gönderdi.")
        else:
            olay_ekle(con, talep_id, "mesaj_talep_eden", "Talep eden mesaj gönderdi", metin, t["talep_eden"])
            if t["durum"] == "Bilgi bekleniyor":
                durum_degistir(con, talep_id, "İnceleniyor", "Sistem")
        goruldu(con, talep_id, kullanici)
        con.commit()
        return talep_detayi(con, talep_id)


class Aktarma(BaseModel):
    birim_id: int
    gerekce: str


@app.post("/api/talepler/{talep_id}/aktar")
def aktar(talep_id: int, istek: Aktarma, kullanici: dict = Depends(rol_gerekli("personel"))):
    gerekce = istek.gerekce.strip()[:500]
    if len(gerekce) < 10:
        raise HTTPException(400, "Aktarma gerekçesi zorunludur (en az 10 karakter). Talep sahibi bu gerekçeyi görür.")
    with baglan() as con:
        t = talebe_erisim(con, talep_id, kullanici)
        if t["durum"] == "Sonuçlandı":
            raise HTTPException(400, "Sonuçlanmış talep aktarılamaz.")
        if istek.birim_id == t["birim_id"]:
            raise HTTPException(400, "Talep zaten bu birimde.")
        hedef = birim_getir(con, istek.birim_id)
        if not hizmet_verir(hedef, t["talep_eden_rol"]):
            raise HTTPException(400, f"{hedef['ad']} {t['talep_eden_rol_adi'].lower()} taleplerine bakmıyor.")
        talebi_aktar(con, talep_id, istek.birim_id, gerekce)
        talep_sahibine_bildir(con, t, f"Talebiniz {hedef['ad']} birimine aktarıldı. Gerekçe uygulamada görünür.")
        con.commit()
        return talep_detayi(con, talep_id)


class DurumIstek(BaseModel):
    durum: str


@app.post("/api/talepler/{talep_id}/durum")
def durum_guncelle(talep_id: int, istek: DurumIstek, kullanici: dict = Depends(rol_gerekli("personel"))):
    if istek.durum not in DURUMLAR:
        raise HTTPException(400, "Geçersiz durum.")
    with baglan() as con:
        t = talebe_erisim(con, talep_id, kullanici)
        if t["durum"] != istek.durum:
            durum_degistir(con, talep_id, istek.durum, t["birim"])
            goruldu(con, talep_id, kullanici)
            ne_oldu = ("Talebiniz sonuçlandı. Sonucu değerlendirebilir, çözülmediyse yeniden açabilirsiniz."
                       if istek.durum == "Sonuçlandı" else f"Talebinizin durumu: {istek.durum}")
            talep_sahibine_bildir(con, t, ne_oldu)
            con.commit()
        return talep_detayi(con, talep_id)


class Degerlendirme(BaseModel):
    puan: int
    yorum: str = ""


@app.post("/api/talepler/{talep_id}/degerlendir")
def degerlendir(talep_id: int, istek: Degerlendirme,
                kullanici: dict = Depends(rol_gerekli("ogrenci", "akademisyen"))):
    """Talep sahibi sonuçlanan talebini 1-5 puanla değerlendirir (bir kez). Bu, birimin
    memnuniyet istatistiğine girer: üniversitenin öğrenci işleri için ölçemediği veriyi üretir."""
    if not 1 <= istek.puan <= 5:
        raise HTTPException(400, "Puan 1 ile 5 arasında olmalı.")
    yorum = istek.yorum.strip()[:500]
    with baglan() as con:
        t = talebe_erisim(con, talep_id, kullanici)
        if t["durum"] != "Sonuçlandı":
            raise HTTPException(400, "Sadece sonuçlanan talepler değerlendirilebilir.")
        if t["puan"]:
            raise HTTPException(400, "Bu talebi zaten değerlendirdiniz.")
        con.execute("UPDATE talepler SET puan=?, degerlendirme=? WHERE id=?", (istek.puan, yorum, talep_id))
        olay_ekle(con, talep_id, "degerlendirme", f"Talep sahibi değerlendirdi: {istek.puan}/5", yorum,
                  kullanici["ad"])
        goruldu(con, talep_id, kullanici)
        return talep_detayi(con, talep_id)


class YenidenAc(BaseModel):
    gerekce: str


@app.post("/api/talepler/{talep_id}/yeniden-ac")
def yeniden_ac(talep_id: int, istek: YenidenAc,
               kullanici: dict = Depends(rol_gerekli("ogrenci", "akademisyen"))):
    """Sorun çözülmediyse talep sahibi, sonuçlanmadan sonraki YENIDEN_ACMA_GUN gün içinde talebi
    gerekçe yazarak yeniden açar. Talep aynı birime "Yeni" olarak döner, hedef süre baştan başlar."""
    gerekce = istek.gerekce.strip()[:500]
    if len(gerekce) < 10:
        raise HTTPException(400, "Neyin çözülmediğini kısaca yazın (en az 10 karakter). Birim bu gerekçeyi görür.")
    with baglan() as con:
        t = talebe_erisim(con, talep_id, kullanici)
        if t["durum"] != "Sonuçlandı":
            raise HTTPException(400, "Talep zaten açık.")
        if not t["yeniden_acilabilir"]:
            raise HTTPException(400, f"Sonuçlanmanın üzerinden {ayarlar.YENIDEN_ACMA_GUN} günden fazla geçti; "
                                     "lütfen yeni bir talep oluşturun.")
        z = simdi().isoformat()
        con.execute("UPDATE talepler SET durum='Yeni', birime_gelis=?, sonuclanma=NULL, puan=NULL, "
                    "degerlendirme='', birim_gordu=NULL WHERE id=?", (z, talep_id))
        olay_ekle(con, talep_id, "yeniden_acildi", "Talep sahibi talebi yeniden açtı", gerekce, kullanici["ad"])
        goruldu(con, talep_id, kullanici)
        return talep_detayi(con, talep_id)


@app.get("/api/istatistik")
def istatistik(kullanici: dict = Depends(rol_gerekli("personel"))):
    bugun = simdi().date().isoformat()
    with baglan() as con:
        talepler = [talep_ozet(r) for r in con.execute(
            TALEP_SORGU + " WHERE t.birim_id=?", (kullanici["birim_id"],))]
        asistan_bugun = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(1 - emin), 0) FROM asistan_sayaci WHERE zaman >= ?", (bugun,)
        ).fetchone()
        birim = dict(birim_getir(con, kullanici["birim_id"]))
        son30 = (simdi() - dt.timedelta(days=30)).isoformat()
        yeniden_acilan = con.execute(
            "SELECT COUNT(*) FROM olaylar o JOIN talepler t ON t.id = o.talep_id "
            "WHERE t.birim_id=? AND o.tur='yeniden_acildi' AND o.zaman >= ?",
            (kullanici["birim_id"], son30)).fetchone()[0]
    acik = [t for t in talepler if t["durum"] != "Sonuçlandı"]
    puanlar = [t["puan"] for t in talepler if t["puan"]]
    return {
        "birim": birim,
        "acik": len(acik),
        "suresi_asan": sum(t["suresi_asti"] for t in talepler),
        "bilgi_bekleyen": sum(t["durum"] == "Bilgi bekleniyor" for t in talepler),
        "ogrenci_talebi": sum(t["talep_eden_rol"] == "ogrenci" for t in acik),
        "akademisyen_talebi": sum(t["talep_eden_rol"] == "akademisyen" for t in acik),
        "asistan_bugun": asistan_bugun[0],
        "asistan_emin_degil": asistan_bugun[1],
        "yeni_hareket": sum(t["birimde_yeni"] for t in acik),
        "memnuniyet_ort": round(sum(puanlar) / len(puanlar), 1) if puanlar else None,
        "memnuniyet_sayi": len(puanlar),
        "yeniden_acilan_30g": yeniden_acilan,
    }


# ----------------------------------------------------------------- Asistan
class Soru(BaseModel):
    soru: str


@app.post("/api/asistan")
def asistana_sor(istek: Soru, kullanici: dict = Depends(rol_gerekli("ogrenci", "akademisyen"))):
    soru = istek.soru.strip()[:500]
    if len(soru) < 2:
        raise HTTPException(400, "Lütfen bir soru yazın.")
    cevap = asistan.cevapla(soru, kullanici["rol"])
    with baglan() as con:
        cevap["birim_id"] = birim_id_bul(con, cevap["birim"])
        con.execute("INSERT INTO asistan_sayaci (zaman, emin) VALUES (?, ?)",
                    (simdi().isoformat(), int(cevap["emin"])))
        con.commit()
    return cevap


@app.get("/api/asistan/durum")
def asistan_durumu():
    return asistan.DURUM


@app.post("/api/demo/sifirla")
def demo_sifirla(kullanici: dict = Depends(rol_gerekli("personel"))):
    """Sunum provalarından sonra örnek verilere geri dönmek için (oturumlar da silinir).
    Test hesaplarının şifreleri yine ortam değişkenlerinden okunur.
    Sadece DEMO_MODU açıkken çalışır; gerçek kullanımda (DEMO_MODU=false) veriler asla silinemez."""
    if not ayarlar.DEMO_MODU:
        raise HTTPException(403, "Demo modu kapalıyken veriler sıfırlanamaz.")
    log.warning("Demo verisi sıfırlandı (isteyen: %s).", kullanici["eposta"])
    kur(sifirla=True)
    return {"tamam": True}

