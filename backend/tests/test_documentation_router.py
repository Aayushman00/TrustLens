"""API-layer tests for /v1/models/{id}/documentation — list, add, delete."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _create_model(api_client: TestClient, headers: dict[str, str]) -> int:
    repo_id = f"org/doc-{uuid.uuid4().hex[:8]}"
    resp = api_client.post("/v1/models", json={"hf_repo_id": repo_id}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_list_documentation_empty_for_manually_created_model(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    model_id = _create_model(api_client, auth_headers)
    resp = api_client.get(f"/v1/models/{model_id}/documentation", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


def test_add_user_documentation_roundtrip(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    model_id = _create_model(api_client, auth_headers)
    resp = api_client.post(
        f"/v1/models/{model_id}/documentation",
        json={
            "url": "https://arxiv.org/abs/1234.5678",
            "documentation_type": "research_paper",
            "title": "The Model Paper",
            "description": "Original publication.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source_kind"] == "user_supplied"
    assert body["documentation_type"] == "research_paper"
    assert body["url"] == "https://arxiv.org/abs/1234.5678"
    # Never fetched/hashed server-side — no SSRF guard for arbitrary URLs.
    assert body["retrieval_status"] == "not_applicable"
    assert body["documentation_content_hash"] is None

    listed = api_client.get(f"/v1/models/{model_id}/documentation", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json()["items"])


def test_delete_user_documentation_succeeds(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    model_id = _create_model(api_client, auth_headers)
    added = api_client.post(
        f"/v1/models/{model_id}/documentation",
        json={"url": "https://example.com/report.pdf", "documentation_type": "evaluation_report"},
        headers=auth_headers,
    )
    source_id = added.json()["id"]

    deleted = api_client.delete(
        f"/v1/models/{model_id}/documentation/{source_id}", headers=auth_headers
    )
    assert deleted.status_code == 204, deleted.text

    listed = api_client.get(f"/v1/models/{model_id}/documentation", headers=auth_headers)
    assert all(item["id"] != source_id for item in listed.json()["items"])


def test_documentation_for_unknown_model_404s(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = api_client.get("/v1/models/999999999/documentation", headers=auth_headers)
    assert resp.status_code == 404
