// Gishe – akademisyen ekranı
// Hızlı talep formu (kategori seçince doğru birime gider), taleplerim listesi ve talep ayrıntısı.
const a = {
  ben: null,
  birimler: [],
  kategori: "Teknik arıza",
  birimAdi: "Yapı İşleri",
  seciliId: null,
};

async function baslat() {
  try {
    a.ben = await oturumKontrol("akademisyen");
    a.birimler = await api("/api/birimler");
  } catch (e) {
    document.getElementById("talepler").innerHTML = `<span class="hata">${kacis(e.message)}</span>`;
    return;
  }
  document.getElementById("kullanici-ad").textContent = a.ben.ad;
  document.getElementById("selam").textContent = `Merhaba, ${a.ben.ad}`;
  document.getElementById("cikis").addEventListener("click", cikisYap);

  document.getElementById("kategoriler").addEventListener("click", (e) => {
    const b = e.target.closest("button.kategori");
    if (!b) return;
    a.kategori = b.dataset.kategori;
    a.birimAdi = b.dataset.birim;
    document.querySelectorAll(".kategori").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    kategoriGuncelle();
  });
  kategoriGuncelle();

  document.getElementById("talep-formu").addEventListener("submit", talepGonder);
  document.getElementById("sor-formu").addEventListener("submit", asistanaSor);
  document.getElementById("talepler").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-id]");
    if (b) detayAc(Number(b.dataset.id));
  });

  await listeCiz();
  setInterval(() => {
    listeCiz();
    const yaziliyor = ["mesaj", "yorum", "yeniden-gerekce"].some((x) => {
      const alan = document.getElementById(x);
      return alan && (alan.value || document.activeElement === alan);
    }) || document.querySelector(".puan-secici .dolu");
    if (a.seciliId && !yaziliyor) detayAc(a.seciliId, false);
  }, 10000);
}

function kategoriGuncelle() {
  const birim = a.birimler.find((b) => b.ad === a.birimAdi);
  document.getElementById("konum-alani").hidden = !["Teknik arıza", "Bilgi işlem"].includes(a.kategori);
  document.getElementById("hedef-bilgi").textContent = birim
    ? `Bu talep doğrudan ${birim.ad} birimine gider · hedef yanıt süresi ${birim.hedef_gun} iş günü`
    : "";
}

async function talepGonder(e) {
  e.preventDefault();
  const hata = document.getElementById("talep-hata");
  hata.textContent = "";
  const konu = document.getElementById("konu").value.trim();
  if (konu.length < 3) { hata.textContent = "Konu en az 3 karakter olmalı."; return; }
  const konumAlani = !document.getElementById("konum-alani").hidden;
  const konum = konumAlani ? document.getElementById("konum").value.trim() : "";
  if (a.kategori === "Teknik arıza" && !konum) { hata.textContent = "Teknik arızalarda bina ve oda bilgisi gerekli."; return; }
  const birim = a.birimler.find((b) => b.ad === a.birimAdi);
  const buton = e.submitter;
  if (buton) buton.disabled = true;
  try {
    const t = await api("/api/talepler", {
      konu,
      aciklama: document.getElementById("aciklama").value,
      konum,
      kategori: a.kategori,
      birim_id: birim ? birim.id : null,
    });
    e.target.reset();
    bildir(t.birim ? `Talebiniz oluşturuldu ve ${t.birim} birimine gitti.` : "Talebiniz oluşturuldu.");
    await listeCiz();
    detayAc(t.id);
  } catch (err) {
    hata.textContent = err.message;
  } finally {
    if (buton) buton.disabled = false;
  }
}

async function listeCiz() {
  const kutu = document.getElementById("talepler");
  let talepler;
  try { talepler = await api("/api/talepler"); } catch (e) { kutu.innerHTML = `<span class="hata">${kacis(e.message)}</span>`; return; }
  if (!talepler.length) { kutu.innerHTML = '<span class="soluk">Henüz talebiniz yok.</span>'; return; }
  kutu.innerHTML = talepler.map((t) => {
    const s = sureBilgisi(t);
    return `<div class="talep-satiri">
      <button type="button" data-id="${t.id}">
        <strong>${kacis(t.konu)}</strong>
        <span class="cok-kucuk soluk">#${kacis(t.no)} · ${t.durum === "Sonuçlandı" ? (t.puan ? "Sonuçlandı" : "Sonuçlandı · değerlendirmenizi bekliyor") : "Şu an: " + kacis(t.birim)}</span>
        ${t.durum === "Sonuçlandı" ? "" : `<span class="cok-kucuk" style="color:${t.suresi_asti ? "var(--kirmizi)" : "var(--soluk)"}">${kacis(s.kalan)}</span>`}
      </button>
      <span class="satir">${yeniCipi(t.yeni_gelisme)}${t.suresi_asti ? '<span class="cip asti">Süre aşıldı</span>' : ""}${durumCipi(t.durum)}</span>
    </div>`;
  }).join("");
}

