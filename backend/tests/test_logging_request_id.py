"""Regression tests for the request_id logging-crash bug.

Root cause: RequestIdFilter was attached only to Logger objects (root,
trustlens.api, trustlens.api.access). A Logger's own .filters only run for
records that *originate* at that logger -- a record from an unrelated
logger (httpx's own logging.getLogger("httpx"), emitted from inside the
Starlette threadpool while a sync dataset-fetch endpoint runs httpx.Client)
merely propagates to root's handler, and only the *handler's* filters are
re-checked during propagation, never the ancestor logger's. The access-log
format string ("...request_id=%(request_id)s...") then raised because the
record never had a request_id attribute at all -- aborting whatever request
was in flight, even though the actual work (the dataset fetch) had already
succeeded, so the caller saw a false 500.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.api.middleware import RequestIdFilter, configure_request_id_logging
from app.routers.v1 import dataset_content as dataset_content_router
from app.storage.evidence_store import format_sha256


class _FakeDatasetContentStore:
    """Minimal store matching DatasetContentStore.put/get (no MinIO) --
    mirrors test_dataset_content_router.py's fixture of the same shape."""

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
def dataset_content_store_override(api_client: TestClient) -> _FakeDatasetContentStore:
    store = _FakeDatasetContentStore()
    api_client.app.dependency_overrides[dataset_content_router.get_dataset_content_store_dep] = (  # type: ignore[attr-defined]
        lambda: store
    )
    yield store
    api_client.app.dependency_overrides.pop(  # type: ignore[attr-defined]
        dataset_content_router.get_dataset_content_store_dep, None
    )


@pytest.fixture
def isolated_root_logger():
    """A throwaway logger tree so this test doesn't leak handlers/filters
    into other tests' root logger state."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_filters = list(root.filters)
    saved_level = root.level
    root.handlers = []
    root.filters = []
    yield root
    root.handlers = saved_handlers
    root.filters = saved_filters
    root.level = saved_level


def test_record_with_no_request_id_in_contextvar_does_not_crash_the_handler(
    isolated_root_logger,
):
    """Reproduces the exact crash shape: a record from an unrelated logger
    (simulating httpx's own "httpx" logger) reaching a handler whose format
    string references %(request_id)s, with the request_id contextvar never
    set for this thread/task. Before the fix, formatting this record raised
    (KeyError, surfaced by logging as a formatting error) -- now it must not."""
    import io

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter("%(levelname)s [%(name)s] request_id=%(request_id)s %(message)s")
    )
    isolated_root_logger.addHandler(handler)
    isolated_root_logger.setLevel(logging.INFO)

    configure_request_id_logging()
    assert any(isinstance(f, RequestIdFilter) for f in handler.filters)

    # A logger with no relation to trustlens.api/trustlens.api.access --
    # exactly the shape of httpx's own "HTTP Request: %s %s" log call, with
    # request_id_ctx never set in this context. Explicit level/disabled/
    # propagate (not just inherited from root) so this doesn't depend on
    # ambient state left by other tests in the suite -- test_migrations.py
    # runs alembic in-process, whose env.py calls logging.config.fileConfig
    # (disable_existing_loggers=True by default), which disables every
    # already-created logger including "httpx" for the rest of the pytest
    # session. That's alembic's own boilerplate behavior, not a bug, but it
    # means this test must not assume "httpx" is in its pristine state.
    unrelated_logger = logging.getLogger("httpx")
    unrelated_logger.disabled = False
    unrelated_logger.propagate = True
    unrelated_logger.setLevel(logging.INFO)
    unrelated_logger.info("HTTP Request: %s %s", "GET", "http://example.test/data.csv")

    output = stream.getvalue()
    assert "request_id=-" in output
    assert "HTTP Request: GET http://example.test/data.csv" in output


def test_dataset_fetch_returns_200_not_500_through_the_real_threadpool_path(
    api_client: TestClient,
    httpserver,
    _localhost_allowed_for_fetch,
    dataset_content_store_override,
) -> None:
    """End-to-end reproduction, not just the logging unit above: the
    dataset-fetch endpoint (a plain `def`, run by Starlette's real
    threadpool, not the event loop) performs a real httpx.Client().send()
    inside that worker thread. httpx's own logger emits an INFO "HTTP
    Request: ..." line with no request_id -- this must not crash the
    request into a false 500 for a fetch that actually succeeded.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_filters = list(root.filters)
    saved_level = root.level
    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s %(message)s",
            force=True,
        )
        configure_request_id_logging()
        httpx_logger = logging.getLogger("httpx")
        httpx_logger.disabled = False
        httpx_logger.propagate = True
        httpx_logger.setLevel(logging.INFO)

        httpserver.expect_request("/threadpool.csv").respond_with_data(
            b"text,label\nhello,1\nworld,0\n", content_type="text/csv"
        )
        url = httpserver.url_for("/threadpool.csv")

        resp = api_client.post("/v1/dataset-fetches", json={"source_url": url})

        assert resp.status_code == 201, resp.text
    finally:
        root.handlers = saved_handlers
        root.filters = saved_filters
        root.level = saved_level
