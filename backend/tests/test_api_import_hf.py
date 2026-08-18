"""API tests for POST /v1/models/import-hf — mocked adapter, no network calls."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ModelNotFoundError, NormalizedModelRecord


class _FakeAdapter:
    def __init__(
        self,
        *,
        record: NormalizedModelRecord | None = None,
        error: Exception | None = None,
    ) -> None:
        self._record = record
        self._error = error

    def resolve(self, ref: str, revision: str | None = None) -> NormalizedModelRecord:
        if self._error is not None:
            raise self._error
        assert self._record is not None
        return self._record


def _patch_adapter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    record: NormalizedModelRecord | None = None,
    error: Exception | None = None,
) -> _FakeAdapter:
    fake = _FakeAdapter(record=record, error=error)
    monkeypatch.setattr("app.services.model_service.HfHubModelAdapter", lambda: fake)
    return fake


def _sample_record(hf_repo_id: str = "distilbert-base-uncased") -> NormalizedModelRecord:
    return NormalizedModelRecord(
        hf_repo_id=hf_repo_id,
        revision="abc123",
        checksum="abc123",
        model_metadata={
            "source": "huggingface_hub",
            "pipeline_tag": "fill-mask",
            "card_text": "# Model Card\nSome text.",
            "files": ["config.json", "pytorch_model.bin"],
        },
    )


def test_import_hf_authenticated_returns_201_with_card_text(
    api_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_adapter(monkeypatch, record=_sample_record())
    response = api_client.post(
        "/v1/models/import-hf",
        json={"repo_id": "distilbert-base-uncased"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["hf_repo_id"] == "distilbert-base-uncased"
    assert body["revision"] == "abc123"
    assert body["checksum"] == "abc123"
    assert body["model_metadata"]["card_text"] == "# Model Card\nSome text."
    assert body["model_metadata"]["files"] == ["config.json", "pytorch_model.bin"]


def test_import_hf_by_url(
    api_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_adapter(monkeypatch, record=_sample_record(hf_repo_id="org/model-name"))
    response = api_client.post(
        "/v1/models/import-hf",
        json={"url": "https://huggingface.co/org/model-name"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["hf_repo_id"] == "org/model-name"


def test_import_hf_duplicate_repo_updates_existing_row(
    api_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-importing an existing hf_repo_id refreshes metadata in place (upsert), no duplicate row."""
    _patch_adapter(monkeypatch, record=_sample_record())
    first = api_client.post(
        "/v1/models/import-hf",
        json={"repo_id": "distilbert-base-uncased"},
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text
    model_id = first.json()["id"]

    updated = _sample_record()
    updated.model_metadata = {**updated.model_metadata, "card_text": "refreshed text"}
    updated.revision = "def456"
    updated.checksum = "def456"
    _patch_adapter(monkeypatch, record=updated)
    second = api_client.post(
        "/v1/models/import-hf",
        json={"repo_id": "distilbert-base-uncased"},
        headers=auth_headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == model_id
    assert second.json()["revision"] == "def456"
    assert second.json()["model_metadata"]["card_text"] == "refreshed text"

    listed = api_client.get("/v1/models", headers=auth_headers)
    matches = [m for m in listed.json()["items"] if m["hf_repo_id"] == "distilbert-base-uncased"]
    assert len(matches) == 1


def test_import_hf_without_token_401(api_client: TestClient) -> None:
    response = api_client.post(
        "/v1/models/import-hf",
        json={"repo_id": "distilbert-base-uncased"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_import_hf_non_hf_url_422_invalid_model_ref(
    api_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = api_client.post(
        "/v1/models/import-hf",
        json={"url": "https://example.com/fake"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_MODEL_REF"


def test_import_hf_missing_both_ref_fields_422(
    api_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = api_client.post("/v1/models/import-hf", json={}, headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_import_hf_both_ref_fields_422(
    api_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = api_client.post(
        "/v1/models/import-hf",
        json={"repo_id": "org/model", "url": "https://huggingface.co/org/model"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_import_hf_unknown_repo_404(
    api_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_adapter(
        monkeypatch,
        error=ModelNotFoundError(
            "Model 'org/missing' was not found on Hugging Face Hub",
            details={"hf_repo_id": "org/missing"},
        ),
    )
    response = api_client.post(
        "/v1/models/import-hf",
        json={"repo_id": "org/missing"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "MODEL_NOT_FOUND"
