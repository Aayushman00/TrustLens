"""POST /v1/dataset-fetches and GET /v1/dataset-contents/{id}."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError, ValidationAppError
from app.core.config import get_settings
from app.db.repositories.dataset_content import DatasetContentRepository, DatasetFetchEventRepository
from app.schemas.dataset_content import DatasetContentRead, DatasetFetchRequest
from app.services.dataset_content_service import DatasetContentService
from app.storage.evidence_store import DatasetContentStore, get_dataset_content_store

router = APIRouter(prefix="/dataset-fetches", tags=["dataset-content"])
content_router = APIRouter(prefix="/dataset-contents", tags=["dataset-content"])
upload_router = APIRouter(prefix="/dataset-uploads", tags=["dataset-content"])

_MAX_UPLOAD_BYTES = 10_000_000


def get_dataset_content_store_dep() -> DatasetContentStore | None:
    """FastAPI dependency wrapper -- overridable in tests (no live MinIO needed)."""
    return get_dataset_content_store(get_settings())


def _get_service(
    db: Session = Depends(get_db),
    store: DatasetContentStore | None = Depends(get_dataset_content_store_dep),
) -> DatasetContentService:
    if store is None:
        raise ValidationAppError("Dataset content storage is not configured")
    return DatasetContentService(
        DatasetContentRepository(db),
        DatasetFetchEventRepository(db),
        store,
    )


@router.post("", response_model=DatasetContentRead, status_code=status.HTTP_201_CREATED)
def create_dataset_fetch(
    body: DatasetFetchRequest,
    service: DatasetContentService = Depends(_get_service),
) -> DatasetContentRead:
    return service.fetch_and_store(body)


@upload_router.post("", response_model=DatasetContentRead, status_code=status.HTTP_201_CREATED)
async def create_dataset_upload(
    file: UploadFile = File(...),
    service: DatasetContentService = Depends(_get_service),
) -> DatasetContentRead:
    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise ValidationAppError(f"uploaded file exceeds {_MAX_UPLOAD_BYTES} byte limit")
    return service.store_uploaded_file(data, filename=file.filename or "upload.csv")


@content_router.get("/{content_id}", response_model=DatasetContentRead)
def get_dataset_content(
    content_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DatasetContentRead:
    row = DatasetContentRepository(db).get_by_id(content_id)
    if row is None:
        raise NotFoundError(f"DatasetContent {content_id} not found", details={"id": str(content_id)})
    return DatasetContentRead.model_validate(row, from_attributes=True)
