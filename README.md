# Gishe

**Talebin her an nerede olduğunu bilen kampüs.**
Öğrenci İşleri ve idari birimler için talep takip sistemi ve yerel yapay zekâ asistanı.

> 🎬 **Demo videosu:** [Uygulamanın Docker ile açılışı ve kullanımı (3 dk)](BURAYA-VIDEO-BAGLANTISI)
>
> ▶️ **Çalıştırma:** `docker compose up --build` → arayüz **http://localhost:3000**, API **http://localhost:8000**

---

## İçindekiler
1. [Problem](#problem)
2. [Çözüm](#çözüm)
3. [Çalıştırma](#çalıştırma)
4. [Mimari](#mimari)
5. [Yapay zekâ bileşeni](#yapay-zekâ-bileşeni)
6. [Ayarlar](#ayarlar)
7. [Güvenlik ve KVKK](#güvenlik-ve-kvkk)
8. [Proje yapısı](#proje-yapısı)
9. [Geliştiriciler](#geliştiriciler)
10. [Yapay zekâyı nasıl kullandık](#yapay-zekâyı-nasıl-kullandık)

---

## Problem

Bir öğrenci talebi (yurt başvurusu, belge, kayıt dondurma…) üniversitede birimden birime dolaşırken
**kimse talebin şu an kimde olduğunu bilmiyor.** Bunu dört sorun büyütüyor:

| Sorun | Ne oluyor? |
|---|---|
| Talep sahipsiz kalıyor | Birimler "bizde değil" deyince sorumluluğu kimse almıyor. |
| Süreç görünmüyor | Öğrenci talebinin nerede olduğunu, kaç gündür beklediğini göremiyor. |
| Birimlere ulaşılamıyor | Telefon açılmıyor; bilgi almanın tek yolu gişeye gitmek. |
| Personel bunalıyor | Aynı sorular her gün defalarca soruluyor; asıl işe zaman kalmıyor. |

Bu tablo kendi deneyimimizden (birimden birime gönderilen bir yaz yurdu başvurusu), arkadaşlarımızla
konuşmalarımızdan, GTÜ Öğrenci İşleri Daire Başkanlığı ile görüşmemizden ve üniversitelerin öğrenci
memnuniyeti verilerinden çıktı.

## Çözüm

Gishe üç söz verir: **her talebin bir sahibi var, her adım görünür, her soru bir cevap bulur.**

- **"Şu an kimde?"** Talep hangi birimde, kaç iş günüdür bekliyor, hedef süre ne; her an görünür.
- **Talebin yolculuğu:** Her adım zaman çizelgesinde görünür, kargo takibi gibi.
- **Gerekçeli aktarma:** Talep başka birime ancak gerekçe yazılarak aktarılır; talep sahibi gerekçeyi görür.
- **Otomatik yönlendirme:** Öğrenci birimi bilmek zorunda değil; sistem konuya göre doğru birimi seçer.
- **Hedef süre:** Her birimin hedef cevap süresi var; aşan talepler personel listesinde öne çıkar.
- **Yapay zekâ asistanı:** Yönetmelik ve sık sorulan sorulardan, **kaynak göstererek** cevap verir.
  Emin değilse **uydurmaz**, soruyu tek dokunuşla doğru birime talep olarak iletir.
- **Üç rol, üç ekran:** Öğrenci, akademisyen ve birim personeli. Rol **seçilemez**; hesaptan gelir
  ve her istekte sunucuda kontrol edilir.

## Çalıştırma

### Gerekenler
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows'ta WSL 2 ile). `docker run hello-world` çalışıyorsa hazırsınız.
- İnternet bağlantısı (sadece ilk derlemede) ve yaklaşık **20 GB boş disk**. GPU **gerekmez**.

### Tek komut

```bash
git clone https://github.com/KULLANICI-ADI/gishe.git
cd gishe
docker compose up --build
```

- İlk derleme internet hızına göre **20–60 dakika** sürebilir: Python, Node, nginx ve Ollama imajları
  (yaklaşık 4 GB) ile 2 GB'lık Qwen modeli indirilir. Model **derleme sırasında otomatik** iner;
  elle dosya kopyalamak gerekmez. Sonraki açılışlar saniyeler sürer.
- Hazır olunca:

| Ne | Adres |
|---|---|
| **Arayüz** | http://localhost:3000 |
| **API** | http://localhost:8000 |
| API belgeleri (Swagger) | http://localhost:8000/docs |
| Durum (health) | http://localhost:8000/health |

- `.env` dosyası **zorunlu değildir**; ayar değiştirmek isterseniz `.env.example` dosyasını `.env` adıyla kopyalayın.
- Durdurmak: `Ctrl + C` ya da `docker compose down`. Verileri de silmek: `docker compose down -v`.

### Demo hesapları
Giriş ekranındaki **Demo hesapları** listesinden bir hesaba tıklamak yeterlidir (şifresiz demo girişi).
Hesaplar ve kişiler örnektir, gerçek değildir.

| Rol | Örnek hesap | Ne görür? |
|---|---|---|
| Öğrenci | Ebru Y. (Mimarlık, 1. sınıf) | Kendi talepleri, "şu an kimde?", asistan |
| Akademisyen | Dr. Öğr. Üyesi Ayşe Demir | Arıza / bilgi işlem / personel işleri talepleri, asistan |
| Personel | Barınma Birimi, Öğrenci İşleri, Yapı İşleri… | Sadece kendi biriminin talepleri, yanıtlama, gerekçeli aktarma |

Gerçek kullanımda `.env` içinde `DEMO_MODU=false` yapılır; demo listesi ve şifresiz giriş kapanır.

### Kısa deneme senaryosu
1. **Ebru** ile girin → *Yaz dönemi yurt başvurusu* talebinde "Şu an kimde?" kartına ve aktarma gerekçesine bakın.
2. Asistana "Yazın yurtta kalabilir miyim?" diye sorun → kaynaklı cevap.
3. "Bursum kesilirse yurt ücreti değişir mi?" → asistan emin değilse **Personele ilet**.
4. Çıkış yapıp **Barınma Birimi Personeli** ile girin → talep listede. Gerekçe yazmadan aktarmayı deneyin: sistem izin vermez.

## Mimari

```
 Tarayıcı ──► frontend (nginx, :3000) ──/api──► backend (FastAPI, :8000) ──► ollama (Qwen, yerel)
                derlenmiş HTML/CSS/JS              iş mantığı, roller,          açık kaynak model,
                                                   RAG asistanı, /health        CPU'da çalışır
                                                        │
                                                        ▼
                                                 SQLite (kalıcı Docker birimi)
```

| Servis | Klasör | Görevi |
|---|---|---|
| `frontend` | `frontend/` | Arayüz. `npm run build` ile derlenir, derlenmiş hâli **nginx** ile sunulur (geliştirme sunucusu yok). Arka uca **sadece API** üzerinden bağlanır. |
| `backend` | `backend/` | FastAPI API'si: giriş, roller, talepler, aktarma, istatistik, asistan. Durumunu **`/health`** ile bildirir. |
| `ollama` | `ollama/` | Açık kaynak dil modeli (Qwen 2.5). Model imaj derlenirken indirilir. Dışarıya açık değildir. |

Arayüz API'ye iki yoldan ulaşabilir: varsayılan olarak aynı adresten (`/api`, nginx arka uca iletir)
ya da `.env` içinde `API_URL=http://localhost:8000` verilirse doğrudan (arka uç bu kaynağa CORS izni verir).

## Yapay zekâ bileşeni

**Konteyner içinde yerel çalışan açık kaynak bir dil modeliyle kurulmuş LLM özelliği.**

- **Model:** Qwen 2.5 (varsayılan `qwen2.5:3b`), Ollama ile, **tamamen yerelde ve CPU'da**.
  Daha hızlı cevap için `.env` içinde `MODEL=qwen2.5:1.5b` yapılabilir.
- **Harici yapay zekâ API'si yoktur.** Ürün hiçbir bulut servisine (Claude, OpenAI, Gemini…) istek atmaz.
- **Yöntem (RAG – "bul, sonra cevapla"):**
  1. `backend/yonetmelikler/` klasöründeki metinler maddelere (uzunsa fıkra gruplarına) bölünür.
  2. Soruya en ilgili maddeler bulunur. Seyrek kelimeler ("burs", "yatay") daha ağır sayılır, madde başlığında geçen
     kelimeler öne çıkar ve öğrencinin günlük dili yönetmelik diline köprülenir ("AKTS" → "kredi yükü",
     "Erasmus" → "değişim programı"). Kullanıcının rolüne uygun olmayan metinler aranmaz.
  3. Model, **sadece bu maddelere dayanarak** cevap vermeye zorlanır; cevabın altında kaynak gösterilir.
  4. İlgili madde yoksa ya da model emin değilse asistan "emin değilim" der ve doğru birime iletmeyi önerir.
- **Yedek mod:** Model henüz yüklenmediyse veya cevap gecikirse uygulama çökmez; asistan en ilgili yönetmelik
  maddesini doğrudan gösterir. Asistan ekranında modelin durumu yazar.
- **Hız:** CPU'da makul süre için bağlam ve cevap uzunluğu sınırlıdır (`MODEL_EN_FAZLA_TOKEN`).
  Model açılışta belleğe yüklenir, böylece ilk soruda beklenmez. Cevap beklerken ekranda yükleniyor göstergesi görünür.
- Görüntü işleme yapılmaz; **YOLO ailesinden hiçbir model kullanılmaz.**

> **Bilgi kaynağı (`backend/yonetmelikler/`):**
> - GTÜ'nün resmî metinlerinden dönüştürülenler: Ön Lisans ve Lisans Eğitim-Öğretim Yönetmeliği, Yatay Geçiş Yönergesi,
>   Yan Dal Programı Yönergesi, Mühendislik ve İşletme Fakültesi staj yönergeleri, GTÜ Vakfı burs bilgileri.
> - Demo için hazırlanmış **örnek** metinler (dosya adında `ornek` geçer): yurt, harç iadesi, bilgi işlem,
>   teknik hizmetler ve akademik personel işlemleri. Gerçek kullanımda üniversitenin metinleriyle değiştirilir.
> - Yeni bir metin eklemek için aynı biçimde `.txt` dosyası koyup `docker compose up --build` demek yeterlidir;
>   model değişmez, imaj boyutu sadece birkaç KB artar.

## Ayarlar

Tüm ayarlar ortam değişkenlerinden okunur; koda gömülü port, adres veya model yolu yoktur.
Örnek değerler: [`.env.example`](.env.example).

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `FRONTEND_PORT` | `3000` | Arayüzün bilgisayardaki portu |
| `API_PORT` | `8000` | API'nin bilgisayardaki portu |
| `MODEL` | `qwen2.5:3b` | Ollama modeli (değişirse `--build` gerekir) |
| `MODEL_ZAMAN_ASIMI` | `120` | Modelden cevap bekleme süresi (sn) |
| `MODEL_EN_FAZLA_TOKEN` | `220` | Cevap uzunluğu sınırı |
| `API_URL` | *(boş)* | Arayüzün API adresi; boşsa aynı adres + nginx |
| `CORS_KAYNAKLARI` | `http://localhost:3000,http://127.0.0.1:3000` | API'ye doğrudan erişebilecek adresler |
| `OTURUM_SAAT` | `12` | Oturum süresi |
| `GUVENLI_CEREZ` | `false` | HTTPS arkasında `true` |
| `DEMO_MODU` | `true` | Demo hesap listesi ve şifresiz demo girişi |
| `DEMO_SIFRE` | *(boş)* | Demo hesaplarının şifresi; boşsa rastgele üretilir |

## Güvenlik ve KVKK

- **Depoda şifre ve gizli bilgi yoktur.** Ayarlar `.env` dosyasındadır ve `.gitignore` ile dışarıda tutulur.
- Şifreler veritabanında düz değil, tuzlanıp özetlenerek (PBKDF2) saklanır. Oturum anahtarı JavaScript'in okuyamadığı bir çerezdedir.
- Rol tarayıcıdan değil veritabanından gelir; her istekte sunucuda kontrol edilir. Öğrenci "akademisyen gibi" talep açamaz.
- Her kullanıcı sadece kendi taleplerini, her personel sadece kendi biriminin taleplerini görür.
- Asistana sorulan **soru metni saklanmaz**; istatistik için sadece zaman ve "cevaplandı / cevaplanamadı" bilgisi tutulur.
- Yapay zekâ üniversitenin kendi sunucusunda çalışır; öğrenci verisi dış bir şirkete gönderilmez.
- Hatalı veya eksik girdi uygulamayı çökertmez; kullanıcıya anlaşılır bir Türkçe hata mesajı gösterilir.

## Proje yapısı

```
gishe/
├─ docker-compose.yml      Tüm servisleri tek komutla başlatır
├─ .env.example            Örnek ayarlar (gerçek .env depoya girmez)
├─ backend/                Arka uç (FastAPI)
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ main.py              API, roller, talepler, /health
│  ├─ ayarlar.py           Ortam değişkenlerinden ayar okuma
│  ├─ asistan.py           RAG asistanı (Ollama'ya bağlanır)
│  └─ yonetmelikler/       Asistanın bilgi kaynağı (örnek metinler)
├─ frontend/               Ön yüz
│  ├─ Dockerfile           Derleme (Node) + sunum (nginx)
│  ├─ package.json, build.mjs
│  ├─ nginx/               Sunucu ayarı ve açılış betiği
│  └─ src/                 HTML, CSS, JavaScript
├─ ollama/
│  └─ Dockerfile           Qwen modelini derleme sırasında imaja indirir
└─ docs/                   Ekran görüntüleri ve demo videosu
```

## Geliştiriciler

| | |
|---|---|
| **Yusuf Çelik** | Gebze Teknik Üniversitesi |
| **Alp Aslan** | Gebze Teknik Üniversitesi |

## Yapay zekâyı nasıl kullandık

<!-- TASLAK: Aşağıdaki maddeler gerçekte yaşadıklarımızdan derlendi. Teslimden önce kendi cümlelerinizle
     gözden geçirin, eksik kalan kendi düzeltmelerinizi ekleyin. Bu yorum satırı GitHub'da görünmez. -->

**Araç:** Claude (Anthropic). Ürünün içinde **değil**, sadece geliştirme aracı olarak kullanıldı.
Ürün hiçbir bulut yapay zekâ servisine bağlanmaz; içindeki model yerel Qwen'dir.

**Hangi işlerde kullandık?**
- **Problemi anlamak ve fikir eleme:** Türkiye'deki üniversite sorunlarını konuştuk, fikirleri artı/eksi yönleriyle tarttık,
  Öğrenci İşleri görüşmesi için soru listesi hazırlattık.
- **Planlama:** Kabul ettiğimiz fikirleri tablo hâline getirip aşamalara böldük.
- **Kod:** FastAPI arka ucu, rol kontrolü, RAG asistanı, arayüz ve Docker yapılandırması asistanla birlikte yazıldı;
  her parçayı çalıştırıp deneyerek ilerledik.
- **Hata ayıklama:** Windows'ta Docker'ın "Virtualization support not detected" hatasını asistanla adım adım çözdük (`wsl --install`).
- **Sunum ve tasarım:** Sunum, arayüz tasarım seçenekleri ve logo üzerinde birlikte çalıştık.

**Örnek istemler**
- "Hocaların talepleriyle öğrencilerin taleplerine ayrı birimler baksa ve farklı arayüzleri olsa?"
- "Bu sunumdaki 5. sayfanın altındaki veriler kafa karıştırıcı, daha anlaşılır yap."
- "Yarışmanın kuralları bunlar; yaptıklarımızı bunlara uyacak şekilde revize et ve yapacaklarımızı adım adım yaz."

**Kendimiz düzelttiklerimiz ve verdiğimiz kararlar**
- **Rol güvenliği:** İlk tasarımda kullanıcı rolünü kendisi seçebiliyordu. Öğrencilerin "hoca" etiketiyle talep açabileceğini
  biz fark ettik; rolün girişte hesaptan gelmesini ve sunucuda kontrol edilmesini istedik.
- **KVKK:** Önerilen kalıcı "Belgelerim" arşivinin kişisel veriyi gereksiz yere sakladığını fark ettik; yerine talebe bağlı,
  süreli ve silinebilir belge fikrine geçtik.
- **Fikir eleme:** Teknik olarak iddialı olan otonom yoklama fikrini, asıl kullanıcısının (hocaların) ihtiyacı olmadığı için askıya aldık.
  Gişe sırası fikrini de Öğrenci İşleri ile görüştükten sonra askıya aldık.
- **İçerik:** Sunumdaki kafa karıştırıcı verileri ve uygunsuz ifadeleri ayıklattık; ilk logonun Google logosuna benzediğini
  fark edip değiştirttik.
- **Asistanın zayıflığı:** Denemelerde asistanın soru biraz farklı sorulunca şaşırdığını gördük; bunu iyileştirme listemize aldık.

## Telif

© 2026 Yusuf Çelik, Alp Aslan. Tüm hakları saklıdır.
Bu depo yarışma değerlendirmesi için herkese açıktır; kod izinsiz kopyalanamaz, çoğaltılamaz ve dağıtılamaz.
