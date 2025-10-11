from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery("pearl")
celery_app.conf.broker_url = settings.redis_url
celery_app.conf.result_backend = settings.redis_url
celery_app.conf.task_default_queue = settings.celery_task_default_queue
celery_app.conf.task_routes = {
    "app.services.tasks.ingestion.ingest_pull_request": {
        "queue": settings.celery_task_default_queue,
    }
}
celery_app.conf.task_track_started = True
celery_app.conf.worker_max_tasks_per_child = 100
celery_app.conf.worker_prefetch_multiplier = 1

# Ensure Celery loads task modules at startup.
celery_app.autodiscover_tasks(["app.services.tasks"])

# Explicit import to register tasks when the worker starts without autodiscovery.
import app.services.tasks.ingestion  # noqa: E402,F401
