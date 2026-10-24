"""
Gishe asistanı için ölçüm (regresyon) testi. Yapay zekâ modeli GEREKMEZ: arama, "emin miyim?" kararı
ve birim yönlendirmesi test edilir. Bir değişiklikten sonra asistanın kötüleşip kötüleşmediğini gösterir.

Çalıştırma:
    docker compose exec backend python test_asistan.py
    (ya da backend/ klasöründe:  python test_asistan.py)

Yeni soru eklemek için SORULAR listesine bir satır ekleyin:
    (soru, rol, beklenen: "emin" | "emin_degil", kaynakta geçmesi gereken metin veya None, beklenen birim veya None)
"""
import sys

import asistan

SORULAR = [
    # --- Öğrenci: yönetmelikte cevabı olanlar
    ("Yazın yurtta kalabilir miyim?", "ogrenci", "emin", "Yurt Yönergesi, Madde 4", "Barınma Birimi"),
    ("Kayıt dondurmak için ne gerekiyor?", "ogrenci", "emin", "Madde 19", "Öğrenci İşleri"),
    ("Kaydımı nasıl dondururum?", "ogrenci", "emin", "Madde 19", "Öğrenci İşleri"),
    ("Devamsızlık sınırı nedir?", "ogrenci", "emin", "Madde 23", "Öğrenci İşleri"),
    ("Dersten kalırsam ne olur?", "ogrenci", "emin", "Eğitim-Öğretim Yönetmeliği", "Öğrenci İşleri"),
    ("Yatay geçiş için not ortalaması kaç olmalı?", "ogrenci", "emin", "Yatay Geçiş", "Öğrenci İşleri"),
    ("Yan dal başvurusu için GNO şartı?", "ogrenci", "emin", "Yan Dal", "Öğrenci İşleri"),
    ("Staj kaç iş günü?", "ogrenci", "emin", "Staj", "Fakülte Sekreterliği"),
    ("Harç iadesi nasıl alınır?", "ogrenci", "emin", "İadesi", "Strateji Geliştirme"),
    ("Mezuniyet için kaç kredi lazım?", "ogrenci", "emin", "Eğitim-Öğretim Yönetmeliği", None),
    ("Azami öğrenim süresi kaç yıl?", "ogrenci", "emin", "Madde 14", "Öğrenci İşleri"),
    ("Yemek bursu nasıl alınır?", "ogrenci", "emin", "Yemek bursu", "Öğrenci İşleri"),
    ("Yurt ücreti ne zaman ödenir?", "ogrenci", "emin", "Yurt Yönergesi, Madde 6", "Barınma Birimi"),
    ("Erasmus ile gidersem derslerim sayılır mı?", "ogrenci", "emin", "Değişim", None),
    ("E-posta şifremi unuttum", "ogrenci", "emin", "e-posta şifresi", "Bilgi İşlem"),
    # --- Öğrenci: cevabı olmayanlar veya iki konuyu birleştirenler (uydurmamalı)
    ("Bursum kesilirse yurt ücreti değişir mi?", "ogrenci", "emin_degil", None, None),
    ("Futbol takımı var mı?", "ogrenci", "emin_degil", None, "Öğrenci İşleri"),
    ("Kantinde vegan yemek var mı?", "ogrenci", "emin_degil", None, None),
    # --- Akademisyen
    ("Projeksiyon bozuk ne yapmalıyım?", "akademisyen", "emin", "Teknik Hizmetler", "Yapı İşleri"),
    ("Kongre için görevlendirme ne zaman istenir?", "akademisyen", "emin", "görevlendirme", "Personel Daire Başkanlığı"),
    ("Yurt başvurusu nasıl yapılır?", "akademisyen", "emin_degil", None, None),
]

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


def karar(soru: str, rol: str) -> dict:
    """Model olmadan asistanın vereceği karar (yedek mod ile aynı mantık)."""
    sonuc = asistan.ara_puanli(soru, rol)
    if not sonuc or not sonuc[0]["guclu"]:
        return {"emin": False, "kaynak": None, "birim": asistan.yonlendir(soru, rol)}
    p = sonuc[0]["parca"]
    return {"emin": True, "kaynak": p["kaynak"], "birim": p["birim"]}


def main() -> int:
    hatalar = 0
    print(f"{'SONUÇ':<6} {'ROL':<12} SORU")
    for soru, rol, beklenen, kaynakta, birim in SORULAR:
        k = karar(soru, rol)
        sorunlar = []
        if k["emin"] != (beklenen == "emin"):
            sorunlar.append(f"beklenen {beklenen}, çıkan {'emin' if k['emin'] else 'emin_degil'}")
        if kaynakta and k["kaynak"] and kaynakta.lower() not in k["kaynak"].lower():
            sorunlar.append(f"kaynak '{k['kaynak']}' içinde '{kaynakta}' yok")
        if birim and k["birim"] != birim:
            sorunlar.append(f"birim {k['birim']} (beklenen {birim})")
        hatalar += bool(sorunlar)
        print(f"{'TAMAM' if not sorunlar else 'HATA':<6} {rol:<12} {soru}")
        print(f"{'':<19}-> {'emin' if k['emin'] else 'emin değil'} · {k['kaynak'] or '-'} · {k['birim']}")
        for s in sorunlar:
            print(f"{'':<19}!! {s}")

    print("\nTalep yönlendirmesi")
    for metin, rol, birim in YONLENDIRME:
        cikan = asistan.yonlendir(metin, rol)
        tamam = cikan == birim
        hatalar += not tamam
        print(f"{'TAMAM' if tamam else 'HATA':<6} {rol:<12} {metin} -> {cikan}" + ("" if tamam else f" (beklenen {birim})"))

    toplam = len(SORULAR) + len(YONLENDIRME)
    print(f"\n{toplam - hatalar}/{toplam} test geçti.")
    return 1 if hatalar else 0


if __name__ == "__main__":
    sys.exit(main())
