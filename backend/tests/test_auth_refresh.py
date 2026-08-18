"""POST /v1/auth/refresh — rotation and invalid-token handling."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _login(api_client: TestClient, email: str, password: str) -> dict:
    response = api_client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_refresh_rotates_access_and_refresh_tokens(api_client: TestClient, seeded_users) -> None:
    user, password = seeded_users["researcher"]
    tokens = _login(api_client, user.email, password)

    response = api_client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["access_token"] != tokens["access_token"]
    assert rotated["refresh_token"] != tokens["refresh_token"]
    assert rotated["token_type"] == "bearer"

    # The rotated access token is itself usable on a protected route.
    me = api_client.get("/v1/auth/me", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    assert me.status_code == 200


def test_refresh_with_garbage_token_401_invalid_token(api_client: TestClient) -> None:
    response = api_client.post("/v1/auth/refresh", json={"refresh_token": "not-a-real-jwt"})
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


def test_refresh_with_access_token_rejected(api_client: TestClient, seeded_users) -> None:
    """An access token has type=access — refresh must reject it as the wrong token type."""
    user, password = seeded_users["researcher"]
    tokens = _login(api_client, user.email, password)

    response = api_client.post("/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
