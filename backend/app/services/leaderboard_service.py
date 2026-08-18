"""Leaderboard service (Phase 22, ADR 0013) — opt-in published evaluations only.

Lists only explicitly published FINALIZED evaluations (never auto-dumps all
finals). Each entry keeps its comparability context and mode/human-review
provenance; when no task filter is given, the response carries a note that
entries may not be comparable across tasks.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.models import Evaluation
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.report import ReportRepository
from app.schemas.leaderboard import (
    NON_COMPARABLE_NOTE,
    LeaderboardEntry,
    LeaderboardList,
    LeaderboardReportRef,
)


class LeaderboardService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._evals = EvaluationRepository(session)
        self._reports = ReportRepository(session)

    def list_published(
        self,
        *,
        task: str | None = None,
        dataset: str | None = None,
        evaluation_mode: EvaluationMode | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> LeaderboardList:
        rows = self._evals.list_published(
            task=task,
            dataset=dataset,
            evaluation_mode=evaluation_mode,
            limit=limit,
            cursor=cursor,
        )
        next_cursor = str(rows[-1].id) if len(rows) == limit and rows else None
        return LeaderboardList(
            items=[self._to_entry(row) for row in rows],
            next_cursor=next_cursor,
            note=NON_COMPARABLE_NOTE if task is None else None,
        )

    def _to_entry(self, evaluation: Evaluation) -> LeaderboardEntry:
        final = evaluation.final_score  # inner join guarantees presence
        report_row = self._reports.latest_for_evaluation(evaluation.id)
        report = (
            LeaderboardReportRef(
                version=report_row.version,
                json_uri=report_row.json_uri,
                pdf_uri=report_row.pdf_uri,
            )
            if report_row is not None
            else None
        )
        return LeaderboardEntry(
            evaluation_id=evaluation.id,
            model_id=evaluation.model_id,
            hf_repo_id=evaluation.model.hf_repo_id,
            model_revision=evaluation.model_revision,
            evaluation_mode=evaluation.evaluation_mode,
            human_reviewed=bool(
                (final.finalized_osd or {}).get("human_reviewed", False)
            ),
            task=evaluation.task,
            dataset=evaluation.dataset,
            config=evaluation.config,
            trustlens_version=evaluation.trustlens_version,
            fries_score=final.fries_score,
            overall_confidence=final.overall_confidence,
            published_at=evaluation.published_at,
            report=report,
        )
