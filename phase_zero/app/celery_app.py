"""
Celery application — GPU Gross Margin Visibility.

Broker + backend: Redis.
Beat schedule imported from celery_config.
Task autodiscovery: app.tasks module.
"""

import os

from celery import Celery

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
BACKEND_URL = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "gpu_margin",
    broker=BROKER_URL,
    backend=BACKEND_URL,
)

# Import beat schedule
from app.celery_config import beat_schedule  # noqa: E402

celery_app.conf.beat_schedule = beat_schedule
celery_app.conf.timezone = "UTC"
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]

# Autodiscover tasks
celery_app.autodiscover_tasks(["app"])
