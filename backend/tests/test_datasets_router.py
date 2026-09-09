"""API-layer tests for /v1/datasets — upload/list/get/group-discovery."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.routers.v1.datasets import get_dataset_store_dep
from tests.fakes import FakeDatasetStore

_CSV = (
    b"text,label,gender\n"
    b"great product,1,Female\n"
    b"bad product,0,Male\n"
    b"ok product,1,Male\n"
    b"terrible,0,Female\n"
)


@pytest.fixture
def dataset_store_override(api_client: TestClient) -> FakeDatasetStore:
    store = FakeDatasetStore()
    api_client.app.dependency_overrides[get_dataset_store_dep] = lambda: store  # type: ignore[attr-defined]
    yield store
    api_client.app.dependency_overrides.pop(get_dataset_store_dep, None)  # type: ignore[attr-defined]


def _upload(api_client: TestClient, headers: dict[str, str], *, filename: str = "sample.csv"):
    return api_client.post(
        "/v1/datasets",
        files={"file": (filename, io.BytesIO(_CSV), "text/csv")},
        headers=headers,
    )


def test_upload_list_get_roundtrip(
    api_client: TestClient,
    auth_headers: dict[str, str],
    dataset_store_override: FakeDatasetStore,
) -> None:
    resp = _upload(api_client, auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["filename"] == "sample.csv"
    assert body["format"] == "csv"
    assert body["row_count"] == 4
    assert body["content_hash"].startswith("sha256:")
    names = {c["name"] for c in body["columns"]}
    assert names == {"text", "label", "gender"}

    listed = api_client.get("/v1/datasets", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json()["items"])

    fetched = api_client.get(f"/v1/datasets/{body['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_group_discovery_reflects_actual_file_values(
    api_client: TestClient,
    auth_headers: dict[str, str],
    dataset_store_override: FakeDatasetStore,
) -> None:
    resp = _upload(api_client, auth_headers)
    dataset_id = resp.json()["id"]

    groups = api_client.get(
        f"/v1/datasets/{dataset_id}/groups",
        params={"column": "gender"},
        headers=auth_headers,
    )
    assert groups.status_code == 200, groups.text
    body = groups.json()
    values = {g["value"]: g["count"] for g in body["observed_groups"]}
    assert values == {"Male": 2, "Female": 2}
    assert body["missing_count"] == 0


def test_dataset_read_has_no_ownership_gate(
    api_client: TestClient,
    auth_headers: dict[str, str],
    dataset_store_override: FakeDatasetStore,
) -> None:
    """Single-user local instance — no ownership concept; any uploaded
    dataset is readable, never a 403."""
    resp = _upload(api_client, auth_headers)
    dataset_id = resp.json()["id"]

    fetched = api_client.get(f"/v1/datasets/{dataset_id}", headers=auth_headers)
    assert fetched.status_code == 200


def test_non_csv_upload_rejected(
    api_client: TestClient,
    auth_headers: dict[str, str],
    dataset_store_override: FakeDatasetStore,
) -> None:
    resp = api_client.post(
        "/v1/datasets",
        files={"file": ("sample.txt", io.BytesIO(_CSV), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_upload_without_store_configured_fails_closed(
    api_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When S3/MinIO is not configured, upload must fail rather than silently
    pretend to store the file (never a fake success)."""
    from app.routers.v1 import datasets as datasets_router

    api_client.app.dependency_overrides[datasets_router.get_dataset_store_dep] = (  # type: ignore[attr-defined]
        lambda: None
    )
    try:
        resp = _upload(api_client, auth_headers)
        assert resp.status_code == 422
    finally:
        api_client.app.dependency_overrides.pop(  # type: ignore[attr-defined]
            datasets_router.get_dataset_store_dep, None
        )
