# Gishe yapay zekâ servisi: açık kaynak Qwen modeli Ollama ile tamamen yerelde, CPU'da çalışır.
# Model ağırlıkları DERLEME SIRASINDA indirilip imaja eklenir; çalıştırırken elle bir şey yapmak gerekmez.
FROM ollama/ollama:0.40.0

ARG MODEL=qwen2.5:3b
ENV OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_KEEP_ALIVE=24h \
    OLLAMA_NUM_PARALLEL=1 \
    OLLAMA_MAX_LOADED_MODELS=1

# Derleme sırasında Ollama'yı geçici olarak başlat, modeli indir, kapat
RUN set -e; \
    ollama serve > /tmp/ollama.log 2>&1 & \
    PID=$!; \
    i=0; \
    until ollama list > /dev/null 2>&1; do \
      i=$((i+1)); \
      if [ "$i" -gt 60 ]; then echo "Ollama derleme sırasında başlamadı:"; cat /tmp/ollama.log; exit 1; fi; \
      sleep 1; \
    done; \
    echo "Model indiriliyor: $MODEL"; \
    ollama pull "$MODEL"; \
    ollama list; \
    kill "$PID"; \
    rm -f /tmp/ollama.log

EXPOSE 11434
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=10 CMD ollama list > /dev/null || exit 1
