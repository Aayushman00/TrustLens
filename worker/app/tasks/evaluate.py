"""Celery task ``trustlens.evaluate_model`` — thin wrapper around the evaluation pipeline.

Vendor-dependent imports (``app.db``, ``app.core.db``, ``evaluate_pipeline``) are
loaded lazily inside the task body so native worker unit tests can import this
module to assert task registration without the Docker-vendored ORM tree.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import Task

from app.celery_app import celery_app

logger = logging.getLogger("trustlens.worker")


class _FailStuckRunningTask(Task):
    """Celery calls ``on_failure`` exactly once a task ends in permanent
    FAILURE — after ``autoretry_for``'s max_retries is exhausted, or for any
    other unhandled exception. Never called for an in-progress retry (that is
    ``on_retry``, a separate callback) — so this can never fire before
    retries are actually exhausted.

    Reuses the same atomic CAS as the rest of the lifecycle
    (``fail_stuck_running_evaluation`` -> ``transition_status``); it is not a
    second status-mutation path. All backend-app imports are lazy, same as
    ``evaluate_model`` below, so native worker unit tests can still import
    this module without the Docker-vendored ORM tree.
    """

    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: object,
    ) -> None:
        from app.core.config import get_settings
        from app.schemas.internal import EvaluateModelPayload

        try:
            payload = EvaluateModelPayload.model_validate(kwargs)
        except Exception:
            logger.exception(
                "evaluate_model_on_failure_payload_invalid task_id=%s", task_id
            )
            return

        settings = get_settings()
        if not settings.database_url:
            logger.error(
                "evaluate_model_on_failure_no_database_url evaluation_id=%s task_id=%s",
                payload.evaluation_id,
                task_id,
            )
            return

        from app.core.db import get_session
        from app.tasks.evaluate_pipeline import fail_stuck_running_evaluation

        with get_session(settings.database_url) as session:
            transitioned = fail_stuck_running_evaluation(session, payload.evaluation_id)
        logger.error(
            "evaluate_model_on_failure evaluation_id=%s task_id=%s transitioned=%s error=%s",
            payload.evaluation_id,
            task_id,
            transitioned,
            repr(exc),
        )


@celery_app.task(
    name="trustlens.evaluate_model",
    bind=True,
    base=_FailStuckRunningTask,
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
