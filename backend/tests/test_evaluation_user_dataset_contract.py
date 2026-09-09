"""Evaluation-create API tests for the user_dataset Fairness contract.

Covers: mutual exclusivity with pairing_id/dataset_key/contract_kind=proxy_lr
and missing-column validation.
"""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.routers.v1.datasets import get_dataset_store_dep
from app.schemas.internal import EvaluateModelPayload
from tests.fakes import FakeDatasetStore

_CSV = (
    b"text,label,gender\n"
    b"great product,1,Female\n"
    b"bad product,0,Male\n"
    b"ok product,1,Male\n"
    b"terrible,0,Female\n"
)


@pytest.fixture
def dataset_store_override(api_client: TestClient) -> FakeDatasetStore:
    store = FakeDatasetStore()
    api_client.app.dependency_overrides[get_dataset_store_dep] = lambda: store  # type: ignore[attr-defined]
    yield store
    api_client.app.dependency_overrides.pop(get_dataset_store_dep, None)  # type: ignore[attr-defined]


def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> list[EvaluateModelPayload]:
    calls: list[EvaluateModelPayload] = []

    def _fake_enqueue(payload: EvaluateModelPayload) -> str:
        calls.append(payload)
        return "fake-task-id"

    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        _fake_enqueue,
    )
    return calls


def _create_model(api_client: TestClient, headers: dict[str, str]) -> int:
    resp = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/user-dataset-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _upload_dataset(api_client: TestClient, headers: dict[str, str]) -> str:
    resp = api_client.post(
        "/v1/datasets",
        files={"file": ("sample.csv", io.BytesIO(_CSV), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_user_dataset_contract_usable(
    api_client: TestClient,
    auth_headers: dict[str, str],
    dataset_store_override: FakeDatasetStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_enqueue(monkeypatch)
    model_id = _create_model(api_client, auth_headers)
    dataset_id = _upload_dataset(api_client, auth_headers)

    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model_id,
            "evaluation_mode": "AI_AUTONOMOUS",
            "user_dataset_id": dataset_id,
            "target_column": "label",
            "group_column": "gender",
            "text_column": "text",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    contract = created.json()["probe_config"]["evaluation_contract"]
    assert contract["kind"] == "user_dataset"
    assert contract["user_dataset_id"] == dataset_id
    assert contract["target_column"] == "label"
    assert contract["group_column"] == "gender"
    assert contract["text_column"] == "text"
    # Never presented as an approved/certified benchmark.
    assert contract["kind"] != "pairing"
    assert contract["pairing_id"] is None


def test_missing_columns_rejected_422(
    api_client: TestClient,
    auth_headers: dict[str, str],
    dataset_store_override: FakeDatasetStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_enqueue(monkeypatch)
    model_id = _create_model(api_client, auth_headers)
    dataset_id = _upload_dataset(api_client, auth_headers)

    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model_id,
            "evaluation_mode": "AI_AUTONOMOUS",
            "user_dataset_id": dataset_id,
            "target_column": "label",
            # group_column/text_column intentionally omitted
        },
        headers=auth_headers,
    )
    assert created.status_code == 422, created.text


def test_user_dataset_mutually_exclusive_with_pairing_id(
    api_client: TestClient,
    auth_headers: dict[str, str],
    dataset_store_override: FakeDatasetStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_enqueue(monkeypatch)
    model_id = _create_model(api_client, auth_headers)
    dataset_id = _upload_dataset(api_client, auth_headers)

    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model_id,
            "evaluation_mode": "AI_AUTONOMOUS",
            "user_dataset_id": dataset_id,
            "target_column": "label",
            "group_column": "gender",
            "text_column": "text",
            "pairing_id": "hatexplain_bert_v1",
        },
        headers=auth_headers,
    )
    assert created.status_code == 422, created.text


def test_user_dataset_reference_has_no_ownership_gate(
    api_client: TestClient,
    auth_headers: dict[str, str],
    dataset_store_override: FakeDatasetStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-user local instance — no ownership concept; any uploaded
    dataset can be referenced by any evaluation."""
    _stub_enqueue(monkeypatch)
    dataset_id = _upload_dataset(api_client, auth_headers)
    model_id = _create_model(api_client, auth_headers)

    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model_id,
            "evaluation_mode": "AI_AUTONOMOUS",
            "user_dataset_id": dataset_id,
            "target_column": "label",
            "group_column": "gender",
            "text_column": "text",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
