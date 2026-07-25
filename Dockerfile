# KineticSketch AI - Multi-stage Docker Build
# Build: Lightweight production container for molecular dynamics workspace
# Includes: Python 3.11, RDKit, CPU PyTorch, Flask, Gunicorn

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# Final runtime stage
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/kineticsketch \
    HOST=0.0.0.0 \
    PORT=7860 \
    MODEL_DEVICE=cpu \
    KINETICSKETCH_DATA_DIR=/opt/kineticsketch/data \
    KINETICSKETCH_STATE_DIR=/var/lib/kineticsketch/state \
    KINETICSKETCH_JOBS_DIR=/var/lib/kineticsketch/jobs \
    KINETICSKETCH_CACHE_DIR=/var/cache/kineticsketch

# Create the runtime identity before copying large assets so ownership is set in
# one layer (Hugging Face Docker Spaces also run applications as UID 1000).
RUN useradd -m -u 1000 appuser && \
    mkdir -p /var/lib/kineticsketch/state /var/lib/kineticsketch/jobs /var/cache/kineticsketch && \
    chown -R appuser:appuser /var/lib/kineticsketch /var/cache/kineticsketch

# Copy application code and any manually supplied model/data assets.
COPY --chown=appuser:appuser . /opt/kineticsketch
WORKDIR /opt/kineticsketch
RUN chmod +x entrypoint.sh
USER appuser

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-7860}/health/ready" || exit 1

# Expose port
EXPOSE 7860

# Run application via entrypoint script
CMD ["./entrypoint.sh"]
