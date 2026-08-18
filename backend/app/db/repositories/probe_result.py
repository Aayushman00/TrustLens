"""ProbeResult repository — create / count for evaluation progress."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import FriesDimension
from app.db.models import ProbeResult


class ProbeResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        evaluation_id: uuid.UUID,
        dimension: FriesDimension,
        metric_values: dict[str, Any] | None = None,
        confidence: float | None = None,
        evidence_refs: list[Any] | None = None,
    ) -> ProbeResult:
        row = ProbeResult(
            evaluation_id=evaluation_id,
            dimension=dimension,
            metric_values=metric_values or {},
            confidence=confidence,
            evidence_refs=evidence_refs if evidence_refs is not None else [],
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list_for_evaluation(self, evaluation_id: uuid.UUID) -> list[ProbeResult]:
        stmt = (
            select(ProbeResult)
            .where(ProbeResult.evaluation_id == evaluation_id)
            .order_by(ProbeResult.id)
        )
        return list(self._session.scalars(stmt).all())

    def count_for_evaluation(self, evaluation_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(ProbeResult).where(
            ProbeResult.evaluation_id == evaluation_id
        )
        return int(self._session.scalar(stmt) or 0)
