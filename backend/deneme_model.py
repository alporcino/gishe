"""
Asistanı GERÇEK yapay zekâ modeliyle (Ollama + Qwen) dener ve sonuçları ekrana yazar.
test_asistan.py modeli kullanmaz; bu betik modelin cevaplarının kalitesini ve hızını görmek içindir.

Çalıştırma (docker compose up açıkken, ikinci bir komut penceresinde):
    docker compose exec backend python deneme_model.py            hazır cevap olmayan sorular (model yolu)
    docker compose exec backend python deneme_model.py --hepsi    hazır cevapları kapatıp her soruyu modele sor

Çıktının tamamını kopyalayıp paylaşırsanız modelin hangi sorularda zorlandığı görülür.
"""
import sys
import time

import asistan

# Hazır cevabı (sss.txt) OLMAYAN, cevabı yönetmeliklerde bulunan sorular: bunları model yazar
MODEL_SORULARI = [
    ("Staj komisyonu kimlerden oluşur?", "ogrenci"),
    ("Ders bilgi formu nedir?", "ogrenci"),
    ("Kesin kaydı vekaletle yaptırabilir miyim?", "ogrenci"),
    ("Seçmeli ders ile zorunlu ders arasındaki fark nedir?", "ogrenci"),
    ("Staj notu nasıl veriliyor?", "ogrenci"),
    ("Staj raporunu teslim etmezsem ne olur?", "ogrenci"),
    ("Sektör stajında başarısız olursam tekrar başvurabilir miyim?", "ogrenci"),
    ("Yatay geçiş sonuçları nerede ilan edilir?", "ogrenci"),
    ("Yatay geçişte yedek adaylar ne zaman çağrılır?", "ogrenci"),
    ("Yan dal programından iki dönem ders almazsam ne olur?", "ogrenci"),
    ("Yan dal öğrencisi mezun olunca katkı payını hangi programa öder?", "ogrenci"),
    ("Çift ana dal yapanlar ikinci dal için de staj yapmak zorunda mı?", "ogrenci"),
    ("Yaz okulunda başka üniversiteden ders almak için taban puan şartı var mı?", "ogrenci"),
    ("Hazırlık sınıfında iki yıl kalabilir miyim?", "ogrenci"),
    ("Burslar karşılıksız mı?", "ogrenci"),
    ("Yurttan ayrılırken odayı teslim etmezsem ne olur?", "ogrenci"),
    ("Kaydı silinen öğrenci harcını geri alabilir mi?", "ogrenci"),
    ("Eduroam'a bağlanmak için hangi şifreyi kullanırım?", "ogrenci"),
    ("Ders saatimi etkileyen bir arıza ne kadar sürede giderilir?", "akademisyen"),
    ("Islak imzalı hizmet belgesi kaç günde hazırlanır?", "akademisyen"),
    # Cevabı olmayan sorular: model "bilmiyorum" demeli, asistan uydurmamalı
    ("Yurtta misafir kalabilir mi?", "ogrenci"),
    ("Öğrenci belgesi nereden alınır?", "ogrenci"),
    ("Kampüste otopark ücretli mi?", "ogrenci"),
]

# --hepsi ile: sık sorulan soruların cevaplarını da model yazsın (hazır cevaplar kapalı)
HAZIR_CEVAPLI = [
    ("Yazın yurtta kalabilir miyim?", "ogrenci"),
    ("Kayıt dondurmak için ne gerekiyor?", "ogrenci"),
    ("Devamsızlık sınırı nedir?", "ogrenci"),
    ("Bütünleme sınavı var mı?", "ogrenci"),
    ("Hastaydım, sınava giremedim ne yapmalıyım?", "ogrenci"),
    ("Dersten kaldım, tekrar almak zorunda mıyım?", "ogrenci"),
    ("Bir dönemde en fazla kaç AKTS alabilirim?", "ogrenci"),
    ("Yatay geçiş için not ortalaması kaç olmalı?", "ogrenci"),
    ("Staj kaç iş günü?", "ogrenci"),
    ("Stajı online yapabilir miyim?", "ogrenci"),
    ("Bursum ne zaman kesilir?", "ogrenci"),
    ("Projeksiyon bozuk, ne yapmalıyım?", "akademisyen"),
]


def main():
    hepsi = "--hepsi" in sys.argv
    print(f"Model: {asistan.MODEL} · Ollama: {asistan.OLLAMA_URL}")
    print("Model hazırlanıyor (ilk seferde bir dakika sürebilir)…")
    asistan.modeli_hazirla()
    print(asistan.DURUM["mesaj"])
    if not asistan.DURUM["hazir"]:
        print("Model hazır değil; önce 'docker compose up' ile servislerin açık olduğundan emin olun.")
        return 1
    sorular = MODEL_SORULARI
    if hepsi:
        asistan.SSS = []  # hazır cevaplar kapalı: her şeyi model yazsın
        sorular = HAZIR_CEVAPLI + MODEL_SORULARI

    # Model ham cevaplarını da görmek için modele_sor sarmalanır
    asil = asistan.modele_sor
    son = {}

    def kayitli(soru, parcalar, rol="ogrenci"):
        son["ham"] = asil(soru, parcalar, rol)
        return son["ham"]
    asistan.modele_sor = kayitli

    toplam_sure = 0.0
    for soru, rol in sorular:
        son.clear()
        t0 = time.monotonic()
        r = asistan.cevapla(soru, rol)
        sure = time.monotonic() - t0
        toplam_sure += sure
        print("\n" + "=" * 90)
        print(f"SORU [{rol}]: {soru}")
        print(f"TÜR: {r['kip']} · emin={r['emin']} · {sure:.1f} sn")
        if "ham" in son and son["ham"].strip() != r["cevap"].strip():
            print(f"MODELİN HAM CEVABI: {son['ham']}")
        print(f"CEVAP: {r['cevap']}")
        print(f"KAYNAK: {'; '.join(r['kaynaklar']) or '-'}")
    print("\n" + "=" * 90)
    print(f"{len(sorular)} soru · ortalama {toplam_sure / len(sorular):.1f} sn/soru")
    return 0


if __name__ == "__main__":
    sys.exit(main())
