"""UserDataset repository — create / read by id / list all."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserDataset


class UserDatasetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        filename: str,
        format: str,
        content_hash: str,
        row_count: int,
        size_bytes: int,
        columns: list[dict[str, Any]],
        storage_uri: str,
        status: str = "ready",
        status_reason: str | None = None,
        id: uuid.UUID | None = None,
    ) -> UserDataset:
        row = UserDataset(
            id=id or uuid.uuid4(),
            filename=filename,
            format=format,
            content_hash=content_hash,
            row_count=row_count,
            size_bytes=size_bytes,
            columns=columns,
            storage_uri=storage_uri,
            status=status,
            status_reason=status_reason,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, dataset_id: uuid.UUID) -> UserDataset | None:
        return self._session.get(UserDataset, dataset_id)

    def list_all(self, *, limit: int = 100) -> list[UserDataset]:
        stmt = (
            select(UserDataset)
            .order_by(UserDataset.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        return list(self._session.scalars(stmt).all())

    def delete(self, row: UserDataset) -> None:
        self._session.delete(row)
        self._session.flush()
