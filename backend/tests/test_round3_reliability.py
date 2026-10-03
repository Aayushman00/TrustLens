"""Round 3 L8 — evaluation lifecycle reliability regressions.

1. Commit/enqueue order: the worker can pick a task up the instant it is
   sent, so the evaluation row must already be committed by then.
2. No silent RUNNING/PROBES_COMPLETED/AGENT_COMPLETED: every failure path
   after start ends in FAILED (reason codes only — never exception text).
3. Reports never come out of a FAILED evaluation, and a missing stored
   artifact is a 503, never a fabricated report.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_event import (
    EVENT_EVALUATION_FAILED,
    EvaluationEventRepository,
)
from app.db.repositories.model import ModelRepository
from app.probes.errors import ProbeError
from app.schemas.internal import EvaluateModelPayload
from app.services.evaluation_enqueue import enqueue_and_record
from app.tasks.evaluate_pipeline import (
    PipelineInterruptedError,
    fail_stuck_running_evaluation,
    run_evaluation_pipeline,
)
from tests.fakes import FakeEvidenceStore, FakeReportStore

# --- 1. commit before enqueue ------------------------------------------------


def test_enqueue_and_record_commits_before_the_task_is_sent() -> None:
    """Old order: enqueue inside the open request transaction, commit after
    the response — a fast worker found no row (EvaluationNotVisibleError)."""
    order: list[str] = []
    payload = MagicMock(spec=EvaluateModelPayload)
    events = MagicMock()
    events.create.side_effect = lambda **_: order.append("event")

    enqueue_and_record(
        events,
        payload,
        evaluation_id=uuid.uuid4(),
        event_type="evaluation_created",
        commit_fn=lambda: order.append("commit"),
        enqueue_fn=lambda _p: order.append("enqueue") or "task-1",
        on_enqueued=lambda _t: None,
    )

    assert order == ["commit", "enqueue", "event"]


def test_create_evaluation_state_is_committed_when_enqueue_runs(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def _fake_enqueue(payload: EvaluateModelPayload) -> str:
        # A committed session has no open transaction left; a flushed-only
        # row (the old behaviour) is still inside one and invisible to the
        # worker's separate connection.
        seen["open_txn"] = db_session.in_transaction()
        seen["status"] = EvaluationRepository(db_session).get_by_id(payload.evaluation_id).status
        return "task-1"

    monkeypatch.setattr("app.services.evaluation_service.enqueue_evaluate_model", _fake_enqueue)
    model = api_client.post(
        "/v1/models", json={"hf_repo_id": f"org/order-{uuid.uuid4().hex[:8]}"}, headers=auth_headers
    )
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": "AI_AUTONOMOUS"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert seen == {"open_txn": False, "status": EvaluationStatus.PENDING}


# --- 2. no silent non-terminal state --------------------------------------


def _evaluation_at(db_session: Session, status: EvaluationStatus) -> uuid.UUID:
    model = ModelRepository(db_session).create(hf_repo_id=f"org/stuck-{uuid.uuid4().hex[:8]}")
    evaluation = EvaluationRepository(db_session).create(
        model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS
    )
    if status is not EvaluationStatus.PENDING:
        evaluation.status = status
    db_session.flush()
    return evaluation.id


@pytest.mark.parametrize(
    "status", [EvaluationStatus.PROBES_COMPLETED, EvaluationStatus.AGENT_COMPLETED]
)
def test_task_failure_after_probes_does_not_leave_evaluation_mid_pipeline(
    db_session: Session, status: EvaluationStatus
) -> None:
    """on_failure used to rescue RUNNING only: an unhandled error after
    PROBES_COMPLETED left the evaluation in a non-terminal state forever."""
    evaluation_id = _evaluation_at(db_session, status)

    assert fail_stuck_running_evaluation(db_session, evaluation_id) is True

    assert EvaluationRepository(db_session).get_by_id(evaluation_id).status is EvaluationStatus.FAILED
    failed = [
        e for e in EvaluationEventRepository(db_session).list_for_evaluation(evaluation_id)
        if e.event_type == EVENT_EVALUATION_FAILED
    ]
    assert [e.detail["from_status"] for e in failed] == [status.value]


def _payload(db_session: Session) -> EvaluateModelPayload:
    evaluation_id = _evaluation_at(db_session, EvaluationStatus.PENDING)
    row = EvaluationRepository(db_session).get_by_id(evaluation_id)
    model = ModelRepository(db_session).get_by_id(row.model_id)
    return EvaluateModelPayload(
        evaluation_id=evaluation_id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config={},
    )


def test_transient_error_after_start_is_not_retried_into_a_silent_skip(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ConnectionError after PENDING->RUNNING used to trigger Celery's
    autoretry; the retry hit 'pipeline_skip_not_pending', returned success,
    and the evaluation stayed RUNNING forever. It must now escape as a
    non-retryable error so on_failure marks it FAILED."""
    payload = _payload(db_session)

    def _boom(*_a: object, **_k: object) -> None:
        raise ConnectionError("hub reset")

    monkeypatch.setattr("app.tasks.evaluate_pipeline.run_all_probes", _boom)

    with pytest.raises(PipelineInterruptedError) as excinfo:
        run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    assert not isinstance(excinfo.value, (ConnectionError, TimeoutError))  # outside autoretry_for

    assert fail_stuck_running_evaluation(db_session, payload.evaluation_id) is True
    assert EvaluationRepository(db_session).get_by_id(payload.evaluation_id).status is EvaluationStatus.FAILED


# --- 3. API / report on failed or partial state ---------------------------


def test_failed_evaluation_reports_failed_and_never_yields_a_report(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload(db_session)
    monkeypatch.setattr(
        "app.tasks.evaluate_pipeline.run_all_probes",
        lambda *_a, **_k: (_ for _ in ()).throw(ProbeError("boom")),
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    store = FakeReportStore()
    monkeypatch.setattr("app.services.report_service.get_report_store", lambda settings: store)

    detail = api_client.get(f"/v1/evaluations/{payload.evaluation_id}", headers=auth_headers)
    assert detail.status_code == 200 and detail.json()["status"] == "FAILED"
    assert detail.json()["final_score"] is None

    for method in ("GET", "POST"):
        url = f"/v1/reports/{payload.evaluation_id}" + ("/generate" if method == "POST" else "")
        response = api_client.request(method, url, headers=auth_headers)
        assert response.status_code == 409, response.text
        assert response.json()["details"]["status"] == "FAILED"
    assert store.objects == {}


def test_report_with_missing_stored_artifact_is_503_not_fabricated(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.repositories.report import ReportRepository

    evaluation_id = _evaluation_at(db_session, EvaluationStatus.FINALIZED)
    ReportRepository(db_session).create(
        evaluation_id=evaluation_id,
        json_uri=f"s3://trustlens/reports/{evaluation_id}/v1/report.json",
        pdf_uri=None,
        version=1,
    )
    db_session.flush()
    store = FakeReportStore()  # empty: the artifact the row points at is gone
    monkeypatch.setattr("app.services.report_service.get_report_store", lambda settings: store)

    response = api_client.get(f"/v1/reports/{evaluation_id}", headers=auth_headers)

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
