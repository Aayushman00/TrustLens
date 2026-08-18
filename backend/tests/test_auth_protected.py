"""Protected /v1 routes require a valid Bearer access token."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.models import User


def test_models_without_token_401(api_client: TestClient) -> None:
    response = api_client.get("/v1/models")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_models_with_expired_token_401_invalid_token(
    api_client: TestClient, seeded_users: dict[str, tuple[User, str]]
) -> None:
    """Expired access token → 401 INVALID_TOKEN (Phase 24 security smoke).

    Minted with the app's own secret/algorithm and a real user id, so expiry —
    not signature or user lookup — is the only reason for rejection.
    """
    user, _ = seeded_users["researcher"]
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "type": "access",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=15),
            "jti": str(uuid.uuid4()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = api_client.get("/v1/models", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "INVALID_TOKEN"
    assert "expired" in body["message"].lower()


def test_models_with_valid_token_200(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    response = api_client.get("/v1/models", headers=auth_headers)
    assert response.status_code == 200


def test_models_with_garbage_token_401_invalid_token(api_client: TestClient) -> None:
    response = api_client.get("/v1/models", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


def test_evaluations_without_token_401(api_client: TestClient) -> None:
    response = api_client.get("/v1/evaluations")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_evaluations_with_valid_token_200(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    response = api_client.get("/v1/evaluations", headers=auth_headers)
    assert response.status_code == 200


def test_leaderboard_requires_auth_then_lists(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Bearer kept on the leaderboard for MVP (Phase 22) — 401 without a token."""
    no_auth = api_client.get("/v1/leaderboard")
    assert no_auth.status_code == 401

    with_auth = api_client.get("/v1/leaderboard", headers=auth_headers)
    assert with_auth.status_code == 200
    assert "items" in with_auth.json()
