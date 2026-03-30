# ============================================================
# Stage 1: Build frontend
# ============================================================
FROM node:20-slim AS frontend-builder

WORKDIR /build

COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund

COPY web/ ./
RUN npm run build

# ============================================================
# Stage 2: Production runtime
# ============================================================
FROM python:3.11-slim

LABEL maintainer="Policy Center Team"
LABEL version="0.1.0"

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (installed before copying code for better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY app/ ./app/
COPY data/regions.json ./data/regions.json
COPY run.py .

# Copy frontend build output from stage 1
COPY --from=frontend-builder /build/dist ./web/dist

# Create runtime directories and non-root user
RUN mkdir -p /app/data /app/uploads /app/logs \
    && groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && chown -R appuser:appuser /app

# Entrypoint: run as root, chown volumes, then drop to appuser
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Database init happens automatically on first startup via lifespan hook
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
