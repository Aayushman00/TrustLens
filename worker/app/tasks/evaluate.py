"""Celery task ``trustlens.evaluate_model`` — thin wrapper around the evaluation pipeline.

Vendor-dependent imports (``app.db``, ``app.core.db``, ``evaluate_pipeline``) are
loaded lazily inside the task body so native worker unit tests can import this
module to assert task registration without the Docker-vendored ORM tree.
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app

logger = logging.getLogger("trustlens.worker")


@celery_app.task(
    name="trustlens.evaluate_model",
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    max_retries=3,
)
def evaluate_model(self, **kwargs: object) -> dict[str, str]:
    """Run the evaluation pipeline (probes → O/S/D agent → terminal) for one evaluation_id."""
    from app.core.config import get_settings
    from app.core.db import get_session
    from app.schemas.internal import EvaluateModelPayload
    from app.tasks.evaluate_pipeline import run_evaluation_pipeline

    payload = EvaluateModelPayload.model_validate(kwargs)
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set — cannot run evaluate_model")

    logger.info(
        "evaluate_model_start evaluation_id=%s mode=%s attempt=%s",
        payload.evaluation_id,
        payload.evaluation_mode.value,
        self.request.retries + 1,
    )
    with get_session(settings.database_url) as session:
        run_evaluation_pipeline(session, payload)
    logger.info("evaluate_model_done evaluation_id=%s", payload.evaluation_id)
    return {
        "evaluation_id": str(payload.evaluation_id),
        "status": "ok",
    }
