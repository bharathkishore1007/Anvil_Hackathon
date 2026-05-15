"""
AutoSRE — Celery Task Queue Configuration
Redis-backed task queue with priority lanes and retry policies.
"""

import os
import sys

# Ensure the autosre package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery import Celery
from config import settings

celery_app = Celery(
    "autosre",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_queues={
        "high": {"exchange": "high", "routing_key": "high"},
        "default": {"exchange": "default", "routing_key": "default"},
        "low": {"exchange": "low", "routing_key": "low"},
    },
    task_default_retry_delay=5,
    task_max_retries=3,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["taskqueue"])
