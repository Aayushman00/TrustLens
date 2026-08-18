"""Model API CRUD tests (requires Postgres)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_create_and_get_model(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    repo_id = f"org/model-{uuid.uuid4().hex[:8]}"
    create = api_client.post(
        "/v1/models",
        json={"hf_repo_id": repo_id, "checksum": "abc123", "model_metadata": {"k": 1}},
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text
    assert create.headers.get("X-Request-ID")
    body = create.json()
    assert body["hf_repo_id"] == repo_id
    assert body["checksum"] == "abc123"
    model_id = body["id"]

    got = api_client.get(f"/v1/models/{model_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["id"] == model_id

    listed = api_client.get("/v1/models?limit=50", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["id"] == model_id for item in listed.json()["items"])


def test_duplicate_hf_repo_id_conflict(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    repo_id = f"org/dup-{uuid.uuid4().hex[:8]}"
    first = api_client.post("/v1/models", json={"hf_repo_id": repo_id}, headers=auth_headers)
    assert first.status_code == 201
    second = api_client.post("/v1/models", json={"hf_repo_id": repo_id}, headers=auth_headers)
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "CONFLICT"
    assert "details" in body


def test_get_missing_model_404(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    response = api_client.get("/v1/models/999999001", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_list_models_without_token_401(api_client: TestClient) -> None:
    response = api_client.get("/v1/models")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