async function detayAc(id, kaydir = true) {
  a.seciliId = id;
  const kutu = document.getElementById("detay");
  let t;
  try { t = await api(`/api/talepler/${id}`); } catch (e) { kutu.hidden = false; kutu.innerHTML = `<span class="hata">${kacis(e.message)}</span>`; return; }
  const s = sureBilgisi(t);
  const kapali = t.durum === "Sonuçlandı";
  kutu.hidden = false;
  kutu.innerHTML = `
    <div class="ust-satir" style="flex-wrap:wrap">
      <div style="display:flex;flex-direction:column;gap:4px">
        <div class="satir"><span class="mono soluk">#${kacis(t.no)}</span>${durumCipi(t.durum)}${t.kategori ? `<span class="cip bilgi">${kacis(t.kategori)}</span>` : ""}</div>
        <h2 style="font-size:20px">${kacis(t.konu)}</h2>
        ${t.konum ? `<span class="kucuk soluk">Konum: ${kacis(t.konum)}</span>` : ""}
      </div>
      <button type="button" class="cikis" id="detay-kapat">Kapat</button>
    </div>
    <div class="iki-sutun">
      <div style="flex:1 1 320px;min-width:0;display:flex;flex-direction:column;gap:12px">
        ${kapali ? `<div class="bilgi-kutusu" style="background:var(--yesil-acik);color:var(--yesil)">Talebiniz sonuçlandı.</div>` : `
        <div class="kart kimde-karti${t.suresi_asti ? " asti" : ""}">
          <span class="kimde-etiket">Şu an kimde?</span>
          <div style="display:flex;flex-direction:column;gap:2px">
            <strong>${kacis(t.birim)}</strong>
            <span class="cok-kucuk soluk">${kacis(t.daire)}</span>
          </div>
          ${s.cubuk}
          <div class="ust-satir cok-kucuk"><span class="soluk">${kacis(s.metin)}</span><strong>${kacis(s.kalan)}</strong></div>
        </div>`}
        ${kapanisBolumu(t)}
        ${t.aciklama ? `<div style="white-space:pre-line;font-size:14px">${kacis(t.aciklama)}</div>` : ""}
        ${kapali ? "" : `
        <form id="mesaj-formu" class="alan">
          <label for="mesaj">Birime mesaj yazın</label>
          <textarea id="mesaj" placeholder="Örn. Ders saatim 09.00'da, öncesinde bakılabilir mi?"></textarea>
          <span id="mesaj-hata" class="hata" role="alert"></span>
          <button class="buton" type="submit" style="align-self:flex-start">Gönder</button>
        </form>`}
      </div>
      <div style="flex:1 1 320px;min-width:0">
        <span class="etiket">Talebin yolculuğu</span>
        <div style="margin-top:10px">${yolculukCiz(t)}</div>
      </div>
    </div>`;

  document.getElementById("detay-kapat").addEventListener("click", () => {
    a.seciliId = null;
    kutu.hidden = true;
  });
  kapanisBagla(t, async () => { await listeCiz(); detayAc(id, false); });
  listeCiz(); // talep görüldü: "Yeni gelişme" işareti kalksın
  const form = document.getElementById("mesaj-formu");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const alan = document.getElementById("mesaj");
      const hata = document.getElementById("mesaj-hata");
      if (!alan.value.trim()) { hata.textContent = "Önce bir mesaj yazın."; return; }
      try {
        await api(`/api/talepler/${id}/mesaj`, { metin: alan.value });
        bildir("Mesajınız birime iletildi.");
        await listeCiz();
        detayAc(id, false);
      } catch (err) { hata.textContent = err.message; }
    });
  }
  if (kaydir) kutu.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function asistanaSor(e) {
  e.preventDefault();
  const alan = document.getElementById("soru");
  const kutu = document.getElementById("asistan-cevap");
  const soru = alan.value.trim();
  if (!soru) { kutu.innerHTML = '<span class="hata">Önce bir soru yazın.</span>'; return; }
  kutu.innerHTML = asistanBalonu(`<span class="dusunuyor">${ASISTAN_ADI} düşünüyor</span>`, "", "max-width:100%");
  try {
    const c = await api("/api/asistan", { soru });
    kutu.innerHTML = asistanBalonu(`
      ${c.emin ? "" : `<span class="cok-kucuk" style="color:var(--turuncu-yazi);font-weight:800">${c.kip === "yapay_zeka" ? "Kısmen emin: yönetmelik sorunun tamamını karşılamıyor" : "Emin değilim"}</span>`}
      <span>${kacis(c.cevap)}</span>
      ${kaynaklarCiz(c)}
      ${c.emin ? "" : `<div class="butonlar"><button type="button" class="buton" id="ilet">Personele ilet (${kacis(c.birim)})</button></div>`}`,
      c.emin ? "" : "emin-degil", "max-width:100%");
    const ilet = document.getElementById("ilet");
    if (ilet) {
      ilet.addEventListener("click", async () => {
        ilet.disabled = true;
        try {
          const t = await api("/api/talepler", {
            konu: soru.slice(0, 120),
            aciklama: "Asistan bu soruyu yanıtlayamadı; akademisyen personele iletti.\n\nSoru: " + soru,
            birim_id: c.birim_id,
            kategori: "Soru",
          });
          kutu.innerHTML = "";
          bildir(`Sorunuz talebe dönüştürüldü${t.no ? ` (${t.no})` : ""}.`);
          alan.value = "";
          await listeCiz();
          detayAc(t.id);
        } catch (err) {
          ilet.disabled = false;
          kutu.insertAdjacentHTML("beforeend", `<span class="hata">${kacis(err.message)}</span>`);
        }
      });
    }
  } catch (err) {
    kutu.innerHTML = `<span class="hata">${kacis(err.message)}</span>`;
  }
}

baslat();
