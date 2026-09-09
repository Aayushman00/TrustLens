"""Structured error shape tests (404 / 409 / 422 / 501)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import create_app


def test_import_hf_without_body_422() -> None:
    """POST /v1/models/import-hf requires no auth — a missing body is a 422."""
    client = TestClient(create_app())
    response = client.post("/v1/models/import-hf")
    assert response.status_code == 422
    assert response.headers.get("X-Request-ID")


def test_not_found_model_without_auth_404(api_client: TestClient) -> None:
    """Single-user local instance — no auth required; an unknown id still 404s."""
    response = api_client.get("/v1/models/999999")
    assert response.status_code == 404
    body = response.json()
    assert "code" in body and "message" in body and "details" in body
    assert response.headers.get("X-Request-ID")


def test_request_id_propagated() -> None:
    client = TestClient(create_app())
    rid = str(uuid.uuid4())
    response = client.get("/health", headers={"X-Request-ID": rid})
    assert response.headers.get("X-Request-ID") == rid
