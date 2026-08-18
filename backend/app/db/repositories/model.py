"""Model (HF Hub registry) repository — create / read by id or hf_repo_id."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Model


class ModelRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        hf_repo_id: str,
        model_metadata: dict[str, Any] | None = None,
        checksum: str | None = None,
        revision: str | None = None,
    ) -> Model:
        row = Model(
            hf_repo_id=hf_repo_id,
            model_metadata=model_metadata or {},
            checksum=checksum,
            revision=revision,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, model_id: int) -> Model | None:
        return self._session.get(Model, model_id)

    def get_by_hf_repo_id(self, hf_repo_id: str) -> Model | None:
        stmt = select(Model).where(Model.hf_repo_id == hf_repo_id)
        return self._session.scalars(stmt).first()

    def update_by_hf_repo_id(
        self,
        hf_repo_id: str,
        *,
        model_metadata: dict[str, Any] | None = None,
        checksum: str | None = None,
        revision: str | None = None,
    ) -> Model | None:
        """Refresh metadata/checksum/revision for an existing row (HF re-import)."""
        row = self.get_by_hf_repo_id(hf_repo_id)
        if row is None:
            return None
        if model_metadata is not None:
            row.model_metadata = model_metadata
        row.checksum = checksum
        row.revision = revision
        self._session.flush()
        return row

    def list_all(self, *, limit: int = 50, cursor: str | None = None) -> list[Model]:
        """List models ordered by id; optional opaque cursor is last seen id."""
        limit = max(1, min(limit, 200))
        stmt = select(Model).order_by(Model.id.asc())
        if cursor:
            try:
                stmt = stmt.where(Model.id > int(cursor))
            except ValueError:
                pass
        stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt).all())
