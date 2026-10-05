"""Evaluation repository — create / read / status updates / list by status."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import Evaluation


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
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, evaluation_id: uuid.UUID) -> Evaluation | None:
        return self._session.get(Evaluation, evaluation_id)

    def lock_for_report_generation(self, evaluation_id: uuid.UUID) -> None:
        """Acquire a row-level ``SELECT ... FOR UPDATE`` on this evaluation
        for the rest of the current transaction (audit P1-6).

        Used only to serialize concurrent report-version assignment
        (ReportService) — never to gate the CAS lifecycle transitions, which
        remain solely governed by ``transition_status``. A no-op (locks
        nothing) if the row does not exist; the caller is expected to have
        already confirmed it exists.
        """
        self._session.execute(
            select(Evaluation.id).where(Evaluation.id == evaluation_id).with_for_update()
        )

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

    def set_execution_metadata(
        self,
        evaluation_id: uuid.UUID,
        execution_metadata: dict[str, Any],
    ) -> Evaluation | None:
        """Persist real device/GPU evidence captured from a probe's inference run.

        Never called with fabricated data — the caller only invokes this when
        a probe actually reports ``device_info``/``inference`` metadata.
        """
        row = self.get_by_id(evaluation_id)
        if row is None:
            return None
        row.execution_metadata = execution_metadata
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
