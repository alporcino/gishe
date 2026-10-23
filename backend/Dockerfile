# Gishe arka uç: FastAPI + iş mantığı + yapay zekâ asistanı (Ollama'ya bağlanır)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VERI_KLASORU=/app/veri \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Root olmayan kullanıcıyla çalışır; veritabanı klasörü bu kullanıcıya aittir
RUN useradd --create-home --uid 1000 gishe && mkdir -p /app/veri && chown -R gishe:gishe /app
USER gishe

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)" || exit 1

# Debug/reload kapalı, tüm ağ arayüzlerini dinler (konteyner dışından erişim için 0.0.0.0)
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --log-level info"]
