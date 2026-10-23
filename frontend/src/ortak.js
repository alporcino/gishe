// Gishe – öğrenci, akademisyen ve personel ekranlarının ortak yardımcı fonksiyonları

// Ön yüz arka uca SADECE API üzerinden bağlanır. Adres config.js'ten gelir (ortam değişkeni API_URL);
// boşsa aynı adres kullanılır ve nginx /api isteklerini arka uca iletir.
const API_TABAN = String((window.GISHE && window.GISHE.apiUrl) || "").replace(/\/$/, "");
const ZAMAN_ASIMI_MS = 150000; // yapay zekâ CPU'da çalıştığı için cevap biraz sürebilir

// Arka uca (API) istek gönderir. Hata olursa anlaşılır bir mesaj fırlatır.
async function api(yol, govde) {
  const denetci = new AbortController();
  const zamanlayici = setTimeout(() => denetci.abort(), ZAMAN_ASIMI_MS);
  const secenekler = { credentials: "include", signal: denetci.signal };
  if (govde !== undefined) {
    Object.assign(secenekler, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) });
  }
  let yanit;
  try {
    yanit = await fetch(API_TABAN + yol, secenekler);
  } catch (e) {
    throw new Error(e.name === "AbortError"
      ? "Sunucu zamanında cevap vermedi. Lütfen tekrar deneyin."
      : "Sunucuya ulaşılamadı. Uygulama çalışıyor mu?");
  } finally {
    clearTimeout(zamanlayici);
  }
  const veri = await yanit.json().catch(() => ({}));
  if (yanit.status === 401 && !yol.startsWith("/api/giris")) {
    // Oturum yok veya süresi doldu: giriş ekranına gönder
    location.href = "/giris.html";
    throw new Error(veri.detail || "Giriş yapmanız gerekiyor.");
  }
  if (!yanit.ok) {
    const detay = Array.isArray(veri.detail) ? "Gönderilen bilgiler eksik veya hatalı." : veri.detail;
    throw new Error(detay || "Bir hata oluştu.");
  }
  return veri;
}

// Kullanıcıdan gelen metni ekrana güvenle basmak için (XSS koruması)
function kacis(metin) {
  return String(metin ?? "").replace(/[&<>"']/g, (k) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[k]));
}

const AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
function tarihYaz(iso) {
  const d = new Date(iso);
  const s = String(d.getHours()).padStart(2, "0") + "." + String(d.getMinutes()).padStart(2, "0");
  return `${d.getDate()} ${AYLAR[d.getMonth()]} ${s}`;
}

function durumCipi(durum) {
  const sinif = { "Yeni": "yeni", "İnceleniyor": "inceleniyor", "Bilgi bekleniyor": "bilgi", "Sonuçlandı": "sonuc" }[durum] || "yeni";
  return `<span class="cip ${sinif}">${kacis(durum)}</span>`;
}

// "Bu birimde 2. gün · hedef 3 iş günü" bilgisini ve süre çubuğunu üretir
function sureBilgisi(t) {
  if (t.durum === "Sonuçlandı") return { metin: "Sonuçlandı", cubuk: "" };
  const oran = Math.min(100, Math.max(8, (t.gecen_gun / t.hedef_gun) * 100));
  const sinif = t.suresi_asti ? "asti" : (t.kalan_gun <= 1 ? "uyari" : "");
  let kalan;
  if (t.suresi_asti) kalan = `Hedef süre ${t.gecen_gun - t.hedef_gun} iş günü aşıldı`;
  else if (t.kalan_gun === 0) kalan = "Hedef süre bugün doluyor";
  else kalan = `${t.kalan_gun} iş günü kaldı`;
  return {
    metin: `Bu birimde ${t.gecen_gun + 1}. iş günü · hedef ${t.hedef_gun} iş günü`,
    kalan,
    sinif,
    cubuk: `<div class="cubuk ${sinif}" role="img" aria-label="${kacis(kalan)}"><span style="width:${oran}%"></span></div>`,
  };
}

// Talebin yolculuğunu (zaman çizelgesi) HTML olarak üretir
function yolculukCiz(t) {
  const olaylar = t.olaylar || [];
  const satirlar = olaylar.map((o, i) => {
    const son = i === olaylar.length - 1;
    const noktaSinif = son && t.durum !== "Sonuçlandı" ? "simdi" : (o.tur.startsWith("mesaj") ? "mesaj" : "");
    let ic = "";
    if (o.tur === "aktarildi") ic = `<div class="kutu gerekce"><strong>Aktarma gerekçesi:</strong> ${kacis(o.metin)}</div>`;
    else if (o.tur.startsWith("mesaj")) ic = `<div class="kutu">${kacis(o.metin)}</div>`;
    else if (o.metin) ic = `<span class="cok-kucuk soluk">${kacis(o.metin)}</span>`;
    return `<li>
      <div class="nokta-sutun"><span class="nokta ${noktaSinif}"></span>${son ? "" : '<span class="hat"></span>'}</div>
      <div class="govde">
        <span class="baslik">${kacis(o.baslik)}</span>
        ${ic}
        <span class="cok-kucuk soluk">${kacis(o.kimden)} · ${tarihYaz(o.zaman)}</span>
      </div>
    </li>`;
  }).join("");
  return `<ol class="yolculuk">${satirlar}</ol>`;
}

// Her rolün kendi ekranı var. Rol bilgisi SUNUCUDAN gelir; kullanıcı seçemez.
const ROL_SAYFASI = { ogrenci: "/", akademisyen: "/akademisyen.html", personel: "/personel.html" };

// Sayfa açılınca çağrılır: giriş yapılmamışsa giriş ekranına, yanlış sayfadaysa kendi ekranına yollar.
// Not: Asıl güvenlik bu kontrol değil, sunucudaki kontroldür. Bu sadece kullanıcıyı doğru ekrana taşır.
async function oturumKontrol(beklenenRol) {
  const ben = await api("/api/ben");
  if (ben.rol !== beklenenRol) {
    location.href = ROL_SAYFASI[ben.rol];
    throw new Error("Yönlendiriliyor…");
  }
  return ben;
}

async function cikisYap() {
  try { await api("/api/cikis", {}); } catch (e) { /* yine de çık */ }
  location.href = "/giris.html";
}
