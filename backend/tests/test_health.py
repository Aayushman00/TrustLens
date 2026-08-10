"""Backend Phase 1 tests — health and imports only."""

from fastapi.testclient import TestClient

from app.main import app, create_app


def test_app_imports() -> None:
    assert app is not None
    assert create_app() is not None


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "trustlens-api"}
