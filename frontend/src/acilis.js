// Gishe – giriş ekranının açılış animasyonu
// 1) Gişe makinesinin yarığından giriş bileti basılır  2) saat damgası makara gibi dönüp durur
// 3) bilet ekrandaki yerine oturur, sayfa açılır ve imleç e-posta alanına gelir.
// Oturum başına bir kez oynar. Tıklayınca, Esc ile veya "Geç" ile atlanır.
// Hareket azaltma tercih edilmişse hiç oynamaz. Sunumda tekrar izlemek için: /giris.html?acilis
(function () {
  const kaplama = document.getElementById("acilis");
  const hedef = document.getElementById("giris-bileti");
  if (!kaplama || !hedef) return;

  const ANAHTAR = "gishe-acilis-goruldu";
  const zorla = new URLSearchParams(location.search).has("acilis");
  const azHareket = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let goruldu = false;
  try { goruldu = sessionStorage.getItem(ANAHTAR) === "1"; } catch (e) { /* gizli sekme */ }

  if (azHareket || (goruldu && !zorla)) { kaplama.remove(); return; }
  try { sessionStorage.setItem(ANAHTAR, "1"); } catch (e) { /* önemsiz */ }

  // Tanıtım biletinin kopyası basılır; asıl bilet uçuş bitene kadar gizli kalır
  // Kopyada kimlikler ve form alanları etkisizleştirilir (ekran okuyucu ve klavye için görünmez)
  const bilet = hedef.cloneNode(true);
  bilet.removeAttribute("id");
  bilet.setAttribute("aria-hidden", "true");
  bilet.querySelectorAll("[id]").forEach((el) => el.removeAttribute("id"));
  bilet.querySelectorAll("[for]").forEach((el) => el.removeAttribute("for"));
  bilet.inert = true; // görünür kalır ama tıklanamaz, odaklanamaz
  bilet.style.width = `${hedef.offsetWidth}px`;
  kaplama.querySelector(".acilis-kap").appendChild(bilet);
  hedef.style.visibility = "hidden";

  // Numara makarası: "GS-2401" → her rakam 0–9 şeridi olur
  const no = bilet.querySelector(".bilet-no");
  const metin = no.textContent;
  no.innerHTML = [...metin].map((k) => /\d/.test(k)
    ? `<span class="hane"><span>${"0123456789".split("").map((d) => `<span>${d}</span>`).join("")}</span></span>`
    : `<span>${k === " " ? "&nbsp;" : k}</span>`).join("");
  const makaralar = [...no.querySelectorAll(".hane > span")];
  const rakamlar = metin.replace(/\D/g, "").split("").map(Number);

  const zamanlar = [];
  const sonra = (ms, is) => zamanlar.push(setTimeout(is, ms));
  let bitti = false;

  function kapat() {
    if (bitti) return;
    bitti = true;
    zamanlar.forEach(clearTimeout);
    hedef.style.visibility = "";
    kaplama.classList.add("bitti");
    const ilkBos = [...hedef.querySelectorAll("input")].find((el) => !el.value);
    if (ilkBos && matchMedia("(pointer: fine)").matches) ilkBos.focus(); // telefonda klavye kendiliğinden açılmasın
    setTimeout(() => kaplama.remove(), 450);
    document.removeEventListener("keydown", tus);
  }
  function tus(e) { if (e.key === "Escape" || e.key === "Enter" || e.key === " ") kapat(); }
  kaplama.addEventListener("click", kapat);
  document.addEventListener("keydown", tus);

  // 1) Baskı
  sonra(150, () => kaplama.classList.add("basiliyor"));
  // 2) Makara: haneler sırayla, her biri birkaç tur atarak durur
  sonra(350, () => {
    makaralar.forEach((m, i) => {
      m.style.transitionDuration = `${600 + i * 70}ms`;
      m.style.transform = `translateY(-${rakamlar[i] * 10}%)`;
    });
  });
  // 3) Uçuş: kopya bilet, asıl biletin yerine (ve eğimine) taşınır
  sonra(1900, () => {
    const bas = bilet.getBoundingClientRect();
    const son = hedef.getBoundingClientRect();
    if (!son.width || !bas.width) { kapat(); return; }
    const olcek = hedef.offsetWidth / bilet.offsetWidth;
    const dx = (son.left + son.width / 2) - (bas.left + bas.width / 2);
    const dy = (son.top + son.height / 2) - (bas.top + bas.height / 2);
    const egim = getComputedStyle(hedef).transform;
    const aci = egim && egim !== "none" ? Math.round(Math.atan2(new DOMMatrix(egim).b, new DOMMatrix(egim).a) * 180 / Math.PI) : 0;

    // Bileti yarıktan çıkarıp ekrana sabitle, sonra uçur
    Object.assign(bilet.style, { position: "fixed", left: `${bas.left}px`, top: `${bas.top}px`, width: `${bas.width}px`, margin: 0, zIndex: 3, animation: "none", transform: "none" });
    kaplama.appendChild(bilet);
    kaplama.querySelector(".acilis-sahne").style.transition = "opacity .25s";
    kaplama.querySelector(".acilis-sahne").style.opacity = "0";
    kaplama.style.transition = "background-color .7s ease";
    kaplama.style.backgroundColor = "transparent";

    const ucus = bilet.animate([
      { transform: "none", filter: "drop-shadow(0 0 0 rgba(0,0,0,0))" },
      { transform: `translate(${dx}px, ${dy}px) rotate(${aci}deg) scale(${olcek})`, filter: "drop-shadow(0 24px 30px rgba(0,0,0,.35))" },
    ], { duration: 750, easing: "cubic-bezier(.5, 0, .2, 1)", fill: "forwards" });
    ucus.onfinish = kapat;
  });
})();
