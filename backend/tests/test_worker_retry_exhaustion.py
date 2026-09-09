"""fail_stuck_running_evaluation — worker retry-exhaustion safety net.

Celery's autoretry_for=(ConnectionError, TimeoutError) with max_retries=3 can
exhaust its retries, leaving the DB row RUNNING forever with no reaper. The
fix (worker/app/tasks/evaluate.py::_FailStuckRunningTask.on_failure) calls
this function — the exact same atomic CAS (transition_status) used
everywhere else in the lifecycle, never a second mutation path.

These tests exercise the real backend function against real Postgres; the
Celery-level wiring itself (on_failure invoked only after retries are truly
exhausted, never mid-retry or on success) is covered in
worker/tests/test_celery_task_registration.py.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_event import (
    EVENT_EVALUATION_FAILED,
    REASON_WORKER_RETRIES_EXHAUSTED,
    EvaluationEventRepository,
)
from app.db.repositories.model import ModelRepository
from app.tasks.evaluate_pipeline import fail_stuck_running_evaluation


@pytest.fixture
def running_evaluation(db_session: Session) -> uuid.UUID:
    model = ModelRepository(db_session).create(hf_repo_id=f"org/retry-{uuid.uuid4().hex[:8]}")
    evaluation = EvaluationRepository(db_session).create(
        model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS
    )
    started = EvaluationRepository(db_session).transition_status(
        evaluation.id, expected=EvaluationStatus.PENDING, new=EvaluationStatus.RUNNING
    )
    assert started is not None
    db_session.flush()
    return evaluation.id


def test_exhausted_retries_transitions_running_to_failed(
    db_session: Session, running_evaluation: uuid.UUID
) -> None:
    transitioned = fail_stuck_running_evaluation(db_session, running_evaluation)
    assert transitioned is True

    row = EvaluationRepository(db_session).get_by_id(running_evaluation)
    assert row is not None
    assert row.status is EvaluationStatus.FAILED


def test_failure_event_recorded_exactly_once_with_closed_reason_code(
    db_session: Session, running_evaluation: uuid.UUID
) -> None:
    fail_stuck_running_evaluation(db_session, running_evaluation)

    events = EvaluationEventRepository(db_session).list_for_evaluation(running_evaluation)
    failed_events = [e for e in events if e.event_type == EVENT_EVALUATION_FAILED]
    assert len(failed_events) == 1
    assert failed_events[0].detail["reason_code"] == REASON_WORKER_RETRIES_EXHAUSTED
    assert failed_events[0].detail["from_status"] == "RUNNING"


def test_duplicate_call_does_not_create_duplicate_failure_event(
    db_session: Session, running_evaluation: uuid.UUID
) -> None:
    """Simulates a redelivered/duplicate on_failure signal for the same task."""
    first = fail_stuck_running_evaluation(db_session, running_evaluation)
    second = fail_stuck_running_evaluation(db_session, running_evaluation)

    assert first is True
    assert second is False  # no-op — already FAILED, not RUNNING anymore

    events = EvaluationEventRepository(db_session).list_for_evaluation(running_evaluation)
    failed_events = [e for e in events if e.event_type == EVENT_EVALUATION_FAILED]
    assert len(failed_events) == 1


def test_stale_signal_cannot_overwrite_another_terminal_state(
    db_session: Session, running_evaluation: uuid.UUID
) -> None:
    """The pipeline itself already reached FINALIZED before the task-level
    exception surfaced (e.g. a transient error after the real work was done)
    — the CAS must refuse to clobber that terminal state."""
    evals = EvaluationRepository(db_session)
    finalized = evals.transition_status(
        running_evaluation, expected=EvaluationStatus.RUNNING, new=EvaluationStatus.FINALIZED
    )
    assert finalized is not None

    transitioned = fail_stuck_running_evaluation(db_session, running_evaluation)
    assert transitioned is False

    row = evals.get_by_id(running_evaluation)
    assert row.status is EvaluationStatus.FINALIZED  # untouched

    events = EvaluationEventRepository(db_session).list_for_evaluation(running_evaluation)
    assert not any(e.event_type == EVENT_EVALUATION_FAILED for e in events)


def test_pending_evaluation_is_not_touched(db_session: Session) -> None:
    """A legitimately still-PENDING evaluation (never even started) must
    never be failed by this safety net — it only ever targets RUNNING."""
    model = ModelRepository(db_session).create(hf_repo_id=f"org/retry-{uuid.uuid4().hex[:8]}")
    evaluation = EvaluationRepository(db_session).create(
        model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS
    )
    db_session.flush()

    transitioned = fail_stuck_running_evaluation(db_session, evaluation.id)
    assert transitioned is False

    row = EvaluationRepository(db_session).get_by_id(evaluation.id)
    assert row.status is EvaluationStatus.PENDING
