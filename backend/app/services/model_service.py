"""Model service — orchestrates ModelRepository (+ HfHubModelAdapter for HF import)."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.adapters.base import ModelAdapter
from app.adapters.hf_hub import HfHubModelAdapter, parse_hf_ref
from app.api.errors import ConflictError, NotFoundError
from app.db.models import Model
from app.db.repositories.model import ModelRepository
from app.schemas.models import ImportHfRequest, ModelCreate

logger = logging.getLogger("trustlens.api")


class ModelService:
    def __init__(self, session: Session, *, hf_adapter: ModelAdapter | None = None) -> None:
        self._repo = ModelRepository(session)
        self._hf_adapter = hf_adapter

    def create_model(self, data: ModelCreate) -> Model:
        existing = self._repo.get_by_hf_repo_id(data.hf_repo_id)
        if existing is not None:
            raise ConflictError(
                f"Model with hf_repo_id '{data.hf_repo_id}' already exists",
                details={"hf_repo_id": data.hf_repo_id, "id": existing.id},
            )
        return self._repo.create(
            hf_repo_id=data.hf_repo_id,
            model_metadata=data.model_metadata,
            checksum=data.checksum,
            revision=data.revision,
        )

    def get_model(self, model_id: int) -> Model:
        row = self._repo.get_by_id(model_id)
        if row is None:
            raise NotFoundError(f"Model {model_id} not found", details={"model_id": model_id})
        return row

    def list_models(self, *, limit: int = 50, cursor: str | None = None) -> tuple[list[Model], str | None]:
        rows = self._repo.list_all(limit=limit, cursor=cursor)
        next_cursor = str(rows[-1].id) if len(rows) == limit and rows else None
        return rows, next_cursor

    def import_from_hf(self, data: ImportHfRequest) -> Model:
        """Resolve HF metadata (never weights) and upsert the models registry (ADR 0012)."""
        ref, revision_hint = parse_hf_ref(data.repo_id, data.url)
        revision = data.revision or revision_hint

        adapter = self._hf_adapter or HfHubModelAdapter()
        record = adapter.resolve(ref, revision=revision)

        existing = self._repo.get_by_hf_repo_id(record.hf_repo_id)
        if existing is None:
            logger.info("hf_import_create hf_repo_id=%s", record.hf_repo_id)
            return self._repo.create(
                hf_repo_id=record.hf_repo_id,
                model_metadata=record.model_metadata,
                checksum=record.checksum,
                revision=record.revision,
            )

        logger.info("hf_import_update hf_repo_id=%s model_id=%s", record.hf_repo_id, existing.id)
        row = self._repo.update_by_hf_repo_id(
            record.hf_repo_id,
            model_metadata=record.model_metadata,
            checksum=record.checksum,
            revision=record.revision,
        )
        if row is None:
            # Row could have been deleted concurrently between the lookup above and here.
            raise NotFoundError(
                f"Model '{record.hf_repo_id}' was removed during import",
                details={"hf_repo_id": record.hf_repo_id},
            )
        return row
