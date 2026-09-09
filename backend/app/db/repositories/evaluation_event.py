"""EvaluationEvent repository — append-only lifecycle audit trail (Phase 4).

Strictly a write-once, read-many log. There is no update/delete method here
on purpose — nothing in the application is meant to ever mutate or remove a
recorded event. Ordering is always by ``id`` (see EvaluationEvent's
docstring for why ``created_at`` alone is unsafe).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvaluationEvent

# Closed event-type vocabulary (Phase 4). Deliberately small — no per-probe
# started/completed events; that granularity already exists in
# ProbeResult/EvidenceDossier. Kept as plain strings (not a native Postgres
# enum) so a future phase can add a type without an Alembic migration —
# mirrors the DocumentationSource.source_kind/documentation_type precedent.
EVENT_EVALUATION_CREATED = "evaluation_created"
EVENT_EVALUATION_REQUEUED = "evaluation_requeued"
EVENT_EVALUATION_STARTED = "evaluation_started"
EVENT_PROBES_COMPLETED = "probes_completed"
EVENT_AGENT_COMPLETED = "agent_completed"
EVENT_EVALUATION_FAILED = "evaluation_failed"
EVENT_AWAITING_REVIEW = "awaiting_review"
EVENT_HUMAN_REVIEW_SUBMITTED = "human_review_submitted"
EVENT_EVALUATION_FINALIZED = "evaluation_finalized"
EVENT_REPORT_GENERATED = "report_generated"

# Closed reason_code vocabulary for EVENT_EVALUATION_FAILED.detail.reason_code.
# Never exception text/stack traces/paths — one short code per existing
# logger.exception(...) failure branch in evaluate_pipeline.py.
REASON_MODEL_REF_MISMATCH = "model_ref_mismatch"
REASON_NO_EVIDENCE_STORE = "no_evidence_store"
REASON_PROBE_ERROR = "probe_error"
REASON_OSD_AGENT_ERROR = "osd_agent_error"
REASON_SCORING_ERROR = "scoring_error"
# The Celery task itself permanently failed (autoretry_for exhausted its
# max_retries on a transient ConnectionError/TimeoutError, or any other
# unhandled exception escaped the task) — recorded by
# fail_stuck_running_evaluation, called from the worker's Task.on_failure.
REASON_WORKER_RETRIES_EXHAUSTED = "worker_retries_exhausted"


class EvaluationEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        evaluation_id: uuid.UUID,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> EvaluationEvent:
        row = EvaluationEvent(
            evaluation_id=evaluation_id,
            event_type=event_type,
            detail=detail,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list_for_evaluation(self, evaluation_id: uuid.UUID) -> list[EvaluationEvent]:
        stmt = (
            select(EvaluationEvent)
            .where(EvaluationEvent.evaluation_id == evaluation_id)
            .order_by(EvaluationEvent.id)
        )
        return list(self._session.scalars(stmt).all())
