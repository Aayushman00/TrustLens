"""EvaluationDraft / DraftDimensionConfig repository.

Drafts are mutable scratch state until atomically consumed by
``POST /v1/evaluations`` (Phase 4) — see Global Constraints in the V1
Dataset/Contract Redesign plan.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import DraftDimensionConfig, EvaluationDraft


class EvaluationDraftRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, model_id: int) -> EvaluationDraft:
        row = EvaluationDraft(model_id=model_id)
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, draft_id: uuid.UUID) -> EvaluationDraft | None:
        return self._session.get(EvaluationDraft, draft_id)

    def get_dimension(self, draft_id: uuid.UUID, dimension: str) -> DraftDimensionConfig | None:
        draft = self.get_by_id(draft_id)
        if draft is None:
            return None
        for dim in draft.dimensions:
            if dim.dimension == dimension:
                return dim
        return None

    def upsert_dimension(self, draft_id: uuid.UUID, dimension: str, **fields: Any) -> DraftDimensionConfig:
        """Create-or-replace the config row for ``dimension`` on this draft.

        Re-editing an already-confirmed dimension always clears that
        dimension's ``confirmed_at`` (the caller passes ``confirmed_at=None``
        in ``fields``) — it never touches the other dimension's row.
        """
        existing = self.get_dimension(draft_id, dimension)
        if existing is None:
            existing = DraftDimensionConfig(draft_id=draft_id, dimension=dimension)
            self._session.add(existing)
        for key, value in fields.items():
            setattr(existing, key, value)
        self._session.flush()
        return existing

    def set_model_snapshot(self, draft_id: uuid.UUID, *, resolved_model_sha: str, model_label_snapshot: dict) -> None:
        draft = self.get_by_id(draft_id)
        if draft is None:
            return
        draft.resolved_model_sha = resolved_model_sha
        draft.model_label_snapshot = model_label_snapshot
        self._session.flush()
