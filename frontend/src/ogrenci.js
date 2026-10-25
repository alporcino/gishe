// Gishe – öğrenci uygulaması
// Ekranlar adres çubuğundaki # işaretine göre değişir:
//   #ana, #talepler, #talep/5, #asistan, #yeni

const durum = {
  ben: null,           // giriş yapan kullanıcı (bilgi sunucudan gelir)
  birimler: [],
  sohbet: [],          // asistan konuşması (sadece bu sekmede tutulur, sunucuya kaydedilmez)
  bekleyenSoru: null,  // ana ekrandan asistana gönderilen soru
  taslak: null,        // asistandan "talep oluştur"a taşınan bilgiler
  zamanlayici: null,
};

// Alt menüdeki "Taleplerim" sekmesinde, bakılmamış gelişme sayısı
function rozetGuncelle(talepler) {
  const sayi = talepler.filter((t) => t.yeni_gelisme).length;
  const a = document.querySelector('.alt-menu a[data-sekme="#talepler"]');
  if (!a) return;
  let r = a.querySelector(".menu-rozet");
  if (!sayi) { if (r) r.remove(); return; }
  if (!r) { r = document.createElement("span"); r.className = "menu-rozet"; a.appendChild(r); }
  r.textContent = sayi;
  r.setAttribute("aria-label", `${sayi} talepte yeni gelişme`);
}

const kok = document.getElementById("uygulama");

async function baslat() {
  try {
    durum.ben = await oturumKontrol("ogrenci");
    durum.birimler = await api("/api/birimler");
  } catch (e) {
    kok.innerHTML = `<div class="kart hata">${kacis(e.message)}</div>`;
    return;
  }
  window.addEventListener("hashchange", ciz);
  ciz();
  // Uygulama açıkken birimden gelen gelişmeler 30 saniyede bir rozete yansır
  setInterval(() => api("/api/talepler").then(rozetGuncelle).catch(() => {}), 30000);
}

