"""Health endpoint tests — structure with mocked dependency checks."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app, create_app
from app.routers.health import run_health_checks


def setup_function() -> None:
    get_settings.cache_clear()


def teardown_function() -> None:
    get_settings.cache_clear()


def test_app_imports() -> None:
    assert app is not None
    assert create_app() is not None


def test_health_structure_without_deps() -> None:
    with (
        patch("app.routers.health.check_postgres", return_value="skipped"),
        patch("app.routers.health.check_redis", return_value="skipped"),
        patch("app.routers.health.check_s3", return_value="skipped"),
    ):
        client = TestClient(app)
        response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "trustlens-api"
    assert body["checks"]["postgres"] == "skipped"


def test_health_returns_503_when_critical_deps_down() -> None:
    with (
        patch("app.routers.health.check_postgres", return_value="error"),
        patch("app.routers.health.check_redis", return_value="ok"),
        patch("app.routers.health.check_s3", return_value="ok"),
    ):
        client = TestClient(app)
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_run_health_checks_payload_keys() -> None:
    with (
        patch("app.routers.health.check_postgres", return_value="ok"),
        patch("app.routers.health.check_redis", return_value="ok"),
        patch("app.routers.health.check_s3", return_value="ok"),
    ):
        payload = run_health_checks()
    assert payload == {
        "status": "ok",
        "service": "trustlens-api",
        "checks": {"postgres": "ok", "redis": "ok", "minio": "ok"},
    }


def test_check_helpers_skip_when_url_absent() -> None:
    from app.core.db import check_postgres
    from app.core.redis_client import check_redis

    assert check_postgres(None) == "skipped"
    assert check_redis(None) == "skipped"
