#!/bin/sh

set -eu

echo "Running database migrations..."
alembic upgrade head

echo "Database migrations completed."

echo "Starting FastAPI..."
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}"