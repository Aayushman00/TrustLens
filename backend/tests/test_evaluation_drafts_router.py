"""API-layer tests for the EvaluationDraft intake lifecycle
(POST /v1/evaluation-drafts, PUT .../{dimension}, POST .../{dimension}/confirm,
GET /v1/evaluation-drafts/{id}).

Uses the repo's real `api_client` fixture (DB-backed TestClient, see
tests/conftest.py) plus `seeded_model`/`seeded_dataset_content` for real
integration through the actual EvaluationDraftService -- only the model
inspection HTTP call is mocked (no live HF Hub access in tests), mirroring
Task 2.4's own service tests.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.inference.model_inspection import ModelLabelSnapshot

FAKE_SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1")


def test_full_draft_lifecycle(api_client: TestClient, seeded_model, seeded_dataset_content) -> None:
    created = api_client.post("/v1/evaluation-drafts", json={"model_id": seeded_model.id}).json()
    draft_id = created["id"]
    assert created["status"] == "incomplete"

    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        validate_resp = api_client.put(
            f"/v1/evaluation-drafts/{draft_id}/FAIRNESS",
            json={
                "dataset_content_id": str(seeded_dataset_content.id),
                "text_column": "text",
                "target_column": "label",
                "sensitive_column": "group",
                "label_mapping": [
                    {"dataset_value": "pos", "model_label_index": 1},
                    {"dataset_value": "neg", "model_label_index": 0},
                ],
                "min_group_n": 2,
            },
        )
    assert validate_resp.status_code == 200, validate_resp.text
    assert validate_resp.json()["ok"]

    confirm_resp = api_client.post(f"/v1/evaluation-drafts/{draft_id}/FAIRNESS/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["fairness_confirmed"]

    get_resp = api_client.get(f"/v1/evaluation-drafts/{draft_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["fairness_confirmed"]


def test_create_draft_unknown_model_returns_404(api_client: TestClient) -> None:
    resp = api_client.post("/v1/evaluation-drafts", json={"model_id": 999999})
    assert resp.status_code == 404


def test_get_draft_unknown_id_returns_404(api_client: TestClient) -> None:
    resp = api_client.get(f"/v1/evaluation-drafts/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_confirm_dimension_without_prior_validation_returns_422(api_client: TestClient, seeded_model) -> None:
    created = api_client.post("/v1/evaluation-drafts", json={"model_id": seeded_model.id}).json()
    resp = api_client.post(f"/v1/evaluation-drafts/{created['id']}/FAIRNESS/confirm")
    assert resp.status_code == 422


def test_target_values_discovery(api_client: TestClient, seeded_model, seeded_dataset_content) -> None:
    created = api_client.post("/v1/evaluation-drafts", json={"model_id": seeded_model.id}).json()
    resp = api_client.get(
        f"/v1/evaluation-drafts/{created['id']}/FAIRNESS/target-values",
        params={"dataset_content_id": str(seeded_dataset_content.id), "target_column": "label"},
    )
    assert resp.status_code == 200, resp.text
    assert set(resp.json()["values"]) == {"pos", "neg"}


def test_target_values_discovery_unknown_column_returns_422_not_500(
    api_client: TestClient, seeded_model, seeded_dataset_content
) -> None:
    created = api_client.post("/v1/evaluation-drafts", json={"model_id": seeded_model.id}).json()
    resp = api_client.get(
        f"/v1/evaluation-drafts/{created['id']}/FAIRNESS/target-values",
        params={"dataset_content_id": str(seeded_dataset_content.id), "target_column": "not_a_column"},
    )
    assert resp.status_code == 422, resp.text


def test_update_dimension_unknown_dimension_returns_422_not_500(api_client: TestClient, seeded_model) -> None:
    created = api_client.post("/v1/evaluation-drafts", json={"model_id": seeded_model.id}).json()
    resp = api_client.put(
        f"/v1/evaluation-drafts/{created['id']}/NOT_A_DIMENSION",
        json={
            "dataset_content_id": str(uuid.uuid4()),
            "text_column": "text",
            "target_column": "label",
            "label_mapping": [],
        },
    )
    assert resp.status_code == 422
