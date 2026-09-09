"""User-defined local Fairness dataset routes (upload/list/get/group-discovery).

Any authenticated user may upload and use their own local dataset — ownership
is enforced per-resource, but this is not admin-gated the way ``proxy_lr`` is:
this path never substitutes model or dataset, it evaluates the user's exact
selected model against their own data.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.errors import ValidationAppError
from app.core.config import get_settings
from app.db.enums import UserRole
from app.db.models import User
from app.schemas.common import ErrorResponse
from app.schemas.datasets import GroupDiscoveryRead, UserDatasetList, UserDatasetRead
from app.services.dataset_service import DatasetService
from app.storage.evidence_store import DatasetStore, get_dataset_store

router = APIRouter(prefix="/datasets", tags=["datasets"])


def get_dataset_store_dep() -> DatasetStore | None:
    """FastAPI dependency wrapper — overridable in tests (no live MinIO needed)."""
    return get_dataset_store(get_settings())


def _service(db: Session, store: DatasetStore | None) -> DatasetService:
    return DatasetService(db, dataset_store=store)


@router.post(
    "",
    response_model=UserDatasetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a local CSV dataset for user-defined Fairness evaluation",
    description=(
        "Stores the file in this TrustLens instance's local MinIO/S3 store — "
        "not a hosted/cloud service. CSV only, capped at 10 MB / ~50k rows."
    ),
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    store: DatasetStore | None = Depends(get_dataset_store_dep),
) -> UserDatasetRead:
    if not file.filename:
        raise ValidationAppError("uploaded file has no filename")
    data = await file.read()
    row = _service(db, store).upload(owner_id=current_user.id, filename=file.filename, data=data)
    return UserDatasetRead.model_validate(row)


@router.get(
    "",
    response_model=UserDatasetList,
    responses={401: {"model": ErrorResponse}},
)
def list_datasets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    store: DatasetStore | None = Depends(get_dataset_store_dep),
) -> UserDatasetList:
    rows = _service(db, store).list_for_owner(current_user.id)
    return UserDatasetList(items=[UserDatasetRead.model_validate(r) for r in rows])


@router.get(
    "/{dataset_id}",
    response_model=UserDatasetRead,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    store: DatasetStore | None = Depends(get_dataset_store_dep),
) -> UserDatasetRead:
    row = _service(db, store).get_owned(
        dataset_id,
        owner_id=current_user.id,
        is_admin=current_user.role == UserRole.ADMIN,
    )
    return UserDatasetRead.model_validate(row)


@router.get(
    "/{dataset_id}/groups",
    response_model=GroupDiscoveryRead,
    summary="Discover observed group values for a chosen group column",
    description=(
        "Reads the actual distinct values present in the dataset for the "
        "given column, with row counts. Never a hardcoded category list — "
        "missing/null values are reported explicitly, not folded into a group."
    ),
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def get_dataset_groups(
    dataset_id: uuid.UUID,
    column: str = Query(..., description="Group/sensitive-attribute column name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    store: DatasetStore | None = Depends(get_dataset_store_dep),
) -> GroupDiscoveryRead:
    return _service(db, store).discover_groups(
        dataset_id,
        owner_id=current_user.id,
        group_column=column,
        is_admin=current_user.role == UserRole.ADMIN,
    )


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def delete_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    store: DatasetStore | None = Depends(get_dataset_store_dep),
) -> None:
    _service(db, store).delete(
        dataset_id,
        owner_id=current_user.id,
        is_admin=current_user.role == UserRole.ADMIN,
    )
