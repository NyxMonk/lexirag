# LexiRAG API (CPU). Build from the repository root:
#   docker build -f backend/Dockerfile -t lexirag-api backend
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BACKEND_HOST=0.0.0.0 \
    STORAGE_DIR=/data/storage \
    MODEL_CACHE_DIR=/data/models

# Tesseract with the LexiRAG language packs, for scanned PDFs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-hin tesseract-ocr-ben \
    tesseract-ocr-mar tesseract-ocr-pan tesseract-ocr-fra \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# CPU-only PyTorch keeps the image small; use the cu124 index for NVIDIA hosts.
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN useradd --create-home --uid 10001 lexirag && mkdir -p /data/storage /data/models && chown -R lexirag /data
USER lexirag

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status == 200 else 1)"
# Migrations are idempotent; models are never downloaded implicitly (mount /data/models or run download-models).
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
