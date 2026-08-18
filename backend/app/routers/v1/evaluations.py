"""Evaluation CRUD routes — create enqueues Celery job (Phase 7). Bearer auth required."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.enums import EvaluationStatus
from app.db.models import User
from app.schemas.common import ErrorResponse
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
    row = EvaluationService(db).create_evaluation(body, created_by=current_user.id)
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
