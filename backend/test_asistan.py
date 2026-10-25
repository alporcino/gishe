"""
Gishe asistanı için ölçüm (regresyon) testi. Yapay zekâ modeli GEREKMEZ: asistan "yedek modda" (model kapalıyken)
ne cevap veriyorsa o ölçülür. Bir değişiklikten sonra asistanın kötüleşip kötüleşmediğini gösterir.

Çalıştırma:
    docker compose exec backend python test_asistan.py          (özet)
    docker compose exec backend python test_asistan.py -v       (her soru tek tek)

Ölçülenler (soru_seti.py, yaklaşık 400 soru):
  - Doğru cevap: kaynak doğru madde mi, sohbet mesajına sohbet cevabı mı verildi?
  - YANLIŞ CEVAP: asistan emin olduğunu söyleyip YANLIŞ maddeyle cevap verdi mi? (En ağır hata: sıfır olmalı.)
  - Kaçırılan: asistan "emin değilim" dedi ama aslında cevabı vardı (güvenli hata; model açıkken çoğu cevaplanır).
  - Talep yönlendirmesi: "Yeni talep" formunda birim boş bırakılınca talep doğru birime gidiyor mu?

Test, yanlış cevap sayısı 0 ve doğruluk en az %90 ise geçer.
"""
import sys
import time

import asistan
import soru_seti

asistan.DURUM["hazir"] = False  # model olmadan ölç (yedek mod)

# Talep yönlendirmesi (asistan değil, "Yeni talep" formunda birim boş bırakılınca)
YONLENDIRME = [
    ("Yaz dönemi yurt başvurusu", "ogrenci", "Barınma Birimi"),
    ("Harç iadesi", "ogrenci", "Strateji Geliştirme"),
    ("Öğrenci e-postama giriş yapamıyorum", "ogrenci", "Bilgi İşlem"),
    ("İntibak işlemim yapılmadı", "ogrenci", "Fakülte Sekreterliği"),
    ("Staj defterimi nereye teslim edeceğim", "ogrenci", "Fakülte Sekreterliği"),
    ("Kayıt dondurma", "ogrenci", "Öğrenci İşleri"),
    ("Ofis kliması çalışmıyor", "akademisyen", "Yapı İşleri"),
    ("Kongre için görevlendirme", "akademisyen", "Personel Daire Başkanlığı"),
    ("MATLAB lisans yenileme", "akademisyen", "Bilgi İşlem"),
]


def degerlendir(r: dict, beklenen: str) -> str:
    """'dogru', 'yanlis' (emin ama yanlış) veya 'kacirdi' (emin değilim dedi)."""
    kaynaklar = r.get("kaynaklar") or []
    if beklenen == "SOHBET":
        return "dogru" if r["kip"] == "sohbet" else ("yanlis" if kaynaklar else "kacirdi")
    if beklenen == "YOK":
        return "dogru" if not r["emin"] and not kaynaklar and r["kip"] != "sohbet" else "yanlis"
    tur, alternatifler = beklenen.split(":", 1)
    alternatifler = [a.lower() for a in alternatifler.split("|")]
    if any(a in k.lower() for k in kaynaklar for a in alternatifler):
        return "dogru"
    if tur == "MY" and ((not r["emin"] and not kaynaklar) or r["kip"] == "secenek"):
        return "dogru"
    return "yanlis" if kaynaklar or r["kip"] == "sohbet" else "kacirdi"


def main() -> int:
    ayrinti = "-v" in sys.argv
    sayac = {"dogru": 0, "yanlis": 0, "kacirdi": 0}
    t0 = time.monotonic()
    for bolum in ("TEMEL", "EK", "TUZAK"):
        sorular = getattr(soru_seti, bolum)
        bolum_sayac = {"dogru": 0, "yanlis": 0, "kacirdi": 0}
        for soru, rol, beklenen in sorular:
            r = asistan.cevapla(soru, rol)
            sonuc = degerlendir(r, beklenen)
            bolum_sayac[sonuc] += 1
            if sonuc != "dogru" or ayrinti:
                etiket = {"dogru": "TAMAM ", "yanlis": "YANLIŞ", "kacirdi": "KAÇTI "}[sonuc]
                print(f"{etiket} [{rol[:3]}] {soru}")
                print(f"{'':10}-> {r['kip']} · {'; '.join(r.get('kaynaklar') or []) or '-'}   (beklenen {beklenen})")
        for k, v in bolum_sayac.items():
            sayac[k] += v
        print(f"{bolum:6}: {bolum_sayac['dogru']}/{len(sorular)} doğru, {bolum_sayac['yanlis']} yanlış, "
              f"{bolum_sayac['kacirdi']} kaçırılan")

    print("\nTalep yönlendirmesi")
    yon_hata = 0
    for metin, rol, birim in YONLENDIRME:
        cikan = asistan.yonlendir(metin, rol)
        if cikan != birim:
            yon_hata += 1
            print(f"HATA   {rol:12} {metin} -> {cikan} (beklenen {birim})")
    print(f"{len(YONLENDIRME) - yon_hata}/{len(YONLENDIRME)} doğru")

    toplam = sum(sayac.values())
    oran = sayac["dogru"] / toplam
    print(f"\nTOPLAM: {sayac['dogru']}/{toplam} doğru (%{100 * oran:.0f}) · YANLIŞ CEVAP: {sayac['yanlis']} · "
          f"kaçırılan: {sayac['kacirdi']} · {1000 * (time.monotonic() - t0) / toplam:.0f} ms/soru")
    gecti = sayac["yanlis"] == 0 and oran >= 0.90 and yon_hata == 0
    print("SONUÇ:", "GEÇTİ" if gecti else "KALDI")
    return 0 if gecti else 1


if __name__ == "__main__":
    sys.exit(main())
