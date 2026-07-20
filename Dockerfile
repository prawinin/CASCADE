# KineticSketch AI - Multi-stage Docker Build
# Build: Lightweight production container for molecular dynamics workspace
# Includes: Python 3.11+, RDKit, PyTorch, Taipy GUI framework

FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies for building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Build wheels in isolated layer
RUN pip install --user --no-cache-dir --upgrade pip && \
    pip install --user --no-cache-dir -r requirements.txt


# Final runtime stage
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built wheels from builder stage
COPY --from=builder /root/.local /root/.local

# Set PATH to use local pip packages
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY . .

# Create non-root user for security and set entrypoint permissions
RUN useradd -m -u 1000 appuser && \
    chmod +x entrypoint.sh && \
    chown -R appuser:appuser /app
USER appuser

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/health/ready || exit 1

# Expose port
EXPOSE 7860

# Run application via entrypoint script
CMD ["./entrypoint.sh"]