async function ciz() {
  clearInterval(durum.zamanlayici);
  const h = location.hash || "#ana";
  document.querySelectorAll(".alt-menu a").forEach((a) => {
    const aktif = a.dataset.sekme === h || (h.startsWith("#talep/") && a.dataset.sekme === "#talepler");
    if (aktif) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  try {
    if (h.startsWith("#talep/")) await talepDetay(Number(h.split("/")[1]));
    else if (h === "#talepler") await talepListesi();
    else if (h === "#asistan") await asistanEkrani();
    else if (h === "#yeni") yeniTalepEkrani();
    else await anaEkran();
  } catch (e) {
    kok.innerHTML = `<div class="kart hata">${kacis(e.message)}</div>`;
  }
  window.scrollTo(0, 0);
}

// ---------------------------------------------------------------- Ana ekran
function talepKarti(t) {
  const s = sureBilgisi(t);
  return `<a class="kart talep-karti" href="#talep/${t.id}">
    <div class="ust-satir"><span class="mono soluk">#${kacis(t.no)}</span><span class="satir">${yeniCipi(t.yeni_gelisme)}${durumCipi(t.durum)}</span></div>
    <strong style="font-size:17px">${kacis(t.konu)}</strong>
    ${t.durum === "Sonuçlandı" ? (t.puan ? "" : '<span class="cok-kucuk" style="color:var(--turuncu-yazi);font-weight:700">Değerlendirmeni bekliyor</span>') : `
    <div class="konum">
      <strong class="kucuk">Şu an: ${kacis(t.birim)}</strong>
      <span class="cok-kucuk soluk">${kacis(s.metin)}</span>
    </div>
    ${s.cubuk}`}
  </a>`;
}

async function anaEkran() {
  const o = durum.ben;
  const talepler = await api("/api/talepler");
  rozetGuncelle(talepler);
  const acik = talepler.filter((t) => t.durum !== "Sonuçlandı");
  const yeniler = talepler.filter((t) => t.yeni_gelisme);
  const degerlendirilecek = talepler.filter((t) => t.durum === "Sonuçlandı" && !t.puan && t.yeniden_acilabilir);
  kok.innerHTML = `
    <div class="ust-satir">
      <div>
        <span class="kucuk soluk">${kacis(o.aciklama)}</span>
        <h1>Merhaba, ${kacis(o.ad.split(" ")[0])}</h1>
      </div>
      <button type="button" class="cikis" id="cikis">Çıkış</button>
    </div>

    <form id="sor-formu" class="alan">
      <label for="soru">Asistana sor</label>
      <div class="satir">
        <input id="soru" type="text" placeholder="Örn. yaz yurdu, öğrenci belgesi…" autocomplete="off">
        <button class="buton" type="submit">Sor</button>
      </div>
    </form>

    ${yeniler.length ? `<a class="bildirim-seridi" href="#talep/${yeniler[0].id}">
      <strong>${yeniler.length === 1 ? "Talebinde yeni gelişme var" : `${yeniler.length} talebinde yeni gelişme var`}</strong>
      <span>${kacis(yeniler[0].konu)}${yeniler.length > 1 ? " ve diğerleri" : ""} →</span></a>` : ""}

    <section style="display:flex;flex-direction:column;gap:10px">
      <h2>Açık taleplerin</h2>
      ${acik.length ? acik.map(talepKarti).join("") : '<div class="kart soluk">Şu an açık talebin yok.</div>'}
    </section>

    ${degerlendirilecek.length ? `<section style="display:flex;flex-direction:column;gap:10px">
      <h2>Sonuçlanan talebini değerlendir</h2>
      ${degerlendirilecek.map(talepKarti).join("")}
    </section>` : ""}

    <div class="izgara2">
      <a class="kisayol" href="#yeni"><strong>Talep oluştur</strong><span>Doğru birime kendisi gider</span></a>
      <a class="kisayol" href="#talepler"><strong>Tüm taleplerim</strong><span>${talepler.length} talep</span></a>
    </div>`;

  document.getElementById("cikis").addEventListener("click", cikisYap);
  document.getElementById("sor-formu").addEventListener("submit", (e) => {
    e.preventDefault();
    const soru = document.getElementById("soru").value.trim();
    if (!soru) return;
    durum.bekleyenSoru = soru;
    location.hash = "#asistan";
  });
}

// ---------------------------------------------------------------- Taleplerim
async function talepListesi() {
  const talepler = await api("/api/talepler");
  kok.innerHTML = `
    <h1>Taleplerim</h1>
    ${talepler.length ? talepler.map(talepKarti).join("") : '<div class="kart soluk">Henüz talebin yok.</div>'}
    <a class="buton" href="#yeni">Yeni talep oluştur</a>`;
}

// ---------------------------------------------------------------- Talep ayrıntısı
async function talepDetay(id) {
  clearInterval(durum.zamanlayici);
  const t = await api(`/api/talepler/${id}`);
  if (location.hash !== `#talep/${id}`) return; // kullanıcı bu arada başka ekrana geçtiyse
  const s = sureBilgisi(t);
  api("/api/talepler").then(rozetGuncelle).catch(() => {}); // talep görüldü: rozeti güncelle
  kok.innerHTML = `
    <div class="geri-satir"><a class="geri" href="#talepler" aria-label="Geri">←</a><strong>Talep ayrıntısı</strong></div>

    <div style="display:flex;flex-direction:column;gap:6px">
      <div class="satir"><span class="mono soluk">#${kacis(t.no)}</span>${durumCipi(t.durum)}</div>
      <h1 style="font-size:22px">${kacis(t.konu)}</h1>
      <span class="kucuk soluk">Oluşturuldu: ${tarihYaz(t.olusturma)}</span>
    </div>

    ${t.durum === "Sonuçlandı" ? `
    <div class="kart" style="background:var(--yesil-acik);border-color:#BFE3CB">
      <strong style="color:var(--yesil)">Talebin sonuçlandı</strong>
      <span class="kucuk">Son işlemi yapan birim: ${kacis(t.birim)}</span>
    </div>` : `
    <div class="kart">
      <span class="cok-kucuk soluk" style="font-weight:800;letter-spacing:.04em">ŞU AN KİMDE?</span>
      <div style="display:flex;flex-direction:column;gap:2px">
        <strong style="font-size:16px">${kacis(t.birim)}</strong>
        <span class="kucuk soluk">${kacis(t.daire)}</span>
      </div>
      ${s.cubuk}
      <div class="ust-satir cok-kucuk">
        <span class="soluk">${kacis(s.metin)}</span>
        <strong style="color:${t.suresi_asti ? "var(--kirmizi)" : "var(--turuncu-yazi)"}">${kacis(s.kalan)}</strong>
      </div>
    </div>`}

    ${kapanisBolumu(t)}

    ${t.aciklama ? `<div class="kart"><span class="etiket">Açıklaman</span><span style="white-space:pre-line">${kacis(t.aciklama)}</span></div>` : ""}

    <section style="display:flex;flex-direction:column;gap:10px">
      <h2 style="font-size:16px">Talebin yolculuğu</h2>
      ${yolculukCiz(t)}
    </section>

    ${t.durum === "Sonuçlandı" ? "" : `
    <form id="mesaj-formu" class="kart">
      <label class="etiket" for="mesaj">Birime mesaj yaz</label>
      <textarea id="mesaj" placeholder="Örn. İstenen belgeyi teslim ettim."></textarea>
      <span id="mesaj-hata" class="hata" role="alert"></span>
      <button class="buton" type="submit">Gönder</button>
    </form>`}`;

  kapanisBagla(t, () => talepDetay(id));
  const form = document.getElementById("mesaj-formu");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const alan = document.getElementById("mesaj");
      const hata = document.getElementById("mesaj-hata");
      if (!alan.value.trim()) { hata.textContent = "Önce bir mesaj yaz."; return; }
      try {
        await api(`/api/talepler/${id}/mesaj`, { metin: alan.value });
        ciz();
      } catch (err) { hata.textContent = err.message; }
    });
  }
  // Personel bir işlem yaparsa ekran kendiliğinden güncellensin (yazı yazılmıyorsa)
  durum.zamanlayici = setInterval(() => {
    const yaziliyor = ["mesaj", "yorum", "yeniden-gerekce"].some((x) => {
      const alan = document.getElementById(x);
      return alan && (alan.value || document.activeElement === alan);
    });
    const puanSecildi = document.querySelector(".puan-secici .dolu");
    if (!yaziliyor && !puanSecildi) talepDetay(id).catch(() => {});
  }, 10000);
}

