"""DatasetContent/DatasetFetchEvent repositories.

upsert() uses Postgres's ON CONFLICT DO UPDATE (no-op update) so the atomic
upsert-by-content_hash race between two concurrent identical fetches always
resolves to exactly one row, with RETURNING giving back its id either way.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import DatasetContent, DatasetFetchEvent


class DatasetContentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        content_hash: str,
        storage_uri: str,
        byte_size: int,
        format: str,
        row_count: int,
        columns: list[dict[str, Any]],
        schema_sniff_version: int = 1,
    ) -> DatasetContent:
        stmt = pg_insert(DatasetContent).values(
            content_hash=content_hash,
            storage_uri=storage_uri,
            byte_size=byte_size,
            format=format,
            row_count=row_count,
            columns=columns,
            schema_sniff_version=schema_sniff_version,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[DatasetContent.content_hash],
            set_={"content_hash": stmt.excluded.content_hash},
        ).returning(DatasetContent.id)
        result_id = self._session.execute(stmt).scalar_one()
        self._session.flush()
        return self._session.get(DatasetContent, result_id)

    def get_by_id(self, content_id: uuid.UUID) -> DatasetContent | None:
        return self._session.get(DatasetContent, content_id)


class DatasetFetchEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        source_url: str,
        http_status: int | None,
        content_type: str | None,
        resolved_content_id: uuid.UUID | None,
        source_revision: str | None = None,
        error_message: str | None = None,
    ) -> DatasetFetchEvent:
        row = DatasetFetchEvent(
            source_url=source_url,
            requested_at=datetime.now(UTC),
            http_status=http_status,
            content_type=content_type,
            source_revision=source_revision,
            resolved_content_id=resolved_content_id,
            error_message=error_message,
        )
        self._session.add(row)
        self._session.flush()
        return row
