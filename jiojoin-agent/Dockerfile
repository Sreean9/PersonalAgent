# ─────────────────────────────────────────────────────────────────────────────
# JioJoin Personal AI Agent — Dockerfile
# Multi-stage build: keeps the final image lean (~200 MB)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build deps in a full image ──────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps needed to compile some wheels (bcrypt, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: lean runtime image ──────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user for security
RUN groupadd -r jiojoin && useradd -r -g jiojoin jiojoin

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source (exclude dev/temp files via .dockerignore)
COPY --chown=jiojoin:jiojoin . .

# Ensure the data directory exists and is writable (SQLite fallback)
RUN mkdir -p /data && chown jiojoin:jiojoin /data

# Switch to non-root user
USER jiojoin

# Expose the default port (Railway / Cloud Run override with $PORT)
EXPOSE 8000

# Health-check so orchestrators know when the app is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health')" || exit 1

# Default start command — Railway overrides via railway.json / $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --log-level info"]
