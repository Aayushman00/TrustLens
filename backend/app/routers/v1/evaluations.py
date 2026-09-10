"""Evaluation CRUD routes — create enqueues Celery job (Phase 7). Local single-user instance."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.enums import EvaluationStatus
from app.db.repositories.evaluation_event import EvaluationEventRepository
from app.schemas.common import ErrorResponse
from app.schemas.evaluation_draft import CreateEvaluationV2Request
from app.schemas.evaluation_events import EvaluationEventList, EvaluationEventRead
from app.schemas.evaluations import EvaluationCreate, EvaluationList, EvaluationRead
from app.services.evaluation_service import EvaluationService
from app.services.evaluation_service_v2 import EvaluationServiceV2

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

logger = logging.getLogger("trustlens.routers.evaluations")


@router.post(
    "",
    response_model=EvaluationRead,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
    summary="[DEPRECATED — use POST /v1/evaluations-v2] Create a bare, contract-free evaluation",
    description=(
        "Deprecated: use POST /v1/evaluations-v2 with a validated draft to "
        "configure Fairness/Robustness against a real dataset. This endpoint "
        "creates an evaluation with no dataset/contract selection of any "
        "kind — Fairness and Robustness both resolve NOT_APPLICABLE. Kept "
        "as the minimal, contract-free creation path (e.g. Integrity/"
        "Explainability/Safety-only evaluations)."
    ),
    responses={404: {"model": ErrorResponse}},
)
def create_evaluation(
    body: EvaluationCreate,
    db: Session = Depends(get_db),
) -> EvaluationRead:
    row = EvaluationService(db).create_evaluation(body)
    return EvaluationRead.model_validate(row)


@router.post(
    "-v2",
    response_model=EvaluationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Consume a validated EvaluationDraft into a frozen EvaluationContractV2",
    description=(
        "Atomically consumes an EvaluationDraft (Task 2.x intake) into a real, "
        "frozen Evaluation carrying EvaluationContractV2, stamped with the "
        "current methodology_version, and enqueues the worker. The sole "
        "evaluation-creation path (Phase 7 — the legacy flat-contract path "
        "has been removed)."
    ),
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def create_evaluation_v2(
    body: CreateEvaluationV2Request,
    db: Session = Depends(get_db),
) -> EvaluationRead:
    row = EvaluationServiceV2(db).create_from_draft(body.draft_id, body.evaluation_mode)
    return EvaluationRead.model_validate(row)


@router.get(
    "",
    response_model=EvaluationList,
)
def list_evaluations(
    status_filter: EvaluationStatus | None = Query(
        None,
        alias="status",
        description="Filter by evaluation status",
    ),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="Opaque cursor (evaluation UUID)"),
    db: Session = Depends(get_db),
) -> EvaluationList:
    rows, next_cursor = EvaluationService(db).list_evaluations(
        status=status_filter,
        limit=limit,
        cursor=cursor,
    )
    return EvaluationList(
        items=[EvaluationRead.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.get(
    "/{evaluation_id}",
    response_model=EvaluationRead,
    responses={404: {"model": ErrorResponse}},
)
def get_evaluation(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EvaluationRead:
    service = EvaluationService(db)
    row = service.get_evaluation(evaluation_id)
    return service.build_detail(row)


@router.post(
    "/{evaluation_id}/reconcile-enqueue",
    response_model=EvaluationRead,
    summary="Operator recovery for a confirmed Celery enqueue failure",
    description=(
        "Re-attempts the Celery enqueue for an evaluation whose "
        "most recent evaluation_created/evaluation_requeued event confirms "
        "enqueued=false — never an age-based guess, and never touches an "
        "evaluation that was actually enqueued (however slow it is to "
        "start). Records the real outcome as a new evaluation_requeued "
        "event; status remains PENDING (the worker's own PENDING->RUNNING "
        "transition is unaffected). Returns 409 if the evaluation is not "
        "PENDING or has no confirmed enqueue failure to reconcile. This is "
        "operator-triggered recovery, not an automatic/self-healing process."
    ),
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def reconcile_evaluation_enqueue(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EvaluationRead:
    row = EvaluationService(db).reconcile_enqueue_failure(evaluation_id)
    return EvaluationRead.model_validate(row)


@router.get(
    "/{evaluation_id}/events",
    response_model=EvaluationEventList,
    summary="Get evaluation lifecycle audit trail",
    description=(
        "Append-only lifecycle events for this evaluation, ordered chronologically "
        "(by insertion order, not timestamp — see EvaluationEvent). "
        "Evaluations created before this endpoint existed, or that have not "
        "progressed yet, return an empty list — never a fabricated history."
    ),
    responses={404: {"model": ErrorResponse}},
)
def get_evaluation_events(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EvaluationEventList:
    # Existence check only — same shared-read model as GET /{evaluation_id}
    # and GET /reports/{evaluation_id}. This table is audit evidence, not
    # authoritative state, so it is deliberately not exposed as part of
    # EvaluationRead itself.
    EvaluationService(db).get_evaluation(evaluation_id)
    rows = EvaluationEventRepository(db).list_for_evaluation(evaluation_id)
    return EvaluationEventList(items=[EvaluationEventRead.model_validate(r) for r in rows])
