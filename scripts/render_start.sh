#!/bin/sh
# Single-container start for Render's free tier, which has no separate
# background-worker service: one Celery worker with beat embedded (-B) runs
# alongside the API, replacing docker-compose.prod.yml's separate
# api/worker/beat services. Concurrency 1 keeps it within the free plan's
# 512 MB. Embedded beat is safe only because exactly one instance runs.
celery -A app.workers.celery_app worker -B --concurrency=1 --loglevel=info &
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
