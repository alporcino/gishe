# Gishe ön yüz: önce derlenir, sonra derlenmiş hâli nginx ile sunulur (geliştirme sunucusu kullanılmaz)

# 1) Derleme aşaması
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json build.mjs ./
COPY src ./src
RUN npm run build

# 2) Sunum aşaması
FROM nginx:1.27-alpine
ENV BACKEND_URL=http://backend:8000 \
    API_URL=""
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/40-gishe-config.sh /docker-entrypoint.d/40-gishe-config.sh
# Windows'ta satır sonları CRLF olabilir; betiğin Linux'ta çalışması için düzeltilir
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-gishe-config.sh /etc/nginx/templates/default.conf.template \
 && chmod +x /docker-entrypoint.d/40-gishe-config.sh \
 && rm -f /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1/giris.html || exit 1
