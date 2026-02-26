FROM python:3.11-slim AS builder

WORKDIR /build

# Build deps only (not needed at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime deps only (no compiler toolchain)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .

# Non-root user for production
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", \
     "gunicorn app.main:app \
      --worker-class uvicorn.workers.UvicornWorker \
      --workers ${WEB_CONCURRENCY:-2} \
      --bind 0.0.0.0:8000 \
      --timeout 120 \
      --graceful-timeout 30"]
