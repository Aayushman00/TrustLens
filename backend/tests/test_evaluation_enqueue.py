"""create_evaluation enqueues Celery task once (Phase 7)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.schemas.internal import EvaluateModelPayload


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
