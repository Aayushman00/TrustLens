"""Model CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ErrorResponse
from app.schemas.models import ModelCreate, ModelList, ModelRead
from app.services.model_service import ModelService

router = APIRouter(prefix="/models", tags=["models"])


@router.post(
    "",
    response_model=ModelRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
def create_model(
    body: ModelCreate,
    db: Session = Depends(get_db),
) -> ModelRead:
    row = ModelService(db).create_model(body)
    return ModelRead.model_validate(row)


@router.get(
    "",
    response_model=ModelList,
)
def list_models(
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="Opaque cursor (last model id)"),
    db: Session = Depends(get_db),
) -> ModelList:
    rows, next_cursor = ModelService(db).list_models(limit=limit, cursor=cursor)
    return ModelList(items=[ModelRead.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.get(
    "/{model_id}",
    response_model=ModelRead,
    responses={404: {"model": ErrorResponse}},
)
def get_model(
    model_id: int,
    db: Session = Depends(get_db),
) -> ModelRead:
    row = ModelService(db).get_model(model_id)
    return ModelRead.model_validate(row)
