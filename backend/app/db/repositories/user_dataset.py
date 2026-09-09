"""UserDataset repository — create / read by id (owner-scoped) / list for owner."""

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
        owner_id: int,
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
            owner_id=owner_id,
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

    def get_owned(self, dataset_id: uuid.UUID, *, owner_id: int) -> UserDataset | None:
        row = self.get_by_id(dataset_id)
        if row is None or row.owner_id != owner_id:
            return None
        return row

    def list_for_owner(self, owner_id: int, *, limit: int = 100) -> list[UserDataset]:
        stmt = (
            select(UserDataset)
            .where(UserDataset.owner_id == owner_id)
            .order_by(UserDataset.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        return list(self._session.scalars(stmt).all())

    def delete(self, row: UserDataset) -> None:
        self._session.delete(row)
        self._session.flush()
