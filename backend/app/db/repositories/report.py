"""Report repository — append-only versioned rows per evaluation (Phase 19)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Report


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def latest_for_evaluation(self, evaluation_id: uuid.UUID) -> Report | None:
        stmt = (
            select(Report)
            .where(Report.evaluation_id == evaluation_id)
            .order_by(Report.version.desc(), Report.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def create(
        self,
        *,
        evaluation_id: uuid.UUID,
        json_uri: str,
        pdf_uri: str | None,
        version: int,
    ) -> Report:
        row = Report(
            evaluation_id=evaluation_id,
            json_uri=json_uri,
            pdf_uri=pdf_uri,
            version=version,
        )
        self._session.add(row)
        self._session.flush()
        return row
