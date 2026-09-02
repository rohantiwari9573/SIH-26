from datetime import timedelta

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "deanon",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"])

# Autonomous collection loop (SIH PS-26151's "continuously gather footprints
# from reliable available sources"): re-pulls the live public feeds Argus
# already knows how to ingest (Tor Onionoo, MISP OSINT, HIBP breach
# directory — see scripts/ingest_onionoo.py etc.) on a fixed interval, then
# re-runs correlation so a fresh external match surfaces without anyone
# manually re-triggering it. Only takes effect for a process actually
# running `celery -A app.workers.celery_app beat` (see docker-compose.prod.yml's
# `beat` service) — importing this module (e.g. from the API process) does
# not start any scheduling on its own.
celery_app.conf.beat_schedule = {
    "scheduled-collection": {
        "task": "tasks.run_scheduled_collection",
        "schedule": timedelta(hours=settings.scheduled_collection_interval_hours),
    }
}
