"""Task 4.2 — methodology_version backfill.

Verifies the migration backfills pre-existing ``evaluations`` rows to
LEGACY_METHODOLOGY_VERSION at the DB level (server_default), not just that
the column exists — including a row inserted via raw SQL, bypassing the ORM
entirely, so a Python-side default couldn't silently be doing the work
instead of the migration's server_default.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.repositories.evaluation import EvaluationRepository
from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION


@pytest.fixture
def seeded_evaluation(db_session: Session, seeded_model) -> object:
    """A plain Evaluation row created the same way existing tests do —
    via EvaluationRepository.create, with no methodology_version passed."""
    return EvaluationRepository(db_session).create(
        model_id=seeded_model.id,
        evaluation_mode=EvaluationMode.AI_ASSISTED,
    )


def test_existing_rows_backfilled_to_legacy_value(
    db_session: Session, seeded_evaluation
) -> None:
    row = EvaluationRepository(db_session).get_by_id(seeded_evaluation.id)
    assert row.methodology_version == LEGACY_METHODOLOGY_VERSION


def test_raw_sql_insert_bypassing_orm_also_backfills_to_legacy_value(
    db_session: Session, seeded_model
) -> None:
    """The backfill must be a DB-level server_default, not a Python-side ORM
    default — a raw INSERT that never goes through the Evaluation model or
    EvaluationRepository must still land on LEGACY_METHODOLOGY_VERSION."""
    new_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO evaluations (id, model_id, status, evaluation_mode)
            VALUES (:id, :model_id, 'PENDING', 'AI_ASSISTED')
            """
        ),
        {"id": new_id, "model_id": seeded_model.id},
    )
    db_session.flush()

    row = EvaluationRepository(db_session).get_by_id(new_id)
    assert row is not None
    assert row.methodology_version == LEGACY_METHODOLOGY_VERSION
