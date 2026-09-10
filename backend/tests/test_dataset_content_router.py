"""API-layer tests for POST /v1/dataset-fetches and GET /v1/dataset-contents/{id}.

Uses the repo's real `api_client` fixture (DB-backed TestClient, see
tests/conftest.py) and a fake DatasetContentStore override so no live
MinIO/S3 is required -- mirrors the pattern in test_datasets_router.py.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.routers.v1 import dataset_content as dataset_content_router
from app.storage.evidence_store import format_sha256


class FakeDatasetContentStore:
    """Minimal store matching DatasetContentStore.put/get for unit tests (no MinIO)."""

    def __init__(self, bucket: str = "trustlens") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}

    def put(self, data: bytes, *, format: str) -> tuple[str, str]:
        digest = format_sha256(data)
        key = f"datasets/{digest.removeprefix('sha256:')}"
        self.objects[key] = data
        return f"s3://{self.bucket}/{key}", digest

    def get(self, storage_uri: str) -> bytes:
        prefix = f"s3://{self.bucket}/"
        key = storage_uri[len(prefix) :]
        return self.objects[key]


@pytest.fixture
def dataset_content_store_override(api_client: TestClient) -> FakeDatasetContentStore:
    store = FakeDatasetContentStore()
    api_client.app.dependency_overrides[dataset_content_router.get_dataset_content_store_dep] = (  # type: ignore[attr-defined]
        lambda: store
    )
    yield store
    api_client.app.dependency_overrides.pop(  # type: ignore[attr-defined]
        dataset_content_router.get_dataset_content_store_dep, None
    )


def test_post_dataset_fetches_creates_content(
    api_client: TestClient,
    httpserver,
    _localhost_allowed_for_fetch,
    dataset_content_store_override: FakeDatasetContentStore,
) -> None:
    httpserver.expect_request("/data.csv").respond_with_data(
        b"text,label\nhello,0\nworld,1\n", content_type="text/csv"
    )
    url = httpserver.url_for("/data.csv")

    resp = api_client.post("/v1/dataset-fetches", json={"source_url": url})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["row_count"] == 2
    assert {"name": "text", "inferred_type": "string"} in body["columns"] or any(
        c["name"] == "text" for c in body["columns"]
    )

    # re-fetching the same content dedupes to the same DatasetContent
    resp2 = api_client.post("/v1/dataset-fetches", json={"source_url": url})
    assert resp2.json()["id"] == body["id"]


def test_get_dataset_content_by_id(
    api_client: TestClient,
    httpserver,
    _localhost_allowed_for_fetch,
    dataset_content_store_override: FakeDatasetContentStore,
) -> None:
    httpserver.expect_request("/data2.csv").respond_with_data(b"a,b\n1,2\n", content_type="text/csv")
    url = httpserver.url_for("/data2.csv")
    created = api_client.post("/v1/dataset-fetches", json={"source_url": url}).json()

    resp = api_client.get(f"/v1/dataset-contents/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["content_hash"] == created["content_hash"]


def test_get_dataset_content_not_found(
    api_client: TestClient,
    dataset_content_store_override: FakeDatasetContentStore,
) -> None:
    resp = api_client.get(f"/v1/dataset-contents/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_post_dataset_fetches_rejects_ssrf_target(
    api_client: TestClient,
    dataset_content_store_override: FakeDatasetContentStore,
) -> None:
    resp = api_client.post("/v1/dataset-fetches", json={"source_url": "http://127.0.0.1/x.csv"})
    assert resp.status_code == 422
