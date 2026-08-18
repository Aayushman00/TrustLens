"""Evaluation repository — create / read / status updates / list by status."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import Evaluation, FinalScore


class EvaluationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        model_id: int,
        evaluation_mode: EvaluationMode,
        status: EvaluationStatus = EvaluationStatus.PENDING,
        probe_config: dict[str, Any] | None = None,
        task: str | None = None,
        dataset: str | None = None,
        config: str | None = None,
        model_revision: str | None = None,
        trustlens_version: str | None = None,
        evaluation_id: uuid.UUID | None = None,
        created_by: int | None = None,
    ) -> Evaluation:
        row = Evaluation(
            id=evaluation_id or uuid.uuid4(),
            model_id=model_id,
            evaluation_mode=evaluation_mode,
            status=status,
            probe_config=probe_config or {},
            task=task,
            dataset=dataset,
            config=config,
            model_revision=model_revision,
            trustlens_version=trustlens_version,
            created_by=created_by,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, evaluation_id: uuid.UUID) -> Evaluation | None:
        return self._session.get(Evaluation, evaluation_id)

    def list_by_status(self, status: EvaluationStatus) -> list[Evaluation]:
        stmt = (
            select(Evaluation)
            .where(Evaluation.status == status)
            .order_by(Evaluation.created_at.desc())
        )
        return list(self._session.scalars(stmt).all())

    def list_all(
        self,
        *,
        status: EvaluationStatus | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[Evaluation]:
        """List evaluations ordered by created_at desc, id desc; cursor is evaluation UUID."""
        limit = max(1, min(limit, 200))
        stmt = select(Evaluation).order_by(
            Evaluation.created_at.desc(),
            Evaluation.id.desc(),
        )
        if status is not None:
            stmt = stmt.where(Evaluation.status == status)
        if cursor:
            try:
                cursor_id = uuid.UUID(cursor)
                current = self.get_by_id(cursor_id)
                if current is not None:
                    stmt = stmt.where(
                        (Evaluation.created_at < current.created_at)
                        | (
                            (Evaluation.created_at == current.created_at)
                            & (Evaluation.id < current.id)
                        )
                    )
            except ValueError:
                pass
        stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt).all())

    def list_published(
        self,
        *,
        task: str | None = None,
        dataset: str | None = None,
        evaluation_mode: EvaluationMode | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[Evaluation]:
        """Published + FINALIZED rows joined to final_scores (Phase 22).

        Order: fries_score desc, published_at desc, id desc. The cursor is the
        last row's evaluation UUID (opaque to clients, same style as list_all);
        an unknown/invalid cursor is ignored.
        """
        limit = max(1, min(limit, 200))
        stmt = (
            select(Evaluation)
            .join(FinalScore, FinalScore.evaluation_id == Evaluation.id)
            .where(
                Evaluation.is_published.is_(True),
                Evaluation.status == EvaluationStatus.FINALIZED,
            )
            .order_by(
                FinalScore.fries_score.desc(),
                Evaluation.published_at.desc(),
                Evaluation.id.desc(),
            )
        )
        if task is not None:
            stmt = stmt.where(Evaluation.task == task)
        if dataset is not None:
            stmt = stmt.where(Evaluation.dataset == dataset)
        if evaluation_mode is not None:
            stmt = stmt.where(Evaluation.evaluation_mode == evaluation_mode)
        anchor = self._published_cursor_anchor(cursor)
        if anchor is not None:
            anchor_score, anchor_published_at, anchor_id = anchor
            stmt = stmt.where(
                (FinalScore.fries_score < anchor_score)
                | (
                    (FinalScore.fries_score == anchor_score)
                    & (
                        (Evaluation.published_at < anchor_published_at)
                        | (
                            (Evaluation.published_at == anchor_published_at)
                            & (Evaluation.id < anchor_id)
                        )
                    )
                )
            )
        stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt).all())

    def _published_cursor_anchor(self, cursor: str | None):
        """(fries_score, published_at, id) of the cursor row, or None if unusable."""
        if not cursor:
            return None
        try:
            cursor_id = uuid.UUID(cursor)
        except ValueError:
            return None
        row = self._session.execute(
            select(FinalScore.fries_score, Evaluation.published_at, Evaluation.id)
            .join(Evaluation, Evaluation.id == FinalScore.evaluation_id)
            .where(Evaluation.id == cursor_id, Evaluation.published_at.is_not(None))
        ).first()
        return None if row is None else (row[0], row[1], row[2])

    def update_status(
        self,
        evaluation_id: uuid.UUID,
        status: EvaluationStatus,
    ) -> Evaluation | None:
        row = self.get_by_id(evaluation_id)
        if row is None:
            return None
        row.status = status
        self._session.flush()
        return row

    def transition_status(
        self,
        evaluation_id: uuid.UUID,
        *,
        expected: EvaluationStatus | set[EvaluationStatus],
        new: EvaluationStatus,
    ) -> Evaluation | None:
        """Atomic conditional UPDATE — only applies if current status is in ``expected``.

        Returns the refreshed row on success, or ``None`` if the row is missing or
        the current status does not match (idempotent no-op / race-safe).
        """
        expected_set = {expected} if isinstance(expected, EvaluationStatus) else set(expected)
        stmt = (
            update(Evaluation)
            .where(
                Evaluation.id == evaluation_id,
                Evaluation.status.in_(expected_set),
            )
            .values(status=new)
        )
        result = self._session.execute(stmt)
        if result.rowcount == 0:
            return None
        self._session.flush()
        return self.get_by_id(evaluation_id)
