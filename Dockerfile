# =============================================================================
# Dockerfile — Quotation-Invoice API (FastAPI backend)
# =============================================================================
FROM python:3.12-slim

# psycopg2-binary and asyncpg both ship prebuilt wheels for this image, but
# libpq is still needed at runtime for psycopg2 (used by Alembic).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create the upload directory with correct ownership so that when the
# "backend_uploads" named volume is mounted here at container start, Docker
# initializes it from this (already-owned-by-app) directory instead of a
# fresh root-owned empty one — otherwise the non-root app user can't write
# to it (document_service.py creates this dir at import time).
RUN mkdir -p uploads/documents \
    && groupadd -r app && useradd -r -g app app \
    && chown -R app:app /app
USER app

COPY --chown=app:app docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
