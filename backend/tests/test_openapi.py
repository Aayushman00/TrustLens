"""OpenAPI surface — docs render and all v1 paths are present (no stubs left)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

IMPLEMENTED_PATHS = {
    "/health",
    "/v1/auth/login",
    "/v1/auth/refresh",
    "/v1/auth/me",
    "/v1/models",
    "/v1/models/{model_id}",
    "/v1/models/import-hf",
    "/v1/evaluations",
    "/v1/evaluations/{evaluation_id}",
    "/v1/evaluations/{evaluation_id}/finalize",
    "/v1/evaluations/{evaluation_id}/human-review",
    "/v1/evaluations/{evaluation_id}/publish",
    "/v1/evaluations/{evaluation_id}/unpublish",
    "/v1/reports/{evaluation_id}",
    "/v1/reports/{evaluation_id}/generate",
    "/v1/leaderboard",
}


def test_docs_and_openapi_ok() -> None:
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 200
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = set(schema["paths"].keys())
    assert IMPLEMENTED_PATHS.issubset(paths)


def test_openapi_declares_bearer_scheme_on_protected_routes() -> None:
    client = TestClient(create_app())
    schema = client.get("/openapi.json").json()
    security_schemes = schema.get("components", {}).get("securitySchemes", {})
    assert any(s.get("type") == "http" and s.get("scheme") == "bearer" for s in security_schemes.values())

    models_get = schema["paths"]["/v1/models"]["get"]
    assert models_get.get("security"), "GET /v1/models should require a security scheme"

    login_post = schema["paths"]["/v1/auth/login"]["post"]
    assert not login_post.get("security"), "POST /v1/auth/login must stay public"
