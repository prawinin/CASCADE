from celery import Celery  # noqa: E402
from app.config import get_config  # noqa: E402

config = get_config()

celery_app = Celery(
    "kinetic_sketch_tasks",
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=["app.tasks.compute_tasks"]
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "storage-cleanup-hourly": {
            "task": "app.tasks.compute_tasks.storage_cleanup_task",
            "schedule": 3600.0,
        },
    }
)

if __name__ == "__main__":
    celery_app.start()
