"""DocumentationSource repository — create / list-for-model / owned lookup."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentationSource


class DocumentationSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        model_id: int,
        source_kind: str,
        documentation_type: str,
        retrieval_status: str,
        source_model_ref: str,
        url: str | None = None,
        title: str | None = None,
        description: str | None = None,
        documentation_revision: str | None = None,
        documentation_content_hash: str | None = None,
        retrieval_error: str | None = None,
        content_length: int | None = None,
        source_model_revision: str | None = None,
        created_by: int | None = None,
    ) -> DocumentationSource:
        row = DocumentationSource(
            model_id=model_id,
            source_kind=source_kind,
            documentation_type=documentation_type,
            url=url,
            title=title,
            description=description,
            documentation_revision=documentation_revision,
            documentation_content_hash=documentation_content_hash,
            retrieval_status=retrieval_status,
            retrieval_error=retrieval_error,
            content_length=content_length,
            source_model_ref=source_model_ref,
            source_model_revision=source_model_revision,
            created_by=created_by,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, source_id: int) -> DocumentationSource | None:
        return self._session.get(DocumentationSource, source_id)

    def list_for_model(self, model_id: int) -> list[DocumentationSource]:
        stmt = (
            select(DocumentationSource)
            .where(DocumentationSource.model_id == model_id)
            .order_by(DocumentationSource.created_at.desc())
        )
        return list(self._session.scalars(stmt).all())

    def replace_hf_source(
        self,
        *,
        model_id: int,
        evidence: dict[str, Any],
        source_model_ref: str,
    ) -> DocumentationSource:
        """Upsert the single auto-fetched HF card row for this model.

        Re-import refreshes documentation evidence just like it refreshes
        ``model_metadata`` — old auto-fetched rows for this model are removed
        first so history doesn't accumulate stale duplicates every re-import.
        """
        existing = [
            row
            for row in self.list_for_model(model_id)
            if row.source_kind == "huggingface_hub"
        ]
        for row in existing:
            self._session.delete(row)
        self._session.flush()
        return self.create(
            model_id=model_id,
            source_kind="huggingface_hub",
            documentation_type=evidence.get("documentation_source_type") or "model_card",
            retrieval_status=evidence.get("retrieval_status") or "error",
            source_model_ref=source_model_ref,
            url=evidence.get("documentation_url"),
            documentation_revision=evidence.get("documentation_revision"),
            documentation_content_hash=evidence.get("documentation_content_hash"),
            retrieval_error=evidence.get("retrieval_error"),
            content_length=evidence.get("content_length"),
            source_model_revision=evidence.get("source_model_revision"),
        )
