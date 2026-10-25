// Gishe – personel paneli
// Personel sadece KENDİ BİRİMİNİN taleplerini görür. Hangi birimde olduğu giriş yaptığı hesaptan gelir.
const DURUMLAR = ["Yeni", "İnceleniyor", "Bilgi bekleniyor", "Sonuçlandı"];

const p = {
  ben: null,
  birimler: [],
  filtre: "acik",
  talepler: [],
  seciliId: null,
};

function rolEtiketi(rol, ad) {
  return `<span class="rol ${rol}">${kacis(ad)}</span>`;
}

async function baslat() {
  try {
    p.ben = await oturumKontrol("personel");
    p.birimler = await api("/api/birimler");
  } catch (e) {
    document.getElementById("tablo").innerHTML = `<tr><td colspan="5" class="hata">${kacis(e.message)}</td></tr>`;
    return;
  }
  document.getElementById("kullanici-ad").textContent = p.ben.ad;
  document.getElementById("kullanici-birim").textContent = p.ben.eposta;

  document.getElementById("filtreler").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-filtre]");
    if (!b) return;
    p.filtre = b.dataset.filtre;
    document.querySelectorAll("#filtreler button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    tabloCiz();
  });
  document.getElementById("cikis").addEventListener("click", cikisYap);
  // Sıfırlama düğmesi sadece DEMO_MODU açıkken görünür (sunum provaları için)
  fetch(API_TABAN + "/health").then((y) => y.json()).then((d) => {
    document.getElementById("sifirla").hidden = !d.demo_modu;
  }).catch(() => {});
  document.getElementById("sifirla").addEventListener("click", async () => {
    if (!confirm("Tüm talepler silinip örnek veriler yeniden yüklenecek ve herkesin oturumu kapanacak. Emin misiniz?")) return;
    await api("/api/demo/sifirla", {}).catch(() => {});
    location.href = "/giris.html";
  });
  document.getElementById("tablo").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-id]");
    if (!b) return;
    p.seciliId = Number(b.dataset.id);
    tabloCiz();
    detayCiz();
  });
  await yenile();
  setInterval(() => yenile(false), 10000);
}

async function yenile(detayDahil = true) {
  try {
    const [talepler, ist] = await Promise.all([api("/api/talepler"), api("/api/istatistik")]);
    p.talepler = talepler;
    istatistikCiz(ist);
    tabloCiz();
    if (detayDahil) await detayCiz();
  } catch (e) {
    document.getElementById("tablo").innerHTML = `<tr><td colspan="5" class="hata">${kacis(e.message)}</td></tr>`;
  }
}

function istatistikCiz(ist) {
  const b = ist.birim;
  const kitle = { ogrenci: "öğrencilere", akademisyen: "akademisyenlere", ortak: "öğrenci ve akademisyenlere" }[b.kitle];
  document.getElementById("baslik").textContent = `${b.ad} · gelen talepler`;
  document.getElementById("daire").textContent = `${b.daire} · ${kitle} hizmet verir · hedef yanıt süresi ${b.hedef_gun} iş günü`;
  document.getElementById("rozet-acik").textContent = ist.acik;
  document.getElementById("rozet-asan").textContent = ist.suresi_asan;
  const dagilim = b.kitle === "ortak"
    ? `<span class="cok-kucuk soluk">${ist.ogrenci_talebi} öğrenci · ${ist.akademisyen_talebi} akademisyen</span>` : "";
  document.getElementById("istatistikler").innerHTML = `
    <div class="istatistik"><span class="kucuk soluk">Açık talep</span><strong>${ist.acik}</strong>${dagilim}</div>
    <div class="istatistik"><span class="kucuk soluk">Hedef süreyi aşan</span><strong style="color:${ist.suresi_asan ? "var(--kirmizi)" : "inherit"}">${ist.suresi_asan}</strong></div>
    <div class="istatistik"><span class="kucuk soluk">Bilgi bekleyen</span><strong>${ist.bilgi_bekleyen}</strong></div>
    <div class="istatistik"><span class="kucuk soluk">Memnuniyet</span><strong>${ist.memnuniyet_ort === null ? "–" : `${String(ist.memnuniyet_ort).replace(".", ",")} / 5`}</strong><span class="cok-kucuk soluk">${ist.memnuniyet_sayi} değerlendirme · son 30 günde ${ist.yeniden_acilan_30g} yeniden açılan</span></div>
    <div class="istatistik"><span class="kucuk soluk">Asistanın bugün yanıtladığı</span><strong>${ist.asistan_bugun - ist.asistan_emin_degil} / ${ist.asistan_bugun}</strong><span class="cok-kucuk soluk">Tüm birimler, soru metni saklanmaz</span></div>`;
}

