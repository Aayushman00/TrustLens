"""Celery producer client — enqueue only; no task bodies in the API process."""

from __future__ import annotations

import logging
from functools import lru_cache

from celery import Celery

from app.core.config import get_settings
from app.schemas.internal import EvaluateModelPayload

logger = logging.getLogger("trustlens.api")

TASK_NAME = "trustlens.evaluate_model"


@lru_cache
def get_celery_app() -> Celery:
    """Lightweight producer Celery app sharing the worker's broker/backend URL."""
    settings = get_settings()
    redis_url = settings.redis_url or "redis://localhost:6379/0"
    app = Celery("trustlens", broker=redis_url, backend=redis_url)
    app.conf.update(
        task_default_queue="trustlens",
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_always_eager=settings.celery_task_always_eager,
    )
    return app


def enqueue_evaluate_model(payload: EvaluateModelPayload) -> str | None:
    """Send ``trustlens.evaluate_model``. Returns task id, or None if Redis unset.

    When ``REDIS_URL`` is unset (host-side unit tests), skip enqueue gracefully
    so create_evaluation still returns PENDING without requiring a broker.
    """
    settings = get_settings()
    if not settings.redis_url:
        logger.warning(
            "enqueue_skipped_no_redis evaluation_id=%s",
            payload.evaluation_id,
        )
        return None
    try:
        result = get_celery_app().send_task(
            TASK_NAME,
            kwargs=payload.model_dump(mode="json"),
            queue="trustlens",
        )
    except Exception:
        logger.exception(
            "enqueue_failed evaluation_id=%s — evaluation left PENDING",
            payload.evaluation_id,
        )
        return None
    logger.info(
        "enqueued_evaluate_model evaluation_id=%s task_id=%s mode=%s",
        payload.evaluation_id,
        result.id,
        payload.evaluation_mode.value,
    )
    return result.id
