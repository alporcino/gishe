#!/bin/sh
# Konteyner açılırken çalışır: API adresini ortam değişkeninden okuyup tarayıcının kullanacağı config.js'i üretir.
# API_URL boşsa arayüz aynı adresi kullanır ve nginx /api isteklerini arka uca iletir.
set -eu
API_URL_TEMIZ=$(printf '%s' "${API_URL:-}" | tr -d '"\\<>')
printf 'window.GISHE = { apiUrl: "%s" };\n' "$API_URL_TEMIZ" > /usr/share/nginx/html/config.js
echo "Gishe arayüz ayarı yazıldı (API_URL='${API_URL_TEMIZ:-aynı adres}')."