// ---------------------------------------------------------------- Asistan
async function asistanEkrani() {
  let modelDurumu = { mesaj: "" };
  try { modelDurumu = await api("/api/asistan/durum"); } catch (e) { /* önemsiz */ }
  kok.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:2px">
      <h1>Asistan</h1>
      <span class="kucuk soluk">Yönetmeliklerden yanıt verir. Emin olmadığında personele iletir.</span>
      <span class="cok-kucuk soluk">${kacis(modelDurumu.mesaj)}</span>
    </div>
    <div id="sohbet" class="sohbet"></div>
    <div class="oneriler" id="oneriler">
      <button class="oneri" type="button">Yazın yurtta kalabilir miyim?</button>
      <button class="oneri" type="button">Kayıt dondurmak için ne gerekiyor?</button>
      <button class="oneri" type="button">Bursum kesilirse yurt ücreti değişir mi?</button>
    </div>
    <form id="asistan-formu" class="satir">
      <label for="asistan-soru" class="gizli-etiket">Sorun</label>
      <input id="asistan-soru" type="text" placeholder="Bir şey sor…" autocomplete="off">
      <button class="buton" type="submit">Gönder</button>
    </form>`;

  sohbetiCiz();
  document.getElementById("asistan-formu").addEventListener("submit", (e) => {
    e.preventDefault();
    const alan = document.getElementById("asistan-soru");
    sor(alan.value);
    alan.value = "";
  });
  document.getElementById("oneriler").addEventListener("click", (e) => {
    if (e.target.matches(".oneri")) sor(e.target.textContent);
  });
  document.getElementById("sohbet").addEventListener("click", sohbetButonu);

  if (durum.bekleyenSoru) {
    const soru = durum.bekleyenSoru;
    durum.bekleyenSoru = null;
    sor(soru);
  }
}

function sohbetiCiz() {
  const kutu = document.getElementById("sohbet");
  if (!kutu) return;
  kutu.innerHTML = durum.sohbet.map((m, i) => {
    if (m.kim === "ben") return `<div class="balon ben">${kacis(m.metin)}</div>`;
    if (m.bekliyor) return `<div class="balon asistan"><span class="dusunuyor">Asistan düşünüyor</span><span class="cok-kucuk soluk">Yapay zekâ bilgisayarında çalıştığı için birkaç saniye sürebilir.</span></div>`;
    if (m.hata) return `<div class="balon asistan emin-degil"><span class="hata">${kacis(m.hata)}</span></div>`;
    const c = m.cevap;
    const butonlar = c.emin
      ? `<button class="buton" data-islem="talep" data-i="${i}" type="button">Talep oluştur</button>`
      : `<button class="buton" data-islem="ilet" data-i="${i}" type="button">Personele ilet (${kacis(c.birim)})</button>
         <button class="buton ikincil" data-islem="vazgec" data-i="${i}" type="button">Vazgeç</button>`;
    return `<div class="balon asistan ${c.emin ? "" : "emin-degil"}">
      ${c.emin ? "" : `<span class="cok-kucuk" style="color:var(--turuncu-yazi);font-weight:800">${c.kip === "yapay_zeka" ? "Kısmen emin: yönetmelik sorunun tamamını karşılamıyor" : "Emin değilim"}</span>`}
      <span>${kacis(c.cevap)}</span>
      ${kaynaklarCiz(c)}
      ${c.kip === "yedek" ? '<span class="cok-kucuk soluk">Yapay zekâ hazır olmadığı için ilgili madde doğrudan gösterildi.</span>' : ""}
      ${c.kip === "madde" ? '<span class="cok-kucuk soluk">Sorunu karşılayan madde aynen gösterildi.</span>' : ""}
      ${m.kapandi ? "" : `<div class="butonlar">${butonlar}</div>`}
    </div>`;
  }).join("");
  kutu.lastElementChild?.scrollIntoView({ block: "nearest" });
}

async function sor(soru) {
  soru = (soru || "").trim();
  if (!soru) return;
  const kayit = { kim: "asistan", bekliyor: true, soru };
  durum.sohbet.push({ kim: "ben", metin: soru }, kayit);
  sohbetiCiz();
  try {
    kayit.cevap = await api("/api/asistan", { soru });
  } catch (e) {
    kayit.hata = e.message;
  }
  kayit.bekliyor = false;
  sohbetiCiz();
}

async function sohbetButonu(e) {
  const buton = e.target.closest("button[data-islem]");
  if (!buton) return;
  const m = durum.sohbet[Number(buton.dataset.i)];
  if (buton.dataset.islem === "vazgec") { m.kapandi = true; sohbetiCiz(); return; }
  if (buton.dataset.islem === "talep") {
    durum.taslak = { konu: m.soru, birim_id: m.cevap.birim_id };
    location.hash = "#yeni";
    return;
  }
  // "İlgili birime ilet": soruyu doğrudan talebe çevir
  buton.disabled = true;
  try {
    const t = await api("/api/talepler", {
      konu: m.soru.slice(0, 120),
      aciklama: "Asistan bu soruyu yönetmeliklerde yanıtlayamadı; öğrenci personele iletti.\n\nSoru: " + m.soru,
      birim_id: m.cevap.birim_id,
    });
    m.kapandi = true;
    location.hash = `#talep/${t.id}`;
  } catch (err) {
    buton.disabled = false;
    alert(err.message);
  }
}

