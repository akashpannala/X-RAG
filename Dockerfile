FROM python:3.13-slim

# libgl1/libglib2.0-0: opencv (RapidOCR). curl: HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU torch/torchvision first — requirements.txt pins bare torch/torchvision (PyPI defaults are CUDA builds)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Small spaCy model for Presidio PII (~12MB). Presidio pip-installs its configured
# model on first use — bake sm in so containers never fetch the 800MB lg at runtime.
RUN pip install --no-cache-dir https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

COPY backend/ backend/
COPY frontend/ frontend/
COPY tests/ tests/
COPY pytest.ini docker-entrypoint.sh ./

# WSO2 rule: USER must be a numeric UID in 10000–20000 (usernames rejected at build validation)
RUN groupadd -g 10001 app && useradd -m -u 10001 -g app app && chown -R 10001:10001 /app

ENV HOST=0.0.0.0 \
    PORT=8001 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models

RUN mkdir -p data/uploads data/logs && chown -R 10001:10001 /app/data

VOLUME ["/app/data", "/models"]
EXPOSE 8001

USER 10001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8001}/health" || exit 1

ENTRYPOINT ["sh", "docker-entrypoint.sh"]