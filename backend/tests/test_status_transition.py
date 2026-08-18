"""EvaluationRepository.transition_status idempotency (Phase 7)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.model import ModelRepository


def test_transition_status_idempotent(db_session: Session) -> None:
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/trans-{uuid.uuid4().hex[:8]}")
    evaluation = evals.create(
        model_id=model.id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        status=EvaluationStatus.PENDING,
    )
    db_session.flush()

    wrong = evals.transition_status(
        evaluation.id,
        expected=EvaluationStatus.RUNNING,
        new=EvaluationStatus.PROBES_COMPLETED,
    )
    assert wrong is None
    assert evals.get_by_id(evaluation.id).status == EvaluationStatus.PENDING  # type: ignore[union-attr]

    first = evals.transition_status(
        evaluation.id,
        expected=EvaluationStatus.PENDING,
        new=EvaluationStatus.RUNNING,
    )
    assert first is not None
    assert first.status == EvaluationStatus.RUNNING

    again = evals.transition_status(
        evaluation.id,
        expected=EvaluationStatus.PENDING,
        new=EvaluationStatus.RUNNING,
    )
    assert again is None
    assert evals.get_by_id(evaluation.id).status == EvaluationStatus.RUNNING  # type: ignore[union-attr]


def test_transition_status_accepts_expected_set(db_session: Session) -> None:
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/trans-set-{uuid.uuid4().hex[:8]}")
    evaluation = evals.create(
        model_id=model.id,
        evaluation_mode=EvaluationMode.AI_ASSISTED,
        status=EvaluationStatus.RUNNING,
    )
    db_session.flush()

    row = evals.transition_status(
        evaluation.id,
        expected={EvaluationStatus.PENDING, EvaluationStatus.RUNNING},
        new=EvaluationStatus.FAILED,
    )
    assert row is not None
    assert row.status == EvaluationStatus.FAILED
