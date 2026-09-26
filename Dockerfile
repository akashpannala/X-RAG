FROM python:3.13-slim

# libgl1/libglib2.0-0: opencv (RapidOCR). curl: HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl libgl1 libglib2.0-0 \
    && rm -rf /varllib/apt/lists/*

WORKDIR /app

# CPU torch/torchvision first — requirements.txt pins bare torch/torchvision (PyPI defaults are CUDA builds)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY tests/ tests/
COPY pytest.ini docker-entrypoint.sh ./

ENV HOST=0.0.0.0 \
    PORT=8001 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models

RUN mkdir -p data/uploads data/logs

VOLUME ["/app/data", "/models"]
EXPOSE 8001 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8001}/health" || exit 1

ENTRYPOINT ["sh", "docker-entrypoint.sh"]
