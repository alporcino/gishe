// Gishe ön yüz derlemesi (ek paket gerektirmez).
// src/ klasörünü dist/ klasörüne derler:
//   - CSS ve JS dosyalarındaki yorum satırlarını ve gereksiz boşlukları atar
//   - HTML'deki dosya bağlantılarına içerik özetinden sürüm ekler (tarayıcı eski dosyayı önbellekten göstermesin)
//   - config.js'e dokunmaz: o dosya konteyner açılırken ortam değişkeninden üretilir
//   - Resimleri (ör. gtu-logo.png) olduğu gibi kopyalar
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { extname, join } from "node:path";

const KAYNAK = "src";
const HEDEF = "dist";
rmSync(HEDEF, { recursive: true, force: true });
mkdirSync(HEDEF, { recursive: true });

const ozet = (metin) => createHash("sha256").update(metin).digest("hex").slice(0, 10);

// Güvenli küçültme: sadece satır başındaki // yorumları, /* */ blok yorumları (CSS) ve boş satırlar
function cssKucult(metin) {
  return metin.replace(/\/\*[\s\S]*?\*\//g, "").split("\n").map((s) => s.trim()).filter(Boolean).join("\n");
}
function jsKucult(metin) {
  return metin.split("\n").map((s) => s.replace(/\s+$/, "")).filter((s) => s.trim() && !/^\s*\/\/(?!#)/.test(s)).join("\n");
}

const surumler = {};
const dosyalar = readdirSync(KAYNAK);
const RESIMLER = [".png", ".svg", ".jpg", ".jpeg", ".webp", ".ico"];
for (const ad of dosyalar) {
  if (RESIMLER.includes(extname(ad).toLowerCase())) copyFileSync(join(KAYNAK, ad), join(HEDEF, ad));
}
for (const ad of dosyalar) {
  const tur = extname(ad);
  if (tur !== ".css" && tur !== ".js") continue;
  let icerik = readFileSync(join(KAYNAK, ad), "utf8");
  if (ad !== "config.js") icerik = tur === ".css" ? cssKucult(icerik) : jsKucult(icerik);
  writeFileSync(join(HEDEF, ad), icerik);
  if (ad !== "config.js") surumler[ad] = ozet(icerik);
}
for (const ad of dosyalar) {
  if (extname(ad) !== ".html") continue;
  let html = readFileSync(join(KAYNAK, ad), "utf8");
  for (const [dosya, s] of Object.entries(surumler)) {
    html = html.replaceAll(`"${dosya}"`, `"${dosya}?v=${s}"`);
  }
  writeFileSync(join(HEDEF, ad), html);
}
writeFileSync(join(HEDEF, "surum.json"), JSON.stringify({ uygulama: "Gishe", derleme: new Date().toISOString(), dosyalar: surumler }, null, 2));
console.log(`Derlendi: ${dosyalar.length} dosya -> ${HEDEF}/`);