function tabloCiz() {
  const liste = p.talepler.filter((t) =>
    p.filtre === "kapali" ? t.durum === "Sonuçlandı"
      : p.filtre === "asan" ? t.suresi_asti
        : t.durum !== "Sonuçlandı");
  const tablo = document.getElementById("tablo");
  if (!liste.length) {
    tablo.innerHTML = '<tr><td colspan="5" class="bos">Bu listede talep yok.</td></tr>';
    return;
  }
  tablo.innerHTML = liste.map((t) => `
    <tr class="${t.id === p.seciliId ? "secili" : ""}">
      <td class="mono">#${kacis(t.no)}</td>
      <td><button class="konu-buton" type="button" data-id="${t.id}">${kacis(t.konu)}</button>
        ${t.durum !== "Sonuçlandı" && t.birimde_yeni ? '<span class="cip yeni-gelisme" title="Talep sahibinin son işlemine henüz bakılmadı">Bakılmadı</span>' : ""}
        ${t.kategori ? `<div class="cok-kucuk soluk">${kacis(t.kategori)}</div>` : ""}
        ${t.puan ? `<div class="cok-kucuk">${yildizlar(t.puan)}</div>` : ""}</td>
      <td>${kacis(t.talep_eden)}<div>${rolEtiketi(t.talep_eden_rol, t.talep_eden_rol_adi)}</div></td>
      <td style="${t.suresi_asti ? "color:var(--kirmizi);font-weight:700" : ""}">${t.durum === "Sonuçlandı" ? "–" : `${t.gecen_gun + 1}. iş günü`}</td>
      <td>${t.suresi_asti ? '<span class="cip asti">Süre aşıldı</span> ' : ""}${durumCipi(t.durum)}</td>
    </tr>`).join("");
}

