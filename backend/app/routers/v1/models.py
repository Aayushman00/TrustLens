"""Model CRUD routes (Bearer auth required)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.common import ErrorResponse
from app.schemas.models import ModelCreate, ModelList, ModelRead
from app.services.model_service import ModelService

router = APIRouter(prefix="/models", tags=["models"])


@router.post(
    "",
    response_model=ModelRead,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_model(
    body: ModelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ModelRead:
    row = ModelService(db).create_model(body)
    return ModelRead.model_validate(row)


@router.get(
    "",
    response_model=ModelList,
    responses={401: {"model": ErrorResponse}},
)
def list_models(
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="Opaque cursor (last model id)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ModelList:
    rows, next_cursor = ModelService(db).list_models(limit=limit, cursor=cursor)
    return ModelList(items=[ModelRead.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.get(
    "/{model_id}",
    response_model=ModelRead,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_model(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ModelRead:
    row = ModelService(db).get_model(model_id)
    return ModelRead.model_validate(row)
