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


def test_post_dataset_fetches_rejects_html_response(
    api_client: TestClient,
    httpserver,
    _localhost_allowed_for_fetch,
    dataset_content_store_override: FakeDatasetContentStore,
    db_session,
) -> None:
    """A webpage returned where a raw CSV was expected (e.g. a Hugging Face URL
    resolving to an HTML page) must be rejected at the ingestion boundary --
    not accepted as a bogus one-column "<!doctype html>" dataset."""
    html_body = b"<!doctype html>\n<html><head><title>Not a dataset</title></head><body>hi</body></html>\n"
    httpserver.expect_request("/not-a-dataset").respond_with_data(
        html_body, content_type="text/csv"  # server lies about content-type on purpose
    )
    url = httpserver.url_for("/not-a-dataset")

    resp = api_client.post("/v1/dataset-fetches", json={"source_url": url})

    assert resp.status_code == 422, resp.text
    assert "html" in resp.json()["message"].lower()

    from app.db.models import DatasetContent, DatasetFetchEvent

    assert db_session.query(DatasetContent).count() == 0

    events = db_session.query(DatasetFetchEvent).filter_by(source_url=url).all()
    assert len(events) == 1
    assert events[0].resolved_content_id is None
    assert events[0].error_message is not None
    assert "not a valid csv" in events[0].error_message.lower() or "html" in events[0].error_message.lower()


def test_post_dataset_fetches_rejects_json_response(
    api_client: TestClient,
    httpserver,
    _localhost_allowed_for_fetch,
    dataset_content_store_override: FakeDatasetContentStore,
) -> None:
    """Audit finding: a JSON API-error payload (also valid UTF-8 text) must be
    rejected the same way as HTML, not silently parsed as a one-column CSV."""
    httpserver.expect_request("/api-error").respond_with_data(
        b'{"error": "not found"}', content_type="text/csv"
    )
    url = httpserver.url_for("/api-error")

    resp = api_client.post("/v1/dataset-fetches", json={"source_url": url})

    assert resp.status_code == 422, resp.text


def test_post_dataset_fetches_rejects_git_lfs_pointer(
    api_client: TestClient,
    httpserver,
    _localhost_allowed_for_fetch,
    dataset_content_store_override: FakeDatasetContentStore,
    db_session,
) -> None:
    """A dataset URL backed by Git LFS (e.g. a GitHub raw URL for an
    LFS-tracked file, or a Hugging Face resolve URL) serves the LFS pointer
    text, not the actual dataset -- must be rejected at ingestion, not
    stored as DatasetContent and not surfaced to column/label-mapping UI."""
    pointer_body = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"b" * 64 + b"\n"
        b"size 3421431\n"
    )
    httpserver.expect_request("/tweets.csv").respond_with_data(
        pointer_body, content_type="text/plain; charset=utf-8"
    )
    url = httpserver.url_for("/tweets.csv")

    resp = api_client.post("/v1/dataset-fetches", json={"source_url": url})

    assert resp.status_code == 422, resp.text
    assert "git lfs" in resp.json()["message"].lower()

    from app.db.models import DatasetContent, DatasetFetchEvent

    # No DatasetContent must ever be created for pointer bytes -- there is
    # nothing for a column-role/label-mapping UI to load.
    assert db_session.query(DatasetContent).count() == 0

    events = db_session.query(DatasetFetchEvent).filter_by(source_url=url).all()
    assert len(events) == 1
    assert events[0].resolved_content_id is None
    assert events[0].error_message is not None
    assert "git lfs" in events[0].error_message.lower()


def test_post_dataset_fetches_accepts_real_csv(
    api_client: TestClient,
    httpserver,
    _localhost_allowed_for_fetch,
    dataset_content_store_override: FakeDatasetContentStore,
    db_session,
) -> None:
    """Regression guard: the Git LFS pointer check must not reject a normal
    CSV dataset -- normal ingestion keeps working end to end."""
    csv_body = b"text,label\nhello,1\nworld,0\n"
    httpserver.expect_request("/real.csv").respond_with_data(
        csv_body, content_type="text/csv"
    )
    url = httpserver.url_for("/real.csv")

    resp = api_client.post("/v1/dataset-fetches", json={"source_url": url})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["row_count"] == 2
    assert {c["name"] for c in body["columns"]} == {"text", "label"}

    from app.db.models import DatasetContent

    assert db_session.query(DatasetContent).count() == 1