// ---------------------------------------------------------------- Yeni talep
function yeniTalepEkrani() {
  const t = durum.taslak || {};
  durum.taslak = null;
  kok.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:4px">
      <h1>Yeni talep</h1>
      <span class="kucuk soluk">Birimi bilmiyorsan boş bırak; sistem konuna göre doğru birime yönlendirir.</span>
    </div>
    <form id="talep-formu" class="kart">
      <div class="alan">
        <label for="konu">Konu</label>
        <input id="konu" type="text" maxlength="120" value="${kacis(t.konu || "")}" placeholder="Örn. Kayıt dondurma">
      </div>
      <div class="alan">
        <label for="aciklama">Açıklama</label>
        <textarea id="aciklama" placeholder="Durumunu kısaca anlat."></textarea>
      </div>
      <div class="alan">
        <label for="birim">Birim</label>
        <select id="birim">
          <option value="">Sistem seçsin (önerilen)</option>
          ${durum.birimler.map((b) => `<option value="${b.id}" ${b.id === t.birim_id ? "selected" : ""}>${kacis(b.ad)}</option>`).join("")}
        </select>
      </div>
      <span id="talep-hata" class="hata" role="alert"></span>
      <button class="buton" type="submit">Talebi gönder</button>
    </form>`;

  document.getElementById("talep-formu").addEventListener("submit", async (e) => {
    e.preventDefault();
    const hata = document.getElementById("talep-hata");
    const konu = document.getElementById("konu").value.trim();
    if (konu.length < 3) { hata.textContent = "Konu en az 3 karakter olmalı."; return; }
    const birim = document.getElementById("birim").value;
    e.submitter && (e.submitter.disabled = true);
    try {
      const yeni = await api("/api/talepler", {
        konu,
        aciklama: document.getElementById("aciklama").value,
        birim_id: birim ? Number(birim) : null,
      });
      location.hash = `#talep/${yeni.id}`;
    } catch (err) {
      hata.textContent = err.message;
      e.submitter && (e.submitter.disabled = false);
    }
  });
}

baslat();
