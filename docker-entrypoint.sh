#!/bin/sh
# =============================================================================
# docker-entrypoint.sh
# -----------------------------------------------------------------------------
# Alembic is the only thing that manages the database schema in staging/UAT
# and production — no create_all() fallback. Migrations run once here before
# Uvicorn starts serving traffic.
# =============================================================================
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
