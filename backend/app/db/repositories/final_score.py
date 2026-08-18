"""FinalScore repository — upsert per-evaluation FRIES result (Phase 16)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.models import FinalScore


class FinalScoreRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        evaluation_id: uuid.UUID,
        fries_score: float,
        dimension_scores: dict[str, Any],
        finalized_osd: dict[str, Any],
        overall_confidence: float | None,
        evaluation_mode: EvaluationMode,
    ) -> FinalScore:
        row = self._session.get(FinalScore, evaluation_id)
        if row is None:
            row = FinalScore(
                evaluation_id=evaluation_id,
                fries_score=fries_score,
                dimension_scores=dimension_scores,
                finalized_osd=finalized_osd,
                overall_confidence=overall_confidence,
                evaluation_mode=evaluation_mode,
            )
            self._session.add(row)
        else:
            row.fries_score = fries_score
            row.dimension_scores = dimension_scores
            row.finalized_osd = finalized_osd
            row.overall_confidence = overall_confidence
            row.evaluation_mode = evaluation_mode
        self._session.flush()
        return row

    def get_for_evaluation(self, evaluation_id: uuid.UUID) -> FinalScore | None:
        return self._session.get(FinalScore, evaluation_id)