async function detayCiz() {
  const kutu = document.getElementById("detay");
  if (!p.seciliId) {
    kutu.innerHTML = '<div class="bos">Ayrıntıyı görmek için listeden bir talep seçin.</div>';
    return;
  }
  let t;
  try {
    t = await api(`/api/talepler/${p.seciliId}`);
  } catch (e) {
    // Talep başka birime aktarıldıysa artık bu personel göremez (sunucu 403 döner)
    kutu.innerHTML = `<div class="bos">${kacis(e.message)} Aktardığınız talepleri artık yeni birim yönetir; talep sahibi aktarma gerekçesini görebiliyor.</div>`;
    return;
  }
  const kapali = t.durum === "Sonuçlandı";
  // Sadece talep sahibine hizmet veren birimlere aktarılabilir
  const hedefler = p.birimler.filter((b) => b.id !== t.birim_id && (b.kitle === "ortak" || b.kitle === t.talep_eden_rol));
  kutu.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:4px">
      <div class="ust-satir"><span class="mono soluk">#${kacis(t.no)}</span>${durumCipi(t.durum)}</div>
      <h2 style="font-size:20px">${kacis(t.konu)}</h2>
      <span class="kucuk soluk">${rolEtiketi(t.talep_eden_rol, t.talep_eden_rol_adi)} ${kacis(t.talep_eden)} · ${kacis(t.talep_eden_aciklama)}</span>
    </div>
    ${t.konum ? `<div class="kucuk"><strong>Konum:</strong> ${kacis(t.konum)}</div>` : ""}
    ${t.aciklama ? `<div style="white-space:pre-line;font-size:14px">${kacis(t.aciklama)}</div>` : ""}

    <details>
      <summary class="etiket" style="cursor:pointer;min-height:32px">Talebin yolculuğu (${t.olaylar.length} adım)</summary>
      <div style="margin-top:10px">${yolculukCiz(t)}</div>
    </details>

    ${kapali ? `<div class="bilgi-kutusu">Bu talep sonuçlandı.${t.puan ? ` Talep sahibinin değerlendirmesi: ${yildizlar(t.puan)}${t.degerlendirme ? `<br><span class="kucuk">“${kacis(t.degerlendirme)}”</span>` : ""}` : " Talep sahibi henüz değerlendirmedi."}</div>` : `
    <form id="yanit-formu" class="ayrac">
      <label class="etiket" for="yanit">Talep sahibine yanıt</label>
      <textarea id="yanit" placeholder="Talep sahibinin göreceği mesaj"></textarea>
      <span class="hata" id="yanit-hata" role="alert"></span>
      <button class="buton" type="submit" style="align-self:flex-start">Gönder</button>
    </form>

    <form id="durum-formu" class="ayrac">
      <label class="etiket" for="durum">Durum</label>
      <div class="satir">
        <select id="durum">${DURUMLAR.map((d) => `<option ${d === t.durum ? "selected" : ""}>${kacis(d)}</option>`).join("")}</select>
        <button class="buton ikincil" type="submit">Güncelle</button>
      </div>
    </form>

    <form id="aktar-formu" class="ayrac">
      <strong>Başka birime aktar</strong>
      <span class="cok-kucuk soluk">Sadece ${kacis(t.talep_eden_rol_adi.toLocaleLowerCase("tr"))} taleplerine bakan birimler listelenir.</span>
      <div class="alan">
        <label for="hedef-birim">Birim</label>
        <select id="hedef-birim">${hedefler.map((b) => `<option value="${b.id}">${kacis(b.ad)}</option>`).join("")}</select>
      </div>
      <div class="alan">
        <label for="gerekce">Gerekçe (zorunlu — talep sahibi görür)</label>
        <input id="gerekce" type="text" maxlength="500" placeholder="Örn. Bu karar fakülte yönetim kurulunda alınır.">
      </div>
      <span class="hata" id="aktar-hata" role="alert"></span>
      <button class="buton koyu-cizgi" type="submit" style="align-self:flex-start">Aktar</button>
    </form>`}`;

  if (kapali) return;
  formBagla("yanit-formu", "yanit-hata", "Yanıt talep sahibine gönderildi.", () => {
    const metin = document.getElementById("yanit").value.trim();
    if (!metin) throw new Error("Önce bir yanıt yazın.");
    return api(`/api/talepler/${t.id}/mesaj`, { metin });
  });
  formBagla("durum-formu", null, "Durum güncellendi.", () =>
    api(`/api/talepler/${t.id}/durum`, { durum: document.getElementById("durum").value }));
  formBagla("aktar-formu", "aktar-hata", "Talep aktarıldı. Talep sahibi gerekçeyi görecek.", () => {
    const gerekce = document.getElementById("gerekce").value.trim();
    if (gerekce.length < 10) throw new Error("Gerekçe zorunludur (en az 10 karakter). Talep sahibi bu gerekçeyi görecek.");
    return api(`/api/talepler/${t.id}/aktar`, { birim_id: Number(document.getElementById("hedef-birim").value), gerekce });
  });
}

// Bir formu gönderince işlemi yapar, hata varsa gösterir, başarılıysa ekranı yeniler
function formBagla(formId, hataId, basariMesaji, islem) {
  document.getElementById(formId).addEventListener("submit", async (e) => {
    e.preventDefault();
    const hata = hataId ? document.getElementById(hataId) : null;
    if (hata) hata.textContent = "";
    try {
      await islem();
      bildir(basariMesaji);
      await yenile();
    } catch (err) {
      if (hata) hata.textContent = err.message; else bildir(err.message, "hata");
    }
  });
}

baslat();
