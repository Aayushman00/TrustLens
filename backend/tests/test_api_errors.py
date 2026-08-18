"""Structured error shape tests (401 / 404 / 409 / 422 / 501)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import create_app


def test_login_missing_body_returns_422() -> None:
    client = TestClient(create_app())
    response = client.post("/v1/auth/login")
    assert response.status_code == 422
    assert response.headers.get("X-Request-ID")
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "message" in body


def test_import_hf_without_token_401() -> None:
    """POST /v1/models/import-hf (Phase 6, live) still enforces auth first."""
    client = TestClient(create_app())
    response = client.post("/v1/models/import-hf")
    assert response.status_code == 401
    assert response.headers.get("X-Request-ID")
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"


def test_not_found_model_without_token_401() -> None:
    """Protected routes reject unauthenticated requests before touching the DB."""
    client = TestClient(create_app())
    response = client.get("/v1/models/999999")
    assert response.status_code == 401
    body = response.json()
    assert "code" in body and "message" in body and "details" in body
    assert response.headers.get("X-Request-ID")


def test_request_id_propagated() -> None:
    client = TestClient(create_app())
    rid = str(uuid.uuid4())
    response = client.get("/health", headers={"X-Request-ID": rid})
    assert response.headers.get("X-Request-ID") == rid
