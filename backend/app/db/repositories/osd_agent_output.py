"""OsdAgentOutput repository — persist PROPOSED O/S/D suggestions (Phase 16)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OsdAgentOutput


class OsdAgentOutputRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        evaluation_id: uuid.UUID,
        ai_suggestion: dict[str, Any],
        ai_confidence: float | None = None,
        evidence_used: list[Any] | None = None,
        rationale: str | None = None,
    ) -> OsdAgentOutput:
        row = OsdAgentOutput(
            evaluation_id=evaluation_id,
            ai_suggestion=ai_suggestion,
            ai_confidence=ai_confidence,
            evidence_used=evidence_used if evidence_used is not None else [],
            rationale=rationale,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def latest_for_evaluation(self, evaluation_id: uuid.UUID) -> OsdAgentOutput | None:
        stmt = (
            select(OsdAgentOutput)
            .where(OsdAgentOutput.evaluation_id == evaluation_id)
            .order_by(OsdAgentOutput.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()
