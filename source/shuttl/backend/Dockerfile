FROM python:3.12-slim AS base
WORKDIR /app

# ffmpeg: soundtrack decoding for the optional audio hit fusion (SHUTTL_AUDIO_FUSION=1)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ─── API stage ────────────────────────────────────────────────────────────────
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ─── Celery worker stage (swap base image for CUDA on GPU ECS) ────────────────
FROM base AS worker
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=info", "--concurrency=1", "--pool=solo"]
