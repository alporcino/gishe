"""
Türkiye resmî tatilleri: hedef yanıt süresi (iş günü) hesabında bu günler sayılmaz.

- Sabit tatiller her yıl aynıdır (2429 sayılı Kanun).
- Dinî bayramlar her yıl değişir; aşağıdaki liste Diyanet takvimine göre girilmiştir.
  YENİ YIL EKLEMEK: DINI_BAYRAMLAR listesine o yılın Ramazan ve Kurban Bayramı günlerini ekleyin.
- Yarım günler (arifeler, 28 Ekim öğleden sonra) iş günü sayılır.
- Üniversitenin ek idari izin günleri .env içindeki EK_TATILLER ile verilir (ör. 2026-10-30,2027-05-20).
"""
import datetime as dt

import ayarlar

SABIT = [(1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29)]

DINI_BAYRAMLAR = [
    # 2025
    "2025-03-30", "2025-03-31", "2025-04-01",                # Ramazan Bayramı
    "2025-06-06", "2025-06-07", "2025-06-08", "2025-06-09",  # Kurban Bayramı
    # 2026
    "2026-03-20", "2026-03-21", "2026-03-22",
    "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30",
    # 2027
    "2027-03-09", "2027-03-10", "2027-03-11",
    "2027-05-16", "2027-05-17", "2027-05-18", "2027-05-19",
]

_DINI = {dt.date.fromisoformat(g) for g in DINI_BAYRAMLAR}
_EK = set()
for _g in ayarlar.EK_TATILLER:
    try:
        _EK.add(dt.date.fromisoformat(_g))
    except ValueError:
        pass  # hatalı tarih uygulamayı çökertmez; ayarlar.py zaten uyarı yazar


def tatil_mi(gun: dt.date) -> bool:
    return (gun.month, gun.day) in SABIT or gun in _DINI or gun in _EK


def is_gunu_mu(gun: dt.date) -> bool:
    return gun.weekday() < 5 and not tatil_mi(gun)
