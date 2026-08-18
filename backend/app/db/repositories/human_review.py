"""HumanReview repository — create + latest lookup (Phase 17/18).

Every review POST appends a new row (audit trail); finalize and detail reads
use the latest row ("latest wins").
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import HumanReview


class HumanReviewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        evaluation_id: uuid.UUID,
        reviewer_id: int,
        overrides: dict[str, Any],
        human_changed: bool,
        notes: str | None = None,
    ) -> HumanReview:
        row = HumanReview(
            evaluation_id=evaluation_id,
            reviewer_id=reviewer_id,
            overrides=overrides,
            human_changed=human_changed,
            notes=notes,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def latest_for_evaluation(self, evaluation_id: uuid.UUID) -> HumanReview | None:
        stmt = (
            select(HumanReview)
            .where(HumanReview.evaluation_id == evaluation_id)
            .order_by(HumanReview.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()
