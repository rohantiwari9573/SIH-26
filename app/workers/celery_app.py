from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "deanon",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"])
