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

RUN groupadd -r app && useradd -r -g app app \
    && chown -R app:app /app
USER app

COPY --chown=app:app docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
