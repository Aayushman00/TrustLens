"""Celery application — Phase 7 evaluation worker (ADR 0005)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
_broker = settings.redis_url or "redis://localhost:6379/0"

celery_app = Celery(
    "trustlens",
    broker=_broker,
    backend=_broker,
)
celery_app.conf.update(
    task_default_queue="trustlens",
    task_acks_late=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
celery_app.autodiscover_tasks(["app.tasks"])

# Ensure task modules are imported when the worker process starts.
import app.tasks.evaluate  # noqa: E402, F401
