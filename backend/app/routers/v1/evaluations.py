"""Evaluation CRUD routes — create enqueues Celery job (Phase 7). Bearer auth required."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.db.enums import EvaluationStatus, UserRole
from app.db.models import User
from app.db.repositories.evaluation_event import EvaluationEventRepository
from app.schemas.common import ErrorResponse
from app.schemas.evaluation_events import EvaluationEventList, EvaluationEventRead
from app.schemas.evaluations import EvaluationCreate, EvaluationList, EvaluationRead
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post(
    "",
    response_model=EvaluationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create evaluation and enqueue stub job",
    description=(
        "Creates an evaluation as PENDING and enqueues trustlens.evaluate_model. "
        "Returns immediately with status=PENDING; poll GET /{id} for progress."
    ),
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_evaluation(
    body: EvaluationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluationRead:
    row = EvaluationService(db).create_evaluation(
        body, created_by=current_user.id, creator=current_user
    )
    return EvaluationRead.model_validate(row)


@router.get(
    "",
    response_model=EvaluationList,
    responses={401: {"model": ErrorResponse}},
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
    current_user: User = Depends(get_current_user),
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
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_evaluation(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluationRead:
    service = EvaluationService(db)
    row = service.get_evaluation(evaluation_id)
    return service.build_detail(row)


@router.post(
    "/{evaluation_id}/reconcile-enqueue",
    response_model=EvaluationRead,
    summary="Operator recovery for a confirmed Celery enqueue failure",
    description=(
        "Admin-only. Re-attempts the Celery enqueue for an evaluation whose "
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
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def reconcile_evaluation_enqueue(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
) -> EvaluationRead:
    row = EvaluationService(db).reconcile_enqueue_failure(evaluation_id)
    return EvaluationRead.model_validate(row)


@router.get(
    "/{evaluation_id}/events",
    response_model=EvaluationEventList,
    summary="Get evaluation lifecycle audit trail",
    description=(
        "Append-only lifecycle events for this evaluation, ordered chronologically "
        "(by insertion order, not timestamp — see EvaluationEvent). Same access "
        "level as evaluation detail reads: any authenticated user. Evaluations "
        "created before this endpoint existed, or that have not progressed yet, "
        "return an empty list — never a fabricated history."
    ),
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_evaluation_events(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluationEventList:
    # Existence check only — same shared-read model as GET /{evaluation_id}
    # and GET /reports/{evaluation_id} (any authenticated user, no owner
    # filter). This table is audit evidence, not authoritative state, so it
    # is deliberately not exposed as part of EvaluationRead itself.
    EvaluationService(db).get_evaluation(evaluation_id)
    rows = EvaluationEventRepository(db).list_for_evaluation(evaluation_id)
    return EvaluationEventList(items=[EvaluationEventRead.model_validate(r) for r in rows])
