from celery import Celery  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

# Ensure app and parent directories are in python path
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

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
)

if __name__ == "__main__":
    celery_app.start()
