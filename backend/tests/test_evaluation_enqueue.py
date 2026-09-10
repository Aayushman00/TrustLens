"""create_evaluation enqueues Celery task once (Phase 7); enqueue-failure
reconciliation (audit P1-4 — stuck PENDING has no reaper)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.repositories.evaluation import EvaluationRepository
from app.schemas.internal import EvaluateModelPayload
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.fakes import FakeEvidenceStore


def _create_model_and_pending_eval(
    api_client: TestClient,
    auth_headers: dict[str, str],
    *,
    enqueue_succeeds: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, str]:
    """Create a model + PENDING evaluation with a controlled enqueue outcome."""
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        (lambda payload: "fake-task-id") if enqueue_succeeds else (lambda payload: None),
    )
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/enq-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model_id, "evaluation_mode": "AI_ASSISTED"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "PENDING"
    return created.json()["id"], model_id


def _events(api_client: TestClient, auth_headers: dict[str, str], eval_id: str) -> list[dict]:
    resp = api_client.get(f"/v1/evaluations/{eval_id}/events", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def test_legacy_create_endpoint_marked_deprecated_in_openapi(api_client: TestClient) -> None:
    """Phase 6, Task 6.2: legacy POST /v1/evaluations stays functional but is
    flagged deprecated in the OpenAPI schema, ahead of Phase 7 removal."""
    schema = api_client.get("/openapi.json").json()
    assert schema["paths"]["/v1/evaluations"]["post"]["deprecated"] is True


def test_create_evaluation_enqueues_once(
    api_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[EvaluateModelPayload] = []

    def _fake_enqueue(payload: EvaluateModelPayload) -> str:
        calls.append(payload)
        return "fake-task-id"

    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        _fake_enqueue,
    )

    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/enq-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    hf_repo_id = model.json()["hf_repo_id"]

    response = api_client.post(
        "/v1/evaluations",
        json={"model_id": model_id, "evaluation_mode": "AI_ASSISTED"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert len(calls) == 1
    assert calls[0].model_ref == hf_repo_id
    assert calls[0].evaluation_mode.value == "AI_ASSISTED"
    assert str(calls[0].evaluation_id) == body["id"]


def test_enqueue_failure_is_recorded_as_confirmed_not_silent(
    api_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broker/enqueue failure must be observable immediately, not silent."""
    eval_id, _ = _create_model_and_pending_eval(
        api_client, auth_headers, enqueue_succeeds=False, monkeypatch=monkeypatch
    )
    events = _events(api_client, auth_headers, eval_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "evaluation_created"
    assert events[0]["detail"]["enqueued"] is False
    assert events[0]["detail"]["task_id"] is None


def test_reconcile_requeues_confirmed_failure_and_records_real_outcome(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_id, _ = _create_model_and_pending_eval(
        api_client, auth_headers, enqueue_succeeds=False, monkeypatch=monkeypatch
    )

    # Broker recovers before the operator retries.
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: "recovered-task-id",
    )
    resp = api_client.post(f"/v1/evaluations/{eval_id}/reconcile-enqueue", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    # Reconciliation never flips status itself — only the worker's own CAS does.
    assert resp.json()["status"] == "PENDING"

    events = _events(api_client, auth_headers, eval_id)
    assert len(events) == 2
    assert events[0]["detail"]["enqueued"] is False
    assert events[1]["event_type"] == "evaluation_requeued"
    assert events[1]["detail"]["enqueued"] is True
    assert events[1]["detail"]["task_id"] == "recovered-task-id"


def test_reconcile_has_no_role_gate(
    api_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-user local instance — reconcile-enqueue has no admin-only gate."""
    eval_id, _ = _create_model_and_pending_eval(
        api_client, auth_headers, enqueue_succeeds=False, monkeypatch=monkeypatch
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: "recovered-task-id",
    )
    resp = api_client.post(f"/v1/evaluations/{eval_id}/reconcile-enqueue", headers=auth_headers)
    assert resp.status_code == 200, resp.text


def test_reconcile_refuses_when_already_confirmed_enqueued(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legitimate (successfully enqueued) evaluation must never be touched,
    no matter how long it stays PENDING waiting on a worker."""
    eval_id, _ = _create_model_and_pending_eval(
        api_client, auth_headers, enqueue_succeeds=True, monkeypatch=monkeypatch
    )
    resp = api_client.post(f"/v1/evaluations/{eval_id}/reconcile-enqueue", headers=admin_headers)
    assert resp.status_code == 409, resp.text
    assert len(_events(api_client, auth_headers, eval_id)) == 1


def test_reconcile_refuses_when_not_pending(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    eval_id, _ = _create_model_and_pending_eval(
        api_client, auth_headers, enqueue_succeeds=False, monkeypatch=monkeypatch
    )
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref="org/does-not-matter",  # deliberate mismatch -> pipeline sets FAILED
        evaluation_mode=EvaluationMode.AI_ASSISTED,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()
    assert EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id)).status.value == "FAILED"

    resp = api_client.post(f"/v1/evaluations/{eval_id}/reconcile-enqueue", headers=admin_headers)
    assert resp.status_code == 409, resp.text


def test_reconcile_is_idempotent_no_duplicate_requeue(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After one successful reconciliation, a second call must refuse —
    preventing a duplicate re-enqueue / duplicate execution risk."""
    eval_id, _ = _create_model_and_pending_eval(
        api_client, auth_headers, enqueue_succeeds=False, monkeypatch=monkeypatch
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: "recovered-task-id",
    )
    first = api_client.post(f"/v1/evaluations/{eval_id}/reconcile-enqueue", headers=admin_headers)
    assert first.status_code == 200, first.text

    second = api_client.post(f"/v1/evaluations/{eval_id}/reconcile-enqueue", headers=admin_headers)
    assert second.status_code == 409, second.text
    # Still exactly 2 events (created + one requeue) — no duplicate requeue event.
    assert len(_events(api_client, auth_headers, eval_id)) == 2


def test_reconcile_nonexistent_evaluation_404(
    api_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    resp = api_client.post(
        f"/v1/evaluations/{uuid.uuid4()}/reconcile-enqueue", headers=admin_headers
    )
    assert resp.status_code == 404, resp.text
