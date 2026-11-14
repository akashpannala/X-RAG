FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    HOST=0.0.0.0 \
    PORT=8001

# libgl1/libglib2.0-0: opencv (RapidOCR). curl: HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU torch/torchvision first — requirements pins bare torch/torchvision.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
      torch torchvision

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

# Small spaCy model for Presidio PII (~12MB) — bake it so containers never fetch
# the large model at runtime.
RUN pip install --no-cache-dir \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

COPY backend/ backend/
COPY frontend/ frontend/
COPY docker-entrypoint.sh .

RUN groupadd -g 10001 app && useradd -m -u 10001 -g app app \
    && mkdir -p /app/data/uploads /app/data/logs /app/data/kuzu /models \
    && chown -R 10001:10001 /app /models

VOLUME ["/app/data", "/models"]
EXPOSE 8001
USER 10001

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8001}/health" || exit 1

ENTRYPOINT ["sh", "docker-entrypoint.sh"]
