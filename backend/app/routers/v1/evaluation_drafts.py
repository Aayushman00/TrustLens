"""HTTP surface for the EvaluationDraft intake lifecycle (Task 2.4's service).

Purely additive: does not touch the existing evaluation-creation path.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.evaluation_draft import (
    CreateDraftRequest,
    DimensionConfigUpdate,
    DimensionValidationRead,
    EvaluationDraftRead,
)
from app.services.evaluation_draft_service import EvaluationDraftService

router = APIRouter(prefix="/evaluation-drafts", tags=["evaluation-drafts"])


@router.post("", response_model=EvaluationDraftRead, status_code=status.HTTP_201_CREATED)
def create_draft(body: CreateDraftRequest, db: Session = Depends(get_db)) -> EvaluationDraftRead:
    return EvaluationDraftService(db).create(body.model_id)


@router.put("/{draft_id}/{dimension}", response_model=DimensionValidationRead)
def update_dimension(
    draft_id: uuid.UUID, dimension: str, body: DimensionConfigUpdate, db: Session = Depends(get_db)
) -> DimensionValidationRead:
    return EvaluationDraftService(db).update_dimension(draft_id, dimension.upper(), body.model_dump(mode="json"))


@router.post("/{draft_id}/{dimension}/confirm", response_model=EvaluationDraftRead)
def confirm_dimension(draft_id: uuid.UUID, dimension: str, db: Session = Depends(get_db)) -> EvaluationDraftRead:
    return EvaluationDraftService(db).confirm_dimension(draft_id, dimension.upper())


@router.get("/{draft_id}", response_model=EvaluationDraftRead)
def get_draft(draft_id: uuid.UUID, db: Session = Depends(get_db)) -> EvaluationDraftRead:
    return EvaluationDraftService(db).get(draft_id)


@router.get("/{draft_id}/{dimension}/target-values")
def get_target_values(
    draft_id: uuid.UUID,
    dimension: str,
    dataset_content_id: uuid.UUID,
    target_column: str,
    db: Session = Depends(get_db),
) -> dict:
    """Distinct observed target-column values, for populating label-mapping
    rows before the user has saved anything — never a source of a default
    mapping (see EvaluationDraftService.discover_target_values)."""
    values = EvaluationDraftService(db).discover_target_values(dataset_content_id, target_column)
    return {"values": values}
