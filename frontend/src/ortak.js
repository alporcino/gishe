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

// İşlem sonrası kısa onay mesajı (ekranın altında belirir, kendiliğinden kaybolur).
// Ekran okuyucular da duyar (aria-live). tur: "basari" ya da "hata"
function bildir(metin, tur = "basari") {
  let kutu = document.getElementById("bildirimler");
  if (!kutu) {
    kutu = document.createElement("div");
    kutu.id = "bildirimler";
    kutu.className = "bildirimler";
    kutu.setAttribute("role", "status");
    kutu.setAttribute("aria-live", "polite");
    document.body.appendChild(kutu);
  }
  const el = document.createElement("div");
  el.className = `bildirim ${tur}`;
  el.textContent = metin;
  kutu.appendChild(el);
  setTimeout(() => {
    el.classList.add("gidiyor");
    setTimeout(() => el.remove(), 300);
  }, tur === "hata" ? 5000 : 3200);
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
    else if (o.tur === "yeniden_acildi") ic = `<div class="kutu gerekce"><strong>Neden yeniden açıldı:</strong> ${kacis(o.metin)}</div>`;
    else if (o.tur === "degerlendirme") ic = o.metin ? `<div class="kutu">${kacis(o.metin)}</div>` : "";
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

// Asistan cevabının altındaki kaynak bilgisi. Model birden fazla maddeye dayanabilir; hepsi gösterilir.
// "İlgili" maddeler cevap değildir: asistan emin olmadığında göz atılabilecek maddelerdir.
function kaynaklarCiz(c) {
  const kaynaklar = c.kaynaklar || (c.kaynak ? [c.kaynak] : []);
  let html = "";
  if (kaynaklar.length) {
    html += `<div class="kaynaklar"><span class="cok-kucuk soluk">${kaynaklar.length > 1 ? "Kaynaklar" : "Kaynak"}</span>
      ${kaynaklar.map((k) => `<span class="cip yeni kaynak">${kacis(k)}</span>`).join("")}</div>`;
  }
  if (c.ilgili && c.ilgili.length) {
    html += `<div class="kaynaklar"><span class="cok-kucuk soluk">Soruyu tam karşılamayan ama ilgili olabilecek maddeler</span>
      ${c.ilgili.map((k) => `<span class="cip bilgi kaynak">${kacis(k)}</span>`).join("")}</div>`;
  }
  return html;
}

// Asistanın yüzü: GTÜ maskotu Pupa. Asistanın her cevabı Pupa'nın görseliyle birlikte gösterilir.
const ASISTAN_ADI = "Pupa";
function pupaGorseli(buyuk = false) {
  const b = buyuk ? 56 : 36;
  return `<img class="pupa${buyuk ? " buyuk" : ""}" src="pupa.png" alt="" width="${b}" height="${b}" onerror="this.remove()">`;
}
function asistanBalonu(ic, sinif = "", stil = "") {
  return `<div class="asistan-satir" aria-label="${ASISTAN_ADI}">${pupaGorseli()}<div class="balon asistan ${sinif}"${stil ? ` style="${stil}"` : ""}>${ic}</div></div>`;
}

// "Yeni gelişme" çipi: karşı taraf talepte bir şey yaptı ve kullanıcı henüz bakmadı
function yeniCipi(goster, metin = "Yeni gelişme") {
  return goster ? `<span class="cip yeni-gelisme">${kacis(metin)}</span>` : "";
}

function yildizlar(puan) {
  return `<span class="yildizlar" aria-label="${puan} / 5">${"★".repeat(puan)}<span class="soluk">${"★".repeat(5 - puan)}</span></span>`;
}

// Sonuçlanan talebin altında: değerlendirme (1-5) ve "çözülmedi, yeniden aç".
// Öğrenci ve akademisyen ekranları ortak kullanır. sonra(): işlem bitince ekranı yenileyen fonksiyon.
function kapanisBolumu(t) {
  if (t.durum !== "Sonuçlandı") return "";
  const degerlendirme = t.puan
    ? `<div class="kart degerlendirildi">
        <span class="etiket">Değerlendirmen</span>
        <div>${yildizlar(t.puan)}</div>
        ${t.degerlendirme ? `<span class="kucuk" style="white-space:pre-line">${kacis(t.degerlendirme)}</span>` : ""}
      </div>`
    : `<form class="kart" id="degerlendir-formu">
        <span class="etiket" id="puan-etiket">Sonuçtan memnun kaldın mı?</span>
        <div class="puan-secici" role="radiogroup" aria-labelledby="puan-etiket">
          ${[1, 2, 3, 4, 5].map((p) => `<button type="button" role="radio" aria-checked="false" data-puan="${p}" aria-label="${p} yıldız">★</button>`).join("")}
        </div>
        <label class="gizli-etiket" for="yorum">Yorum</label>
        <textarea id="yorum" maxlength="500" placeholder="İstersen kısa bir yorum yaz (isteğe bağlı)"></textarea>
        <span class="hata" id="degerlendir-hata" role="alert"></span>
        <button class="buton" type="submit" style="align-self:flex-start">Değerlendir</button>
        <span class="cok-kucuk soluk">Puanın birimin hizmet kalitesini ölçmek için kullanılır.</span>
      </form>`;
  const yenidenAc = t.yeniden_acilabilir
    ? `<details class="kart yeniden-ac">
        <summary class="etiket">Sorun çözülmedi mi? Talebi yeniden aç</summary>
        <form id="yeniden-ac-formu" class="alan" style="margin-top:8px">
          <label for="yeniden-gerekce">Neyin çözülmediğini yaz (birim bunu görür)</label>
          <textarea id="yeniden-gerekce" maxlength="500" placeholder="Örn. Belge teslim edildi ama üzerindeki bilgi hatalı."></textarea>
          <span class="hata" id="yeniden-hata" role="alert"></span>
          <button class="buton ikincil" type="submit" style="align-self:flex-start">Yeniden aç</button>
        </form>
      </details>`
    : "";
  return degerlendirme + yenidenAc;
}

function kapanisBagla(t, sonra) {
  const form = document.getElementById("degerlendir-formu");
  if (form) {
    let puan = 0;
    const butonlar = form.querySelectorAll("[data-puan]");
    form.querySelector(".puan-secici").addEventListener("click", (e) => {
      const b = e.target.closest("[data-puan]");
      if (!b) return;
      puan = Number(b.dataset.puan);
      document.getElementById("degerlendir-hata").textContent = "";
      butonlar.forEach((x) => {
        x.setAttribute("aria-checked", String(Number(x.dataset.puan) === puan));
        x.classList.toggle("dolu", Number(x.dataset.puan) <= puan);
      });
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const hata = document.getElementById("degerlendir-hata");
      if (!puan) { hata.textContent = "Önce 1-5 arası bir puan seç."; return; }
      try {
        await api(`/api/talepler/${t.id}/degerlendir`, { puan, yorum: document.getElementById("yorum").value });
        bildir("Değerlendirmen kaydedildi. Teşekkürler!");
        sonra();
      } catch (err) { hata.textContent = err.message; }
    });
  }
  const ac = document.getElementById("yeniden-ac-formu");
  if (ac) {
    ac.addEventListener("submit", async (e) => {
      e.preventDefault();
      const hata = document.getElementById("yeniden-hata");
      const gerekce = document.getElementById("yeniden-gerekce").value.trim();
      if (gerekce.length < 10) { hata.textContent = "Neyin çözülmediğini kısaca yaz (en az 10 karakter)."; return; }
      try {
        await api(`/api/talepler/${t.id}/yeniden-ac`, { gerekce });
        bildir("Talep yeniden açıldı. Birim gerekçeni görecek.");
        sonra();
      } catch (err) { hata.textContent = err.message; }
    });
  }
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
