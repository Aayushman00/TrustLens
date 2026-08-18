"""POST /v1/auth/login (requires Postgres)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_success_returns_token_pair(api_client: TestClient, seeded_users) -> None:
    user, password = seeded_users["researcher"]
    response = api_client.post("/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert isinstance(body["refresh_token"], str) and body["refresh_token"]
    assert body["expires_in"] == 15 * 60


def test_login_bad_password_401(api_client: TestClient, seeded_users) -> None:
    user, _ = seeded_users["researcher"]
    response = api_client.post("/v1/auth/login", json={"email": user.email, "password": "wrong-password"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"
    assert body["message"] == "Invalid email or password"


def test_login_unknown_email_401_generic_message(api_client: TestClient) -> None:
    """Same generic message for unknown email as for a wrong password — no email enumeration."""
    response = api_client.post(
        "/v1/auth/login",
        json={"email": "nobody@trustlens.local", "password": "whatever"},
    )
    assert response.status_code == 401
    assert response.json()["message"] == "Invalid email or password"


def test_login_response_never_includes_password_hash(api_client: TestClient, seeded_users) -> None:
    user, password = seeded_users["admin"]
    response = api_client.post("/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200
    assert "password_hash" not in response.json()


def test_me_returns_current_user_without_password_hash(api_client: TestClient, seeded_users) -> None:
    user, password = seeded_users["researcher"]
    login = api_client.post("/v1/auth/login", json={"email": user.email, "password": password})
    token = login.json()["access_token"]
    response = api_client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["role"] == "researcher"
    assert "password_hash" not in body
