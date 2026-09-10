# TrustLens V1 Dataset/Contract Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace TrustLens's pairing/registry/proxy_lr dataset architecture with a content-addressed `DatasetContent`/`DatasetFetchEvent` model, per-dimension optional Fairness/Robustness configuration via a server-side validated draft, a redesigned `EvaluationContractV1`, and version-gated confidence/FRIES scoring — without breaking the currently-working evaluation path until the new path is proven.

**Architecture:** Additive-first, incremental cutover. Each phase ships working, tested software alongside the still-functioning legacy path. Nothing legacy is deleted until Phase 7, after the new path has fully replaced it in Phase 6.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), Celery + Redis (worker), MinIO/boto3 (object storage), Pydantic v2 (schemas), React + TypeScript (frontend), pytest (backend tests), Vitest (frontend tests).

**Spec:** This document's Global Constraints section compiles every architecture decision locked across the preceding design conversation (no separate spec file exists — this plan *is* the spec's durable record).

## Global Constraints

- One `Evaluation` may independently configure Fairness and/or Robustness; either may be `null` (NOT_APPLICABLE), never forced to both.
- Dataset identity = SHA-256 of raw bytes (`DatasetContent.content_hash`), never a URL. `DatasetFetchEvent` records provenance (source_url, timestamps, HTTP status) separately, append-only.
- `DatasetContent` is immutable once created: no UPDATE path, ever. Storage key is content-addressed: `datasets/{content_hash}` (no extension, no client-supplied filename).
- Fairness declares `text_column`, `target_column`, `sensitive_column` (exactly one). Robustness declares `text_column`, `target_column` only — no sensitive attribute, no `evaluation_domain` field at all (removed, not demoted).
- Both dimensions require an explicit, user-confirmed `label_mapping` (`dataset_value -> model_label_index`); never auto-applied without a confirm action, even when a normalized-string match looks confident.
- Model compatibility at intake uses `AutoConfig`-only inspection (no weights) against the frozen `resolved_model_sha`; the worker re-loads the full model and hard-fails on any `num_labels`/`id2label` mismatch against the frozen `model_label_snapshot`.
- `model_label_snapshot`/`resolved_model_sha` are frozen **once, at the Evaluation level**, shared by both dimensions. A model-revision change before draft consumption invalidates the whole draft and every previously-confirmed dimension — never partial/mixed snapshots.
- `min_group_n` is user-configurable per Fairness draft (default 30), positive-integer validation only (no invented hard floor). The intake-time group-count warning is a pure feasibility check against the user's own chosen value — never framed as a reliability/uncertainty signal (that's `wide_ci`, computed post-inference, in the worker).
- Validated intake lives in a mutable `evaluation_draft` (+ per-dimension `draft_dimension_config` rows) until consumed atomically by `POST /v1/evaluations`, which freezes everything into `EvaluationContractV1` and marks the draft `consumed` (retained, never deleted, for audit).
- NOT_APPLICABLE dimensions are excluded from confidence aggregation and the FRIES O/S/D aspect count for evaluations created under the new `methodology_version`; legacy evaluations keep their original semantics forever (`methodology_version` is stamped server-side at Evaluation creation, immutable, never retroactively reinterpreted).
- `ReportV1`/`ReportRead.methodology_version` is required and non-null for every newly generated report; `ReportRead.methodology_version` is `str | None` on the read path only, `None` meaning "legacy report generated before this field existed" — existing stored `report.json` blobs in MinIO are never rewritten.
- PostgreSQL, MinIO, Celery, Redis, and the separate worker service all remain. Celery Beat is removed (no registered periodic job exists anywhere in the codebase today).
- No embeddings, vector DB, LLM claim extraction, semantic retrieval, or documentation-to-behavior verification anywhere in this plan — out of V1 scope entirely.
- `pairing.py`, `datasets/registry.py`'s registry machinery, `robustness_compat.py`, `proxy_lr`, `dataset_key`, `EvaluationOptionsRead`, the Hatexplain input adapter, and the old flat `EvaluationContractV1` shape are all deleted in Phase 7 — never preserved merely because they already exist.

---

## Phase 1 — DatasetContent + DatasetFetchEvent + URL ingestion/storage/validation

**Rollback/safety boundary:** Entirely additive — new tables, new storage prefix, new endpoints. Nothing existing reads or writes these tables yet. Safe to deploy and even leave unused; a revert is a straight `alembic downgrade` with no data-loss risk to any existing evaluation.

**What old behavior remains temporarily:** The entire existing pairing/registry/user_dataset evaluation-creation path keeps working unchanged. `UserDataset`/`DatasetStore` (the old upload-only path) stays in place and in use.

**What becomes impossible after this phase:** Nothing — this phase only adds capability. It does not yet wire anything into evaluation creation.

### Task 1.1: `DatasetContent` and `DatasetFetchEvent` models + migration

**Files:**
- Modify: `backend/app/db/models.py` (add two new classes, alongside existing `UserDataset`/`DocumentationSource`)
- Create: `backend/alembic/versions/XXX_add_dataset_content.py` (revision id follows the next sequential number after the latest existing migration — check `backend/alembic/versions/` for the current head before creating)
- Test: `backend/tests/test_dataset_content_models.py`

**Interfaces:**
- Produces: `DatasetContent` (columns: `id: UUID PK`, `content_hash: str(64) UNIQUE NOT NULL`, `storage_uri: str NOT NULL`, `byte_size: int NOT NULL`, `format: str(32) NOT NULL`, `row_count: int NOT NULL`, `columns: JSONB NOT NULL`, `schema_sniff_version: int NOT NULL default 1`, `created_at: datetime`), `DatasetFetchEvent` (columns: `id: UUID PK`, `source_url: Text NOT NULL`, `requested_at: datetime NOT NULL`, `http_status: int NULL`, `content_type: Text NULL`, `source_revision: Text NULL`, `resolved_content_id: UUID NULL FK -> dataset_content.id ON DELETE RESTRICT`, `error_message: Text NULL`, `created_at: datetime`).

- [ ] **Step 1: Add the models**

```python
# backend/app/db/models.py — add near UserDataset

class DatasetContent(Base):
    """Immutable content-addressed dataset snapshot. Never updated after insert."""

    __tablename__ = "dataset_content"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    schema_sniff_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DatasetFetchEvent(Base):
    """Append-only provenance record — one row per fetch attempt, written once terminal."""

    __tablename__ = "dataset_fetch_event"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_content_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dataset_content.id", ondelete="RESTRICT"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    content: Mapped[DatasetContent | None] = relationship()
```

Add `PGUUID` import (`from sqlalchemy.dialects.postgresql import UUID as PGUUID`) if not already imported in this file — check the top of `models.py` first; `UserDataset`/`Evaluation` already use a UUID primary-key pattern, follow whatever import name that file already uses instead of introducing a second alias.

- [ ] **Step 2: Generate and hand-verify the Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "add dataset_content and dataset_fetch_event"`

Open the generated file and confirm it creates exactly two tables with the columns above, the unique constraint on `content_hash`, and the FK with `ondelete="RESTRICT"`. Autogenerate sometimes misses `ondelete` — add it manually if absent:

```python
sa.Column("resolved_content_id", postgresql.UUID(as_uuid=True), nullable=True),
...
sa.ForeignKeyConstraint(["resolved_content_id"], ["dataset_content.id"], ondelete="RESTRICT"),
```

- [ ] **Step 3: Apply migration in test DB and verify**

Run: `cd backend && alembic upgrade head`
Expected: no errors; `\d dataset_content` and `\d dataset_fetch_event` in psql show the expected columns/constraints.

- [ ] **Step 4: Write model-level tests**

```python
# backend/tests/test_dataset_content_models.py
import uuid
from datetime import datetime, UTC

from app.db.models import DatasetContent, DatasetFetchEvent


def test_dataset_content_unique_content_hash(db_session):
    row = DatasetContent(
        content_hash="a" * 64,
        storage_uri="s3://trustlens/datasets/" + "a" * 64,
        byte_size=100,
        format="csv",
        row_count=10,
        columns=[{"name": "text", "inferred_type": "string"}],
    )
    db_session.add(row)
    db_session.flush()
    assert row.id is not None

    dup = DatasetContent(
        content_hash="a" * 64,
        storage_uri="s3://trustlens/datasets/" + "a" * 64,
        byte_size=100,
        format="csv",
        row_count=10,
        columns=[],
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_dataset_fetch_event_records_provenance(db_session):
    content = DatasetContent(
        content_hash="b" * 64,
        storage_uri="s3://trustlens/datasets/" + "b" * 64,
        byte_size=50,
        format="csv",
        row_count=5,
        columns=[],
    )
    db_session.add(content)
    db_session.flush()

    event = DatasetFetchEvent(
        source_url="https://example.com/data.csv",
        requested_at=datetime.now(UTC),
        http_status=200,
        content_type="text/csv",
        resolved_content_id=content.id,
    )
    db_session.add(event)
    db_session.flush()
    assert event.resolved_content_id == content.id
```

Add `import pytest` and `from sqlalchemy.exc import IntegrityError` at the top of the test file. Check `backend/tests/conftest.py` for the exact name of the `db_session` fixture already used by `test_models_fk.py` — reuse it verbatim, don't invent a new fixture.

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_dataset_content_models.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/ backend/tests/test_dataset_content_models.py
git commit -m "feat: add DatasetContent and DatasetFetchEvent models"
```

### Task 1.2: Content-addressed storage helper (`DatasetContentStore`)

**Files:**
- Modify: `backend/app/storage/evidence_store.py` (add new class alongside `EvidenceStore`/`DatasetStore` — do not modify the existing `DatasetStore` class, it stays serving the legacy `user_dataset` upload path until Phase 7)
- Test: `backend/tests/test_dataset_content_store.py`

**Interfaces:**
- Consumes: `boto3.client` (`BaseClient`), same `_STORE_BOTO_CONFIG` pattern already in this file.
- Produces: `DatasetContentStore.put(data: bytes, *, format: str) -> tuple[str, str]` returning `(storage_uri, content_hash)`; `DatasetContentStore.get(storage_uri: str) -> bytes`; `get_dataset_content_store(settings) -> DatasetContentStore | None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dataset_content_store.py
from app.storage.evidence_store import DatasetContentStore, format_sha256


def test_put_is_content_addressed_and_idempotent(fake_s3_client):
    store = DatasetContentStore(fake_s3_client, "trustlens")
    data = b"col1,col2\nfoo,bar\n"

    uri1, hash1 = store.put(data, format="csv")
    uri2, hash2 = store.put(data, format="csv")

    assert hash1 == hash2 == format_sha256(data)
    assert uri1 == uri2
    assert store.get(uri1) == data


def test_put_different_bytes_different_key(fake_s3_client):
    store = DatasetContentStore(fake_s3_client, "trustlens")
    uri1, hash1 = store.put(b"aaa", format="csv")
    uri2, hash2 = store.put(b"bbb", format="csv")
    assert uri1 != uri2
    assert hash1 != hash2
```

Check `backend/tests/fakes.py` for an existing fake S3/boto3 client fixture (`EvidenceStore`'s tests already need one) — reuse it as `fake_s3_client`, don't write a new fake.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_dataset_content_store.py -v`
Expected: FAIL — `ImportError: cannot import name 'DatasetContentStore'`.

- [ ] **Step 3: Implement**

```python
# backend/app/storage/evidence_store.py — add after the existing DatasetStore class

class DatasetContentStore:
    """Content-addressed storage for DatasetContent bytes.

    Key is derived purely from the SHA-256 of the bytes — never from a
    client-supplied filename or the source URL. Same bytes always resolve
    to the same key; puts are idempotent.
    """

    def __init__(self, client: BaseClient, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def _object_key(self, content_hash: str) -> str:
        return f"datasets/{content_hash.removeprefix('sha256:')}"

    def put(self, data: bytes, *, format: str) -> tuple[str, str]:
        digest = format_sha256(data)
        key = self._object_key(digest)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=f"text/{format}" if format else "application/octet-stream",
            )
        except Exception as exc:
            raise EvidenceStoreError(f"Failed to put dataset content key={key}: {exc}") from exc
        return f"s3://{self._bucket}/{key}", digest

    def get(self, storage_uri: str) -> bytes:
        parsed = urlparse(storage_uri)
        if parsed.scheme != "s3" or parsed.netloc != self._bucket:
            raise EvidenceStoreError(f"Unsupported/mismatched dataset content URI: {storage_uri}")
        key = parsed.path.lstrip("/")
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return bytes(response["Body"].read())
        except Exception as exc:
            raise EvidenceStoreError(f"Failed to get dataset content key={key}: {exc}") from exc


def get_dataset_content_store(settings: Settings | _SettingsLike) -> DatasetContentStore | None:
    if not settings.s3_endpoint or not settings.s3_access_key or not settings.s3_secret_key:
        return None
    client: BaseClient = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=_STORE_BOTO_CONFIG,
    )
    return DatasetContentStore(client, settings.s3_bucket)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_dataset_content_store.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/evidence_store.py backend/tests/test_dataset_content_store.py
git commit -m "feat: add content-addressed DatasetContentStore"
```

### Task 1.3: SSRF-safe URL fetcher

**Files:**
- Create: `backend/app/datasets/url_fetch.py`
- Test: `backend/tests/test_url_fetch.py`

**Interfaces:**
- Produces: `fetch_dataset_url(url: str, *, max_bytes: int = 10_000_000, timeout_seconds: float = 15.0) -> FetchedBytes` (dataclass: `data: bytes`, `content_type: str | None`, `http_status: int`), raising `UrlFetchError` (with a `reason` attribute) on any SSRF/size/timeout/scheme violation.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_url_fetch.py
import pytest

from app.datasets.url_fetch import UrlFetchError, fetch_dataset_url


def test_rejects_non_http_scheme():
    with pytest.raises(UrlFetchError, match="scheme"):
        fetch_dataset_url("file:///etc/passwd")


def test_rejects_loopback_address():
    with pytest.raises(UrlFetchError, match="private|loopback"):
        fetch_dataset_url("http://127.0.0.1/data.csv")


def test_rejects_link_local_address():
    with pytest.raises(UrlFetchError, match="private|link-local"):
        fetch_dataset_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_private_rfc1918_address():
    with pytest.raises(UrlFetchError, match="private"):
        fetch_dataset_url("http://10.0.0.5/data.csv")


def test_rejects_oversized_response(httpserver):
    httpserver.expect_request("/big.csv").respond_with_data(b"x" * 20_000_000, content_type="text/csv")
    url = httpserver.url_for("/big.csv")
    with pytest.raises(UrlFetchError, match="size|exceeds"):
        fetch_dataset_url(url, max_bytes=1_000_000)


def test_successful_fetch(httpserver):
    httpserver.expect_request("/data.csv").respond_with_data(b"a,b\n1,2\n", content_type="text/csv")
    url = httpserver.url_for("/data.csv")
    result = fetch_dataset_url(url)
    assert result.data == b"a,b\n1,2\n"
    assert result.http_status == 200
```

Add `pytest-httpserver` to `backend/pyproject.toml`'s dev/test dependencies if not already present — check first with `grep httpserver backend/pyproject.toml`.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_url_fetch.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/app/datasets/url_fetch.py
"""SSRF-safe streaming dataset URL fetcher — V1: no archives, no redirects followed
automatically past a re-validated hop, hard byte cap enforced while streaming."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 3
_CONNECT_TIMEOUT = 5.0


class UrlFetchError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class FetchedBytes:
    data: bytes
    content_type: str | None
    http_status: int


def _resolve_and_validate_host(host: str) -> str:
    """Resolve host to an IP and reject private/loopback/link-local/reserved ranges.

    Returns the validated IP as a string so the caller can pin the connection
    to it (defends against DNS rebinding between check and connect).
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UrlFetchError(f"could not resolve host: {exc}") from exc
    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UrlFetchError(f"resolved address is private/loopback/link-local/reserved: {ip}")
    return str(ipaddress.ip_address(infos[0][4][0]))


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UrlFetchError(f"unsupported scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UrlFetchError("URL has no hostname")
    _resolve_and_validate_host(parsed.hostname)
    return url


def fetch_dataset_url(
    url: str,
    *,
    max_bytes: int = 10_000_000,
    timeout_seconds: float = 15.0,
) -> FetchedBytes:
    current_url = _validate_url(url)
    redirects_followed = 0

    with httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT, read=timeout_seconds, write=timeout_seconds, pool=timeout_seconds),
    ) as client:
        while True:
            with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    redirects_followed += 1
                    if redirects_followed > _MAX_REDIRECTS:
                        raise UrlFetchError("too many redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UrlFetchError("redirect with no Location header")
                    current_url = _validate_url(location)
                    continue

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise UrlFetchError(f"response exceeds max_bytes={max_bytes}")
                    chunks.append(chunk)
                return FetchedBytes(
                    data=b"".join(chunks),
                    content_type=response.headers.get("content-type"),
                    http_status=response.status_code,
                )
```

Add `httpx` to `backend/pyproject.toml` dependencies if not already present (check first — it's a common FastAPI-adjacent dependency, likely already installed).

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_url_fetch.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/datasets/url_fetch.py backend/tests/test_url_fetch.py backend/pyproject.toml
git commit -m "feat: add SSRF-safe streaming dataset URL fetcher"
```

### Task 1.4: `DatasetContentRepository` + upsert-by-hash concurrency handling

**Files:**
- Create: `backend/app/db/repositories/dataset_content.py`
- Test: `backend/tests/test_dataset_content_repository.py`

**Interfaces:**
- Consumes: `DatasetContent`, `DatasetFetchEvent` (Task 1.1).
- Produces: `DatasetContentRepository.upsert(*, content_hash, storage_uri, byte_size, format, row_count, columns) -> DatasetContent` (atomic upsert-by-hash), `DatasetContentRepository.get_by_id(id) -> DatasetContent | None`, `DatasetFetchEventRepository.create(...) -> DatasetFetchEvent`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dataset_content_repository.py
from app.db.repositories.dataset_content import DatasetContentRepository, DatasetFetchEventRepository


def test_upsert_same_hash_returns_same_row(db_session):
    repo = DatasetContentRepository(db_session)
    row1 = repo.upsert(
        content_hash="c" * 64, storage_uri="s3://b/datasets/c" * 1, byte_size=10,
        format="csv", row_count=1, columns=[],
    )
    row2 = repo.upsert(
        content_hash="c" * 64, storage_uri="s3://b/datasets/c" * 1, byte_size=10,
        format="csv", row_count=1, columns=[],
    )
    assert row1.id == row2.id


def test_fetch_event_records_resolved_content(db_session):
    content_repo = DatasetContentRepository(db_session)
    content = content_repo.upsert(
        content_hash="d" * 64, storage_uri="s3://b/datasets/d", byte_size=5,
        format="csv", row_count=1, columns=[],
    )
    event_repo = DatasetFetchEventRepository(db_session)
    event = event_repo.create(
        source_url="https://example.com/x.csv",
        http_status=200,
        content_type="text/csv",
        resolved_content_id=content.id,
    )
    assert event.resolved_content_id == content.id


def test_fetch_event_failure_has_no_resolved_content(db_session):
    event_repo = DatasetFetchEventRepository(db_session)
    event = event_repo.create(
        source_url="https://example.com/broken.csv",
        http_status=None,
        content_type=None,
        resolved_content_id=None,
        error_message="could not resolve host",
    )
    assert event.resolved_content_id is None
    assert event.error_message == "could not resolve host"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_dataset_content_repository.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/app/db/repositories/dataset_content.py
"""DatasetContent/DatasetFetchEvent repositories.

upsert() uses Postgres's ON CONFLICT DO UPDATE (no-op update) so the atomic
upsert-by-content_hash race between two concurrent identical fetches always
resolves to exactly one row, with RETURNING giving back its id either way.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import DatasetContent, DatasetFetchEvent


class DatasetContentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        content_hash: str,
        storage_uri: str,
        byte_size: int,
        format: str,
        row_count: int,
        columns: list[dict[str, Any]],
        schema_sniff_version: int = 1,
    ) -> DatasetContent:
        stmt = pg_insert(DatasetContent).values(
            content_hash=content_hash,
            storage_uri=storage_uri,
            byte_size=byte_size,
            format=format,
            row_count=row_count,
            columns=columns,
            schema_sniff_version=schema_sniff_version,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[DatasetContent.content_hash],
            set_={"content_hash": stmt.excluded.content_hash},
        ).returning(DatasetContent.id)
        result_id = self._session.execute(stmt).scalar_one()
        self._session.flush()
        return self._session.get(DatasetContent, result_id)

    def get_by_id(self, content_id: uuid.UUID) -> DatasetContent | None:
        return self._session.get(DatasetContent, content_id)


class DatasetFetchEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        source_url: str,
        http_status: int | None,
        content_type: str | None,
        resolved_content_id: uuid.UUID | None,
        source_revision: str | None = None,
        error_message: str | None = None,
    ) -> DatasetFetchEvent:
        row = DatasetFetchEvent(
            source_url=source_url,
            requested_at=datetime.now(UTC),
            http_status=http_status,
            content_type=content_type,
            source_revision=source_revision,
            resolved_content_id=resolved_content_id,
            error_message=error_message,
        )
        self._session.add(row)
        self._session.flush()
        return row
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_dataset_content_repository.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/repositories/dataset_content.py backend/tests/test_dataset_content_repository.py
git commit -m "feat: add DatasetContentRepository with atomic upsert-by-hash"
```

### Task 1.5: CSV schema sniffing reused for fetched bytes + `POST /v1/dataset-fetches` endpoint

**Files:**
- Modify: `backend/app/datasets/user_dataset.py` (no changes needed — `sniff_columns`/`count_rows` already format-agnostic over raw bytes; reuse verbatim, do not duplicate)
- Create: `backend/app/schemas/dataset_content.py`
- Create: `backend/app/services/dataset_content_service.py`
- Create: `backend/app/routers/v1/dataset_content.py`
- Modify: `backend/app/main.py` (register new router — check how existing routers are registered, e.g. `app.include_router(datasets.router, prefix="/v1")`, and follow the identical pattern)
- Test: `backend/tests/test_dataset_content_router.py`

**Interfaces:**
- Consumes: `fetch_dataset_url` (Task 1.3), `DatasetContentStore`/`get_dataset_content_store` (Task 1.2), `DatasetContentRepository`/`DatasetFetchEventRepository` (Task 1.4), `sniff_columns`/`count_rows` from `app.datasets.user_dataset`.
- Produces: `DatasetContentRead` schema (`id`, `content_hash`, `byte_size`, `format`, `row_count`, `columns`), `POST /v1/dataset-fetches {source_url: str}` -> `DatasetContentRead`, `GET /v1/dataset-contents/{id}` -> `DatasetContentRead`.

- [ ] **Step 1: Write the failing router test**

```python
# backend/tests/test_dataset_content_router.py
def test_post_dataset_fetches_creates_content(client, httpserver):
    httpserver.expect_request("/data.csv").respond_with_data(
        b"text,label\nhello,0\nworld,1\n", content_type="text/csv"
    )
    url = httpserver.url_for("/data.csv")

    resp = client.post("/v1/dataset-fetches", json={"source_url": url})
    assert resp.status_code == 201
    body = resp.json()
    assert body["row_count"] == 2
    assert {"name": "text", "inferred_type": "string"} in body["columns"] or any(
        c["name"] == "text" for c in body["columns"]
    )

    # re-fetching the same content dedupes to the same DatasetContent
    resp2 = client.post("/v1/dataset-fetches", json={"source_url": url})
    assert resp2.json()["id"] == body["id"]


def test_get_dataset_content_by_id(client, httpserver):
    httpserver.expect_request("/data2.csv").respond_with_data(b"a,b\n1,2\n", content_type="text/csv")
    url = httpserver.url_for("/data2.csv")
    created = client.post("/v1/dataset-fetches", json={"source_url": url}).json()

    resp = client.get(f"/v1/dataset-contents/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["content_hash"] == created["content_hash"]


def test_post_dataset_fetches_rejects_ssrf_target(client):
    resp = client.post("/v1/dataset-fetches", json={"source_url": "http://127.0.0.1/x.csv"})
    assert resp.status_code == 422
```

Check `backend/tests/conftest.py` for the existing `client` fixture (a `TestClient` wired to the FastAPI app) — reuse it, it's already used across every other router test.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_dataset_content_router.py -v`
Expected: FAIL — 404 (route doesn't exist).

- [ ] **Step 3: Implement schema**

```python
# backend/app/schemas/dataset_content.py
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetFetchRequest(BaseModel):
    source_url: str = Field(..., min_length=1, max_length=2048)


class DatasetContentRead(BaseModel):
    id: uuid.UUID
    content_hash: str
    byte_size: int
    format: str
    row_count: int
    columns: list[dict[str, Any]]
    created_at: datetime
```

- [ ] **Step 4: Implement service**

```python
# backend/app/services/dataset_content_service.py
from __future__ import annotations

from app.api.errors import ValidationAppError
from app.core.config import Settings
from app.datasets.url_fetch import UrlFetchError, fetch_dataset_url
from app.datasets.user_dataset import count_rows, sniff_columns
from app.db.repositories.dataset_content import DatasetContentRepository, DatasetFetchEventRepository
from app.schemas.dataset_content import DatasetContentRead, DatasetFetchRequest
from app.storage.evidence_store import DatasetContentStore

_MAX_FETCH_BYTES = 10_000_000
_SUPPORTED_FORMAT = "csv"


class DatasetContentService:
    def __init__(
        self,
        content_repo: DatasetContentRepository,
        event_repo: DatasetFetchEventRepository,
        store: DatasetContentStore,
    ) -> None:
        self._content_repo = content_repo
        self._event_repo = event_repo
        self._store = store

    def fetch_and_store(self, body: DatasetFetchRequest) -> DatasetContentRead:
        try:
            fetched = fetch_dataset_url(body.source_url, max_bytes=_MAX_FETCH_BYTES)
        except UrlFetchError as exc:
            self._event_repo.create(
                source_url=body.source_url,
                http_status=None,
                content_type=None,
                resolved_content_id=None,
                error_message=exc.reason,
            )
            raise ValidationAppError(f"could not fetch dataset URL: {exc.reason}") from exc

        try:
            columns = sniff_columns(fetched.data)
            row_count = count_rows(fetched.data)
        except Exception as exc:
            self._event_repo.create(
                source_url=body.source_url,
                http_status=fetched.http_status,
                content_type=fetched.content_type,
                resolved_content_id=None,
                error_message=f"malformed CSV: {exc}",
            )
            raise ValidationAppError(f"downloaded file is not a valid CSV: {exc}") from exc

        storage_uri, content_hash = self._store.put(fetched.data, format=_SUPPORTED_FORMAT)
        content = self._content_repo.upsert(
            content_hash=content_hash,
            storage_uri=storage_uri,
            byte_size=len(fetched.data),
            format=_SUPPORTED_FORMAT,
            row_count=row_count,
            columns=columns,
        )
        self._event_repo.create(
            source_url=body.source_url,
            http_status=fetched.http_status,
            content_type=fetched.content_type,
            resolved_content_id=content.id,
        )
        return DatasetContentRead.model_validate(content, from_attributes=True)
```

`sniff_columns` returns `[{"name": ..., "inferred_type": ...}]` per its existing signature (verified earlier in this design conversation) — no adaptation needed.

- [ ] **Step 5: Implement router**

```python
# backend/app/routers/v1/dataset_content.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.core.config import get_settings
from app.db.repositories.dataset_content import DatasetContentRepository, DatasetFetchEventRepository
from app.schemas.dataset_content import DatasetContentRead, DatasetFetchRequest
from app.services.dataset_content_service import DatasetContentService
from app.storage.evidence_store import get_dataset_content_store

router = APIRouter(prefix="/dataset-fetches", tags=["dataset-content"])
content_router = APIRouter(prefix="/dataset-contents", tags=["dataset-content"])


def _get_service(db: Session = Depends(get_db)) -> DatasetContentService:
    store = get_dataset_content_store(get_settings())
    if store is None:
        from app.api.errors import AppError

        raise AppError("STORAGE_UNAVAILABLE", "Dataset content storage is not configured", status_code=503)
    return DatasetContentService(
        DatasetContentRepository(db),
        DatasetFetchEventRepository(db),
        store,
    )


@router.post("", response_model=DatasetContentRead, status_code=status.HTTP_201_CREATED)
def create_dataset_fetch(
    body: DatasetFetchRequest,
    service: DatasetContentService = Depends(_get_service),
) -> DatasetContentRead:
    return service.fetch_and_store(body)


@content_router.get("/{content_id}", response_model=DatasetContentRead)
def get_dataset_content(
    content_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DatasetContentRead:
    row = DatasetContentRepository(db).get_by_id(content_id)
    if row is None:
        raise NotFoundError(f"DatasetContent {content_id} not found", details={"id": str(content_id)})
    return DatasetContentRead.model_validate(row, from_attributes=True)
```

- [ ] **Step 6: Register routers**

In `backend/app/main.py`, find where existing `v1` routers are included (e.g. `from app.routers.v1 import datasets` then `app.include_router(datasets.router, prefix="/v1")`) and add:

```python
from app.routers.v1 import dataset_content

app.include_router(dataset_content.router, prefix="/v1")
app.include_router(dataset_content.content_router, prefix="/v1")
```

- [ ] **Step 7: Run to verify pass**

Run: `cd backend && pytest tests/test_dataset_content_router.py -v`
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/dataset_content.py backend/app/services/dataset_content_service.py backend/app/routers/v1/dataset_content.py backend/app/main.py backend/tests/test_dataset_content_router.py
git commit -m "feat: add POST /v1/dataset-fetches and GET /v1/dataset-contents/{id}"
```

**Phase 1 complete when:** all tasks above pass; `POST /v1/dataset-fetches` and `GET /v1/dataset-contents/{id}` are live and tested; nothing in the existing evaluation-creation path has changed.

---

## Phase 2 — Evaluation draft + draft dimension configuration + validation/confirmation APIs

**Rollback/safety boundary:** Additive — new tables (`evaluation_draft`, `draft_dimension_config`), new endpoints, new service calling `AutoConfig`. Nothing existing reads these tables. A revert is a straight `alembic downgrade`.

**What old behavior remains temporarily:** Old evaluation-creation (`POST /v1/evaluations` with `pairing_id`/`dataset_key`/`contract_kind`) is completely untouched and still the only way to actually create an `Evaluation` in this phase. Drafts exist but nothing consumes them into a real evaluation yet — that's Phase 4.

**What becomes impossible after this phase:** Nothing yet — still purely additive.

### Task 2.1: `evaluation_draft` + `draft_dimension_config` models and migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/alembic/versions/XXX_add_evaluation_draft.py`
- Test: `backend/tests/test_evaluation_draft_models.py`

**Interfaces:**
- Produces: `EvaluationDraft` (`id: UUID PK`, `model_id: int FK -> models.id ON DELETE RESTRICT`, `status: str` — `"incomplete"|"validated"|"consumed"|"stale"`, `resolved_model_sha: str | None`, `model_label_snapshot: JSONB | None`, `created_at`, `updated_at`), `DraftDimensionConfig` (`id: UUID PK`, `draft_id: UUID FK -> evaluation_draft.id ON DELETE CASCADE`, `dimension: str` — `"FAIRNESS"|"ROBUSTNESS"`, `dataset_content_id: UUID NULL FK -> dataset_content.id ON DELETE RESTRICT`, `text_column: str NULL`, `target_column: str NULL`, `sensitive_column: str NULL`, `label_mapping: JSONB NULL`, `min_group_n: int NULL`, `validated_at: datetime NULL`, `confirmed_at: datetime NULL`, unique constraint on `(draft_id, dimension)`).

- [ ] **Step 1: Add the models**

```python
# backend/app/db/models.py — add after DatasetFetchEvent

class EvaluationDraft(Base):
    __tablename__ = "evaluation_draft"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[int] = mapped_column(Integer, ForeignKey("models.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="incomplete")
    resolved_model_sha: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_label_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    dimensions: Mapped[list[DraftDimensionConfig]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )


class DraftDimensionConfig(Base):
    __tablename__ = "draft_dimension_config"
    __table_args__ = (UniqueConstraint("draft_id", "dimension", name="uq_draft_dimension"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evaluation_draft.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset_content_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dataset_content.id", ondelete="RESTRICT"), nullable=True
    )
    text_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sensitive_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    label_mapping: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    min_group_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    draft: Mapped[EvaluationDraft] = relationship(back_populates="dimensions")
```

Add `UniqueConstraint` to the existing `sqlalchemy` import line at the top of `models.py` if not already imported.

- [ ] **Step 2: Generate and hand-verify migration**

Run: `cd backend && alembic revision --autogenerate -m "add evaluation_draft and draft_dimension_config"`

Verify the generated file includes the unique constraint `uq_draft_dimension` and both `ondelete` clauses (`CASCADE` for `draft_id`, `RESTRICT` for `dataset_content_id`) — autogenerate often needs these added by hand.

- [ ] **Step 3: Apply and verify**

Run: `cd backend && alembic upgrade head`
Expected: no errors.

- [ ] **Step 4: Write model tests**

```python
# backend/tests/test_evaluation_draft_models.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import DraftDimensionConfig, EvaluationDraft


def test_draft_defaults_to_incomplete(db_session, seeded_model):
    draft = EvaluationDraft(model_id=seeded_model.id)
    db_session.add(draft)
    db_session.flush()
    assert draft.status == "incomplete"


def test_one_dimension_config_per_dimension_per_draft(db_session, seeded_model):
    draft = EvaluationDraft(model_id=seeded_model.id)
    db_session.add(draft)
    db_session.flush()

    db_session.add(DraftDimensionConfig(draft_id=draft.id, dimension="FAIRNESS"))
    db_session.flush()

    db_session.add(DraftDimensionConfig(draft_id=draft.id, dimension="FAIRNESS"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_draft_cascades_to_dimension_configs(db_session, seeded_model):
    draft = EvaluationDraft(model_id=seeded_model.id)
    db_session.add(draft)
    db_session.flush()
    dim = DraftDimensionConfig(draft_id=draft.id, dimension="ROBUSTNESS")
    db_session.add(dim)
    db_session.flush()
    dim_id = dim.id

    db_session.delete(draft)
    db_session.flush()
    assert db_session.get(DraftDimensionConfig, dim_id) is None
```

Check `backend/tests/conftest.py` for a `seeded_model` fixture (or the equivalent already used by `test_models_fk.py`, e.g. `_seed_model_and_eval`) — reuse whatever fixture already creates a `Model` row for tests, don't invent a new one.

- [ ] **Step 5: Run and verify pass**

Run: `cd backend && pytest tests/test_evaluation_draft_models.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/ backend/tests/test_evaluation_draft_models.py
git commit -m "feat: add EvaluationDraft and DraftDimensionConfig models"
```

### Task 2.2: Config-only model inspection (`AutoConfig`) service

**Files:**
- Create: `backend/app/inference/model_inspection.py`
- Test: `backend/tests/test_model_inspection.py`

**Interfaces:**
- Produces: `inspect_model_config(model_ref: str, *, revision: str | None, hf_token: str | None) -> ModelLabelSnapshot` (dataclass: `num_labels: int`, `id2label: dict[int, str]`, `resolved_sha: str`), raising `ModelInspectionError` on failure (unknown revision, no classification head, network error).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_model_inspection.py
from unittest.mock import patch

import pytest

from app.inference.model_inspection import ModelInspectionError, inspect_model_config


def test_inspect_model_config_returns_snapshot():
    fake_config = type("Cfg", (), {
        "num_labels": 2,
        "id2label": {0: "NEGATIVE", 1: "POSITIVE"},
        "_commit_hash": "abc123def456",
    })()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = fake_config
        snapshot = inspect_model_config("distilbert-base-uncased-finetuned-sst-2-english", revision="main", hf_token=None)
    assert snapshot.num_labels == 2
    assert snapshot.id2label == {0: "NEGATIVE", 1: "POSITIVE"}
    assert snapshot.resolved_sha == "abc123def456"


def test_inspect_model_config_rejects_no_classification_head():
    fake_config = type("Cfg", (), {"num_labels": None, "id2label": None, "_commit_hash": "xyz"})()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = fake_config
        with pytest.raises(ModelInspectionError, match="classification head"):
            inspect_model_config("some/model", revision="main", hf_token=None)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_model_inspection.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/app/inference/model_inspection.py
"""Config-only (AutoConfig) model inspection for intake-time compatibility
validation. Never loads model weights — no GPU/RAM cost, no torch import
required at the API layer."""

from __future__ import annotations

from dataclasses import dataclass

from transformers import AutoConfig

from app.inference.errors import INVALID_MODEL_REVISION, MODEL_LOAD_ERROR


class ModelInspectionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ModelLabelSnapshot:
    num_labels: int
    id2label: dict[int, str]
    resolved_sha: str


def inspect_model_config(
    model_ref: str,
    *,
    revision: str | None,
    hf_token: str | None,
) -> ModelLabelSnapshot:
    kwargs: dict[str, str] = {}
    if revision:
        kwargs["revision"] = revision
    if hf_token:
        kwargs["token"] = hf_token
    try:
        config = AutoConfig.from_pretrained(model_ref, **kwargs)
    except Exception as exc:
        from huggingface_hub.utils import RevisionNotFoundError

        if isinstance(exc, RevisionNotFoundError):
            raise ModelInspectionError(
                INVALID_MODEL_REVISION, f"model revision not found for {model_ref}: {exc}"
            ) from exc
        raise ModelInspectionError(MODEL_LOAD_ERROR, f"failed to inspect model config for {model_ref}: {exc}") from exc

    num_labels = getattr(config, "num_labels", None)
    id2label_raw = getattr(config, "id2label", None)
    if not num_labels or not isinstance(id2label_raw, dict):
        raise ModelInspectionError(
            MODEL_LOAD_ERROR, f"{model_ref} has no sequence-classification head (num_labels={num_labels})"
        )
    resolved_sha = getattr(config, "_commit_hash", None) or (revision or "")
    return ModelLabelSnapshot(
        num_labels=int(num_labels),
        id2label={int(k): str(v) for k, v in id2label_raw.items()},
        resolved_sha=str(resolved_sha),
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_model_inspection.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/inference/model_inspection.py backend/tests/test_model_inspection.py
git commit -m "feat: add config-only AutoConfig model inspection for intake validation"
```

### Task 2.3: Column-role + label-mapping validation logic

**Files:**
- Create: `backend/app/services/draft_validation.py`
- Test: `backend/tests/test_draft_validation.py`

**Interfaces:**
- Consumes: `ModelLabelSnapshot` (Task 2.2), `DatasetContent.columns`/`row_count`, raw dataset bytes via `DatasetContentStore.get`.
- Produces: `validate_fairness_config(*, dataset_bytes, text_column, target_column, sensitive_column, label_mapping, model_label_snapshot, min_group_n) -> FairnessValidationResult` (dataclass: `ok: bool`, `errors: list[str]`, `group_preview: list[dict]` — `{value, count, meets_min_group_n}`, `groups_remaining: int`); `validate_robustness_config(*, dataset_bytes, text_column, target_column, label_mapping, model_label_snapshot) -> RobustnessValidationResult` (dataclass: `ok: bool`, `errors: list[str]`, `n_label_compatible: int`, `n_excluded: int`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_draft_validation.py
from app.inference.model_inspection import ModelLabelSnapshot
from app.services.draft_validation import validate_fairness_config, validate_robustness_config

SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="abc")

CSV = b"text,label,group\nhello,pos,a\nworld,neg,a\nfoo,pos,b\nbar,neg,b\nbaz,pos,b\n"


def test_fairness_validation_reports_group_counts():
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=2,
    )
    assert result.ok
    counts = {g["value"]: g["count"] for g in result.group_preview}
    assert counts == {"a": 2, "b": 3}
    assert result.groups_remaining == 2


def test_fairness_validation_flags_too_few_groups():
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=3,
    )
    assert result.groups_remaining == 1
    assert any("fewer than 2 groups" in e for e in result.errors)


def test_fairness_validation_rejects_incomplete_label_mapping():
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
    )
    assert not result.ok
    assert any("label_mapping" in e for e in result.errors)


def test_robustness_validation_reports_label_compatibility():
    result = validate_robustness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
    )
    assert result.ok
    assert result.n_label_compatible == 5
    assert result.n_excluded == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_draft_validation.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/app/services/draft_validation.py
"""Column-role and label-mapping validation against a DatasetContent's raw
bytes and a model's ModelLabelSnapshot. Runs at intake time, before the
worker ever sees anything — reuses app.datasets.user_dataset's CSV parsing,
never re-implements it."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app.datasets.user_dataset import UserDatasetError, discover_group_values
from app.inference.model_inspection import ModelLabelSnapshot

_MISSING_TOKENS = {"", "na", "n/a", "null", "nan", "none"}


@dataclass
class FairnessValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    group_preview: list[dict] = field(default_factory=list)
    groups_remaining: int = 0


@dataclass
class RobustnessValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    n_label_compatible: int = 0
    n_excluded: int = 0


def _validate_label_mapping(label_mapping: list[dict], target_values: set[str], snapshot: ModelLabelSnapshot) -> list[str]:
    errors: list[str] = []
    mapped_values = {entry["dataset_value"] for entry in label_mapping}
    missing = target_values - mapped_values
    if missing:
        errors.append(f"label_mapping is missing entries for observed target values: {sorted(missing)}")
    for entry in label_mapping:
        idx = entry["model_label_index"]
        if idx not in snapshot.id2label:
            errors.append(f"label_mapping entry {entry!r} references unknown model_label_index={idx}")
    return errors


def _observed_target_values(data: bytes, target_column: str) -> set[str]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    values: set[str] = set()
    for row in reader:
        raw = row.get(target_column)
        if raw is not None and raw.strip().lower() not in _MISSING_TOKENS:
            values.add(raw.strip())
    return values


def validate_fairness_config(
    *,
    dataset_bytes: bytes,
    text_column: str,
    target_column: str,
    sensitive_column: str,
    label_mapping: list[dict],
    model_label_snapshot: ModelLabelSnapshot,
    min_group_n: int,
) -> FairnessValidationResult:
    errors: list[str] = []
    try:
        observed_groups, _missing = discover_group_values(dataset_bytes, group_column=sensitive_column)
    except UserDatasetError as exc:
        return FairnessValidationResult(ok=False, errors=[str(exc)])

    try:
        target_values = _observed_target_values(dataset_bytes, target_column)
    except Exception as exc:  # noqa: BLE001 — surfaced as a validation error, not a crash
        return FairnessValidationResult(ok=False, errors=[f"could not read target_column={target_column!r}: {exc}"])

    errors.extend(_validate_label_mapping(label_mapping, target_values, model_label_snapshot))

    group_preview = [
        {"value": g["value"], "count": g["count"], "meets_min_group_n": g["count"] >= min_group_n}
        for g in observed_groups
    ]
    groups_remaining = sum(1 for g in group_preview if g["meets_min_group_n"])
    if groups_remaining < 2:
        errors.append(
            f"fewer than 2 groups meet min_group_n={min_group_n} "
            f"(groups_remaining={groups_remaining}) — Fairness comparison would be INSUFFICIENT_EVIDENCE"
        )

    return FairnessValidationResult(
        ok=not errors, errors=errors, group_preview=group_preview, groups_remaining=groups_remaining
    )


def validate_robustness_config(
    *,
    dataset_bytes: bytes,
    text_column: str,
    target_column: str,
    label_mapping: list[dict],
    model_label_snapshot: ModelLabelSnapshot,
) -> RobustnessValidationResult:
    try:
        target_values = _observed_target_values(dataset_bytes, target_column)
    except Exception as exc:  # noqa: BLE001
        return RobustnessValidationResult(ok=False, errors=[f"could not read target_column={target_column!r}: {exc}"])

    errors = _validate_label_mapping(label_mapping, target_values, model_label_snapshot)

    reader = csv.DictReader(io.StringIO(dataset_bytes.decode("utf-8-sig")))
    mapped = {entry["dataset_value"]: entry["model_label_index"] for entry in label_mapping}
    total = 0
    compatible = 0
    for row in reader:
        total += 1
        raw = (row.get(target_column) or "").strip()
        if raw in mapped:
            compatible += 1
    excluded = total - compatible

    return RobustnessValidationResult(
        ok=not errors, errors=errors, n_label_compatible=compatible, n_excluded=excluded
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_draft_validation.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/draft_validation.py backend/tests/test_draft_validation.py
git commit -m "feat: add Fairness/Robustness intake validation (columns, label mapping, group preview)"
```

### Task 2.4: Draft repository + service (create, update dimension, confirm, get)

**Files:**
- Create: `backend/app/db/repositories/evaluation_draft.py`
- Create: `backend/app/services/evaluation_draft_service.py`
- Create: `backend/app/schemas/evaluation_draft.py`
- Test: `backend/tests/test_evaluation_draft_service.py`

**Interfaces:**
- Consumes: `EvaluationDraft`/`DraftDimensionConfig` (Task 2.1), `inspect_model_config` (Task 2.2), `validate_fairness_config`/`validate_robustness_config` (Task 2.3), `DatasetContentRepository` (Phase 1), `ModelRepository` (existing).
- Produces: `EvaluationDraftService.create(model_id: int) -> EvaluationDraftRead`, `.update_dimension(draft_id, dimension, body: DimensionConfigUpdate) -> DimensionValidationRead`, `.confirm_dimension(draft_id, dimension) -> EvaluationDraftRead`, `.get(draft_id) -> EvaluationDraftRead`.

- [ ] **Step 1: Write the failing service test**

```python
# backend/tests/test_evaluation_draft_service.py
from unittest.mock import patch

import pytest

from app.api.errors import ValidationAppError
from app.inference.model_inspection import ModelLabelSnapshot
from app.services.evaluation_draft_service import EvaluationDraftService

FAKE_SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1")


@pytest.fixture
def draft_service(db_session):
    return EvaluationDraftService(db_session)


def test_create_draft(draft_service, seeded_model):
    read = draft_service.create(seeded_model.id)
    assert read.status == "incomplete"
    assert read.model_id == seeded_model.id


def test_update_fairness_dimension_validates_and_returns_preview(
    draft_service, seeded_model, seeded_dataset_content
):
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        result = draft_service.update_dimension(
            draft.id,
            "FAIRNESS",
            {
                "dataset_content_id": seeded_dataset_content.id,
                "text_column": "text",
                "target_column": "label",
                "sensitive_column": "group",
                "label_mapping": [
                    {"dataset_value": "pos", "model_label_index": 1},
                    {"dataset_value": "neg", "model_label_index": 0},
                ],
                "min_group_n": 2,
            },
        )
    assert result.ok
    assert result.groups_remaining >= 2


def test_confirm_requires_prior_validation(draft_service, seeded_model):
    draft = draft_service.create(seeded_model.id)
    with pytest.raises(ValidationAppError, match="not.*validated"):
        draft_service.confirm_dimension(draft.id, "FAIRNESS")


def test_confirm_sets_confirmed_at(draft_service, seeded_model, seeded_dataset_content):
    draft = draft_service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        draft_service.update_dimension(
            draft.id,
            "FAIRNESS",
            {
                "dataset_content_id": seeded_dataset_content.id,
                "text_column": "text",
                "target_column": "label",
                "sensitive_column": "group",
                "label_mapping": [
                    {"dataset_value": "pos", "model_label_index": 1},
                    {"dataset_value": "neg", "model_label_index": 0},
                ],
                "min_group_n": 2,
            },
        )
    read = draft_service.confirm_dimension(draft.id, "FAIRNESS")
    assert read.fairness_confirmed
```

Add `seeded_dataset_content` fixture to `backend/tests/conftest.py` (a `DatasetContent` row with `columns=[{"name":"text",...},{"name":"label",...},{"name":"group",...}]`, `row_count=5`, backed by the same CSV bytes used in Task 2.3's tests — store it via a fake/in-memory store so `dataset_bytes` retrieval in the service works in tests without real MinIO).

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_evaluation_draft_service.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement repository**

```python
# backend/app/db/repositories/evaluation_draft.py
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import DraftDimensionConfig, EvaluationDraft


class EvaluationDraftRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, model_id: int) -> EvaluationDraft:
        row = EvaluationDraft(model_id=model_id)
        self._session.add(row)
        self._session.flush()
        return row

    def get_by_id(self, draft_id: uuid.UUID) -> EvaluationDraft | None:
        return self._session.get(EvaluationDraft, draft_id)

    def get_dimension(self, draft_id: uuid.UUID, dimension: str) -> DraftDimensionConfig | None:
        for dim in self.get_by_id(draft_id).dimensions:
            if dim.dimension == dimension:
                return dim
        return None

    def upsert_dimension(self, draft_id: uuid.UUID, dimension: str, **fields: Any) -> DraftDimensionConfig:
        existing = self.get_dimension(draft_id, dimension)
        if existing is None:
            existing = DraftDimensionConfig(draft_id=draft_id, dimension=dimension)
            self._session.add(existing)
        for key, value in fields.items():
            setattr(existing, key, value)
        self._session.flush()
        return existing

    def set_model_snapshot(self, draft_id: uuid.UUID, *, resolved_model_sha: str, model_label_snapshot: dict) -> None:
        draft = self.get_by_id(draft_id)
        draft.resolved_model_sha = resolved_model_sha
        draft.model_label_snapshot = model_label_snapshot
        self._session.flush()
```

- [ ] **Step 4: Implement schemas**

```python
# backend/app/schemas/evaluation_draft.py
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel


class DimensionConfigUpdate(BaseModel):
    dataset_content_id: uuid.UUID
    text_column: str
    target_column: str
    sensitive_column: str | None = None
    label_mapping: list[dict[str, Any]]
    min_group_n: int | None = None


class DimensionValidationRead(BaseModel):
    ok: bool
    errors: list[str]
    group_preview: list[dict[str, Any]] | None = None
    groups_remaining: int | None = None
    n_label_compatible: int | None = None
    n_excluded: int | None = None


class EvaluationDraftRead(BaseModel):
    id: uuid.UUID
    model_id: int
    status: Literal["incomplete", "validated", "consumed", "stale"]
    fairness_confirmed: bool
    robustness_confirmed: bool
```

- [ ] **Step 5: Implement service**

```python
# backend/app/services/evaluation_draft_service.py
"""Draft lifecycle: create -> update_dimension (validate) -> confirm_dimension
-> (Phase 4) consumed by POST /v1/evaluations. A dimension is mutable until
confirmed; the model snapshot is fetched once per draft and shared by both
dimensions (single frozen model identity per evaluation — never duplicated
per dimension, see Global Constraints)."""

from __future__ import annotations

import uuid

from app.api.errors import NotFoundError, ValidationAppError
from app.core.config import get_settings
from app.db.repositories.dataset_content import DatasetContentRepository
from app.db.repositories.evaluation_draft import EvaluationDraftRepository
from app.db.repositories.model import ModelRepository
from app.inference.model_inspection import inspect_model_config
from app.schemas.evaluation_draft import DimensionConfigUpdate, DimensionValidationRead, EvaluationDraftRead
from app.services.draft_validation import validate_fairness_config, validate_robustness_config
from app.storage.evidence_store import get_dataset_content_store


class EvaluationDraftService:
    def __init__(self, session) -> None:
        self._session = session
        self._drafts = EvaluationDraftRepository(session)
        self._models = ModelRepository(session)
        self._contents = DatasetContentRepository(session)

    def create(self, model_id: int) -> EvaluationDraftRead:
        model = self._models.get_by_id(model_id)
        if model is None:
            raise NotFoundError(f"Model {model_id} not found", details={"model_id": model_id})
        draft = self._drafts.create(model_id=model_id)
        return self._to_read(draft)

    def _ensure_model_snapshot(self, draft) -> None:
        if draft.resolved_model_sha and draft.model_label_snapshot:
            return
        model = self._models.get_by_id(draft.model_id)
        snapshot = inspect_model_config(model.hf_repo_id, revision=model.revision, hf_token=get_settings().hf_token)
        self._drafts.set_model_snapshot(
            draft.id,
            resolved_model_sha=snapshot.resolved_sha,
            model_label_snapshot={"num_labels": snapshot.num_labels, "id2label": snapshot.id2label},
        )
        draft.resolved_model_sha = snapshot.resolved_sha
        draft.model_label_snapshot = {"num_labels": snapshot.num_labels, "id2label": snapshot.id2label}

    def update_dimension(
        self, draft_id: uuid.UUID, dimension: str, body: dict
    ) -> DimensionValidationRead:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        update = DimensionConfigUpdate.model_validate(body)
        self._ensure_model_snapshot(draft)

        content = self._contents.get_by_id(update.dataset_content_id)
        if content is None:
            raise NotFoundError(
                f"DatasetContent {update.dataset_content_id} not found",
                details={"dataset_content_id": str(update.dataset_content_id)},
            )
        store = get_dataset_content_store(get_settings())
        data = store.get(content.storage_uri)

        from app.inference.model_inspection import ModelLabelSnapshot

        snapshot = ModelLabelSnapshot(
            num_labels=draft.model_label_snapshot["num_labels"],
            id2label={int(k): v for k, v in draft.model_label_snapshot["id2label"].items()},
            resolved_sha=draft.resolved_model_sha,
        )

        if dimension == "FAIRNESS":
            if not update.sensitive_column:
                raise ValidationAppError("Fairness requires sensitive_column")
            result = validate_fairness_config(
                dataset_bytes=data,
                text_column=update.text_column,
                target_column=update.target_column,
                sensitive_column=update.sensitive_column,
                label_mapping=update.label_mapping,
                model_label_snapshot=snapshot,
                min_group_n=update.min_group_n or 30,
            )
            read = DimensionValidationRead(
                ok=result.ok, errors=result.errors,
                group_preview=result.group_preview, groups_remaining=result.groups_remaining,
            )
        elif dimension == "ROBUSTNESS":
            result = validate_robustness_config(
                dataset_bytes=data,
                text_column=update.text_column,
                target_column=update.target_column,
                label_mapping=update.label_mapping,
                model_label_snapshot=snapshot,
            )
            read = DimensionValidationRead(
                ok=result.ok, errors=result.errors,
                n_label_compatible=result.n_label_compatible, n_excluded=result.n_excluded,
            )
        else:
            raise ValidationAppError(f"unknown dimension {dimension!r}")

        import datetime as _dt

        self._drafts.upsert_dimension(
            draft.id, dimension,
            dataset_content_id=update.dataset_content_id,
            text_column=update.text_column,
            target_column=update.target_column,
            sensitive_column=update.sensitive_column,
            label_mapping=update.label_mapping,
            min_group_n=update.min_group_n,
            validated_at=_dt.datetime.now(_dt.UTC) if result.ok else None,
            confirmed_at=None,  # editing always clears prior confirmation for THIS dimension only
        )
        return read

    def confirm_dimension(self, draft_id: uuid.UUID, dimension: str) -> EvaluationDraftRead:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        dim = self._drafts.get_dimension(draft_id, dimension)
        if dim is None or dim.validated_at is None:
            raise ValidationAppError(f"{dimension} has not been validated yet")
        import datetime as _dt

        dim.confirmed_at = _dt.datetime.now(_dt.UTC)
        self._session.flush()
        return self._to_read(draft)

    def get(self, draft_id: uuid.UUID) -> EvaluationDraftRead:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        return self._to_read(draft)

    @staticmethod
    def _to_read(draft) -> EvaluationDraftRead:
        by_dim = {d.dimension: d for d in draft.dimensions}
        return EvaluationDraftRead(
            id=draft.id,
            model_id=draft.model_id,
            status=draft.status,
            fairness_confirmed=bool(by_dim.get("FAIRNESS") and by_dim["FAIRNESS"].confirmed_at),
            robustness_confirmed=bool(by_dim.get("ROBUSTNESS") and by_dim["ROBUSTNESS"].confirmed_at),
        )
```

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && pytest tests/test_evaluation_draft_service.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/repositories/evaluation_draft.py backend/app/services/evaluation_draft_service.py backend/app/schemas/evaluation_draft.py backend/tests/test_evaluation_draft_service.py
git commit -m "feat: add EvaluationDraftService (create, update_dimension, confirm_dimension)"
```

### Task 2.5: Draft router

**Files:**
- Create: `backend/app/routers/v1/evaluation_drafts.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_evaluation_drafts_router.py`

**Interfaces:**
- Consumes: `EvaluationDraftService` (Task 2.4).
- Produces: `POST /v1/evaluation-drafts {model_id}`, `PUT /v1/evaluation-drafts/{id}/{dimension}`, `POST /v1/evaluation-drafts/{id}/{dimension}/confirm`, `GET /v1/evaluation-drafts/{id}`.

- [ ] **Step 1: Write the failing router test**

```python
# backend/tests/test_evaluation_drafts_router.py
from unittest.mock import patch

from app.inference.model_inspection import ModelLabelSnapshot

FAKE_SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1")


def test_full_draft_lifecycle(client, seeded_model, seeded_dataset_content):
    created = client.post("/v1/evaluation-drafts", json={"model_id": seeded_model.id}).json()
    draft_id = created["id"]
    assert created["status"] == "incomplete"

    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=FAKE_SNAPSHOT):
        validate_resp = client.put(
            f"/v1/evaluation-drafts/{draft_id}/FAIRNESS",
            json={
                "dataset_content_id": str(seeded_dataset_content.id),
                "text_column": "text",
                "target_column": "label",
                "sensitive_column": "group",
                "label_mapping": [
                    {"dataset_value": "pos", "model_label_index": 1},
                    {"dataset_value": "neg", "model_label_index": 0},
                ],
                "min_group_n": 2,
            },
        )
    assert validate_resp.status_code == 200
    assert validate_resp.json()["ok"]

    confirm_resp = client.post(f"/v1/evaluation-drafts/{draft_id}/FAIRNESS/confirm")
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["fairness_confirmed"]

    get_resp = client.get(f"/v1/evaluation-drafts/{draft_id}")
    assert get_resp.json()["fairness_confirmed"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_evaluation_drafts_router.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement router**

```python
# backend/app/routers/v1/evaluation_drafts.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.evaluation_draft import DimensionValidationRead, EvaluationDraftRead
from app.services.evaluation_draft_service import EvaluationDraftService

router = APIRouter(prefix="/evaluation-drafts", tags=["evaluation-drafts"])


class _CreateDraftBody:
    model_id: int


@router.post("", response_model=EvaluationDraftRead, status_code=status.HTTP_201_CREATED)
def create_draft(body: dict, db: Session = Depends(get_db)) -> EvaluationDraftRead:
    return EvaluationDraftService(db).create(body["model_id"])


@router.put("/{draft_id}/{dimension}", response_model=DimensionValidationRead)
def update_dimension(
    draft_id: uuid.UUID, dimension: str, body: dict, db: Session = Depends(get_db)
) -> DimensionValidationRead:
    return EvaluationDraftService(db).update_dimension(draft_id, dimension.upper(), body)


@router.post("/{draft_id}/{dimension}/confirm", response_model=EvaluationDraftRead)
def confirm_dimension(draft_id: uuid.UUID, dimension: str, db: Session = Depends(get_db)) -> EvaluationDraftRead:
    return EvaluationDraftService(db).confirm_dimension(draft_id, dimension.upper())


@router.get("/{draft_id}", response_model=EvaluationDraftRead)
def get_draft(draft_id: uuid.UUID, db: Session = Depends(get_db)) -> EvaluationDraftRead:
    return EvaluationDraftService(db).get(draft_id)
```

Replace the placeholder `body: dict` request parameters with a proper Pydantic body model (`class CreateDraftRequest(BaseModel): model_id: int`, defined in `app.schemas.evaluation_draft`) before merging — `dict` bodies skip FastAPI's request validation/OpenAPI docs. Add `CreateDraftRequest` to `evaluation_draft.py` and use it for `create_draft`; use `DimensionConfigUpdate` (already defined in Task 2.4) directly as the body type for `update_dimension` instead of `dict`.

- [ ] **Step 4: Register router**

In `backend/app/main.py`, add alongside the other v1 router registrations:

```python
from app.routers.v1 import evaluation_drafts

app.include_router(evaluation_drafts.router, prefix="/v1")
```

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && pytest tests/test_evaluation_drafts_router.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/v1/evaluation_drafts.py backend/app/main.py backend/app/schemas/evaluation_draft.py backend/tests/test_evaluation_drafts_router.py
git commit -m "feat: add evaluation draft API routes"
```

**Phase 2 complete when:** all tasks above pass; a draft can be created, a dimension validated with a real compatibility preview, explicitly confirmed, and read back — entirely independent of the existing evaluation-creation path, which remains untouched.

---

## Phase 3 — New wizard/intake flow using drafts

**Rollback/safety boundary:** New frontend pages/components only, reached via a new route (e.g. `/evaluations/new-v2`). The existing `/evaluations/new` wizard and `CreateEvaluationPage.tsx` are untouched — both routes coexist. Revert = remove the new route; zero backend risk since Phases 1-2 are additive.

**What old behavior remains temporarily:** The old wizard stays the default entry point (linked from wherever "New evaluation" is currently linked). The new wizard is reachable but not yet the primary path.

**What becomes impossible after this phase:** Nothing yet — both wizards coexist.

### Task 3.1: Frontend API types for dataset content + drafts

**Files:**
- Modify: `frontend/src/api/types.ts` (add new interfaces, do not touch existing `EvaluationContractV1`/`EvaluationCreate` etc. yet — those change in Phase 4)
- Test: none (pure type additions; covered indirectly by component tests in later tasks)

- [ ] **Step 1: Add types**

```typescript
// frontend/src/api/types.ts — append

export interface DatasetContentRead {
  id: string;
  content_hash: string;
  byte_size: number;
  format: string;
  row_count: number;
  columns: { name: string; inferred_type: string }[];
  created_at: string;
}

export interface DatasetFetchRequest {
  source_url: string;
}

export interface LabelMappingEntry {
  dataset_value: string;
  model_label_index: number;
}

export interface DimensionConfigUpdate {
  dataset_content_id: string;
  text_column: string;
  target_column: string;
  sensitive_column?: string;
  label_mapping: LabelMappingEntry[];
  min_group_n?: number;
}

export interface GroupPreviewEntry {
  value: string;
  count: number;
  meets_min_group_n: boolean;
}

export interface DimensionValidationRead {
  ok: boolean;
  errors: string[];
  group_preview?: GroupPreviewEntry[];
  groups_remaining?: number;
  n_label_compatible?: number;
  n_excluded?: number;
}

export type EvaluationDraftStatus = "incomplete" | "validated" | "consumed" | "stale";

export interface EvaluationDraftRead {
  id: string;
  model_id: number;
  status: EvaluationDraftStatus;
  fairness_confirmed: boolean;
  robustness_confirmed: boolean;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "feat: add frontend types for DatasetContent and EvaluationDraft"
```

### Task 3.2: Dataset intake component (fetch URL, show preview, map columns)

**Files:**
- Create: `frontend/src/components/DatasetIntakeForm.tsx`
- Test: `frontend/src/components/DatasetIntakeForm.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` (`frontend/src/api/client.ts`, existing), `DatasetContentRead`/`DatasetFetchRequest` (Task 3.1).
- Produces: `<DatasetIntakeForm onContentReady={(content: DatasetContentRead) => void} />`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/DatasetIntakeForm.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import DatasetIntakeForm from "./DatasetIntakeForm";
import { apiFetch } from "../api/client";

vi.mock("../api/client");

test("fetches dataset and reports content to parent", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce({
    id: "content-1",
    content_hash: "abc",
    byte_size: 100,
    format: "csv",
    row_count: 3,
    columns: [{ name: "text", inferred_type: "string" }],
    created_at: "2026-01-01T00:00:00Z",
  });
  const onReady = vi.fn();
  render(<DatasetIntakeForm onContentReady={onReady} />);

  fireEvent.change(screen.getByLabelText(/dataset url/i), { target: { value: "https://example.com/d.csv" } });
  fireEvent.click(screen.getByRole("button", { name: /fetch/i }));

  await waitFor(() => expect(onReady).toHaveBeenCalledWith(expect.objectContaining({ id: "content-1" })));
  expect(screen.getByText(/3 rows/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/components/DatasetIntakeForm.test.tsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/DatasetIntakeForm.tsx
import { useState } from "react";

import { apiFetch } from "../api/client";
import type { DatasetContentRead } from "../api/types";
import ErrorNotice from "./ErrorNotice";

export default function DatasetIntakeForm({
  onContentReady,
}: {
  onContentReady: (content: DatasetContentRead) => void;
}) {
  const [url, setUrl] = useState("");
  const [content, setContent] = useState<DatasetContentRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function fetchDataset() {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch<DatasetContentRead>("/v1/dataset-fetches", {
        method: "POST",
        body: { source_url: url.trim() },
      });
      setContent(result);
      onContentReady(result);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <ErrorNotice error={error} />
      <label>
        Dataset URL
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/dataset.csv"
        />
      </label>
      <button type="button" onClick={() => void fetchDataset()} disabled={loading || !url.trim()}>
        {loading ? "Fetching…" : "Fetch dataset"}
      </button>
      {content ? (
        <div>
          <p>
            {content.row_count} rows, {content.byte_size} bytes, format={content.format}
          </p>
          <ul>
            {content.columns.map((c) => (
              <li key={c.name}>
                {c.name} ({c.inferred_type})
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/components/DatasetIntakeForm.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DatasetIntakeForm.tsx frontend/src/components/DatasetIntakeForm.test.tsx
git commit -m "feat: add DatasetIntakeForm component"
```

### Task 3.3: Column-role + label-mapping form component

**Files:**
- Create: `frontend/src/components/ColumnRoleMappingForm.tsx`
- Test: `frontend/src/components/ColumnRoleMappingForm.test.tsx`

**Interfaces:**
- Consumes: `DatasetContentRead` (columns list), `apiFetch`, `DimensionConfigUpdate`/`DimensionValidationRead` (Task 3.1).
- Produces: `<ColumnRoleMappingForm draftId={string} dimension={"FAIRNESS"|"ROBUSTNESS"} content={DatasetContentRead} onValidated={(result: DimensionValidationRead) => void} />` — renders column-role selects, a label-mapping row per **discovered target value** (fetched via a small preview call — reuse `PUT .../{dimension}` itself as the validation call, no separate preview endpoint needed per Phase 2's design), and a "Save & validate" button that calls `PUT /v1/evaluation-drafts/{draftId}/{dimension}`. Never auto-selects a label mapping — every row starts unmapped and requires an explicit choice, per the locked "never auto-apply without confirm" rule.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/ColumnRoleMappingForm.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import ColumnRoleMappingForm from "./ColumnRoleMappingForm";
import { apiFetch } from "../api/client";

vi.mock("../api/client");

const CONTENT = {
  id: "content-1",
  content_hash: "abc",
  byte_size: 100,
  format: "csv",
  row_count: 5,
  columns: [
    { name: "text", inferred_type: "string" },
    { name: "label", inferred_type: "string" },
    { name: "group", inferred_type: "string" },
  ],
  created_at: "2026-01-01T00:00:00Z",
};

test("submits column roles and shows validation result", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce({
    ok: true,
    errors: [],
    group_preview: [{ value: "a", count: 3, meets_min_group_n: true }],
    groups_remaining: 2,
  });
  const onValidated = vi.fn();
  render(
    <ColumnRoleMappingForm draftId="draft-1" dimension="FAIRNESS" content={CONTENT} onValidated={onValidated} />
  );

  fireEvent.change(screen.getByLabelText(/text column/i), { target: { value: "text" } });
  fireEvent.change(screen.getByLabelText(/target column/i), { target: { value: "label" } });
  fireEvent.change(screen.getByLabelText(/sensitive column/i), { target: { value: "group" } });
  fireEvent.click(screen.getByRole("button", { name: /save.*validate/i }));

  await waitFor(() => expect(onValidated).toHaveBeenCalledWith(expect.objectContaining({ ok: true })));
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/components/ColumnRoleMappingForm.test.tsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/ColumnRoleMappingForm.tsx
import { useState } from "react";

import { apiFetch } from "../api/client";
import type { DatasetContentRead, DimensionValidationRead, LabelMappingEntry } from "../api/types";
import ErrorNotice from "./ErrorNotice";

export default function ColumnRoleMappingForm({
  draftId,
  dimension,
  content,
  onValidated,
}: {
  draftId: string;
  dimension: "FAIRNESS" | "ROBUSTNESS";
  content: DatasetContentRead;
  onValidated: (result: DimensionValidationRead) => void;
}) {
  const [textColumn, setTextColumn] = useState("");
  const [targetColumn, setTargetColumn] = useState("");
  const [sensitiveColumn, setSensitiveColumn] = useState("");
  const [labelMapping, setLabelMapping] = useState<LabelMappingEntry[]>([]);
  const [minGroupN, setMinGroupN] = useState(30);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const result = await apiFetch<DimensionValidationRead>(
        `/v1/evaluation-drafts/${draftId}/${dimension}`,
        {
          method: "PUT",
          body: {
            dataset_content_id: content.id,
            text_column: textColumn,
            target_column: targetColumn,
            sensitive_column: dimension === "FAIRNESS" ? sensitiveColumn : undefined,
            label_mapping: labelMapping,
            min_group_n: dimension === "FAIRNESS" ? minGroupN : undefined,
          },
        }
      );
      onValidated(result);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <ErrorNotice error={error} />
      <label>
        Text column
        <select value={textColumn} onChange={(e) => setTextColumn(e.target.value)}>
          <option value="">Select…</option>
          {content.columns.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Target column
        <select value={targetColumn} onChange={(e) => setTargetColumn(e.target.value)}>
          <option value="">Select…</option>
          {content.columns.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      {dimension === "FAIRNESS" ? (
        <>
          <label>
            Sensitive column
            <select value={sensitiveColumn} onChange={(e) => setSensitiveColumn(e.target.value)}>
              <option value="">Select…</option>
              {content.columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Minimum group size
            <input
              type="number"
              min={1}
              value={minGroupN}
              onChange={(e) => setMinGroupN(Number(e.target.value))}
            />
          </label>
        </>
      ) : null}
      {/* Label-mapping rows: populated from an explicit "discover values" step
          not yet wired here — deferred to Task 3.4, which adds a
          GET-based values discovery call and renders one mapping row per
          observed dataset value, each defaulting to unmapped. */}
      <button type="button" onClick={() => void submit()} disabled={submitting}>
        {submitting ? "Validating…" : "Save & validate"}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/components/ColumnRoleMappingForm.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ColumnRoleMappingForm.tsx frontend/src/components/ColumnRoleMappingForm.test.tsx
git commit -m "feat: add ColumnRoleMappingForm component"
```

### Task 3.4: Label-mapping rows with never-auto-apply confirmation UI

**Files:**
- Modify: `frontend/src/components/ColumnRoleMappingForm.tsx` (fill in the deferred label-mapping section from Task 3.3)
- Modify: `backend/app/routers/v1/evaluation_drafts.py` (add a values-discovery endpoint)
- Modify: `backend/app/services/evaluation_draft_service.py` (add `discover_target_values`)
- Test: `backend/tests/test_evaluation_drafts_router.py` (extend), `frontend/src/components/ColumnRoleMappingForm.test.tsx` (extend)

**Interfaces:**
- Produces: `GET /v1/evaluation-drafts/{id}/{dimension}/target-values?dataset_content_id=...&target_column=...` -> `{values: string[]}` (distinct observed target values, for populating mapping rows before the user has saved anything yet).

- [ ] **Step 1: Write the failing backend test**

```python
# backend/tests/test_evaluation_drafts_router.py — append

def test_target_values_discovery(client, seeded_model, seeded_dataset_content):
    created = client.post("/v1/evaluation-drafts", json={"model_id": seeded_model.id}).json()
    resp = client.get(
        f"/v1/evaluation-drafts/{created['id']}/FAIRNESS/target-values",
        params={"dataset_content_id": str(seeded_dataset_content.id), "target_column": "label"},
    )
    assert resp.status_code == 200
    assert set(resp.json()["values"]) == {"pos", "neg"}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_evaluation_drafts_router.py -v`
Expected: FAIL — 404 on the new route.

- [ ] **Step 3: Implement backend**

```python
# backend/app/services/evaluation_draft_service.py — add method to EvaluationDraftService

def discover_target_values(self, dataset_content_id, target_column: str) -> list[str]:
    content = self._contents.get_by_id(dataset_content_id)
    if content is None:
        raise NotFoundError(f"DatasetContent {dataset_content_id} not found")
    store = get_dataset_content_store(get_settings())
    data = store.get(content.storage_uri)
    from app.services.draft_validation import _observed_target_values

    return sorted(_observed_target_values(data, target_column))
```

```python
# backend/app/routers/v1/evaluation_drafts.py — add route

import uuid as _uuid


@router.get("/{draft_id}/{dimension}/target-values")
def get_target_values(
    draft_id: _uuid.UUID,
    dimension: str,
    dataset_content_id: _uuid.UUID,
    target_column: str,
    db: Session = Depends(get_db),
) -> dict:
    values = EvaluationDraftService(db).discover_target_values(dataset_content_id, target_column)
    return {"values": values}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_evaluation_drafts_router.py -v`
Expected: PASS.

- [ ] **Step 5: Implement frontend mapping rows**

Replace the comment placeholder in `ColumnRoleMappingForm.tsx` with:

```tsx
// after targetColumn is chosen, fetch distinct values and render one row each
import { useEffect } from "react";

// inside the component, after existing state:
const [targetValues, setTargetValues] = useState<string[]>([]);
const modelLabels = ["NEGATIVE", "POSITIVE"]; // replace with real id2label passed as a prop once EvaluationDraftRead exposes model_label_snapshot to the frontend (Task 4.x)

useEffect(() => {
  if (!targetColumn) return;
  void apiFetch<{ values: string[] }>(
    `/v1/evaluation-drafts/${draftId}/${dimension}/target-values?dataset_content_id=${content.id}&target_column=${targetColumn}`
  ).then((res) => {
    setTargetValues(res.values);
    setLabelMapping(res.values.map((v) => ({ dataset_value: v, model_label_index: -1 })));
  });
}, [targetColumn]);

// render (replace the placeholder comment):
{targetValues.length > 0 ? (
  <fieldset>
    <legend>Map dataset labels to model labels</legend>
    {targetValues.map((value, idx) => (
      <label key={value}>
        {value} →
        <select
          value={labelMapping[idx]?.model_label_index ?? -1}
          onChange={(e) => {
            const next = [...labelMapping];
            next[idx] = { dataset_value: value, model_label_index: Number(e.target.value) };
            setLabelMapping(next);
          }}
        >
          <option value={-1}>Select model label…</option>
          {modelLabels.map((label, i) => (
            <option key={label} value={i}>
              {label}
            </option>
          ))}
        </select>
      </label>
    ))}
  </fieldset>
) : null}
```

Every row defaults to `model_label_index: -1` ("unmapped") — the "Save & validate" submit already fails server-side (`_validate_label_mapping`'s "missing entries" check) if any row is left at `-1`, since `-1` won't match any real `id2label` key. This is the mechanism enforcing "never auto-apply" — there is no default guess, ever.

- [ ] **Step 6: Run to verify pass**

Run: `cd frontend && npx vitest run src/components/ColumnRoleMappingForm.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/evaluation_draft_service.py backend/app/routers/v1/evaluation_drafts.py backend/tests/test_evaluation_drafts_router.py frontend/src/components/ColumnRoleMappingForm.tsx frontend/src/components/ColumnRoleMappingForm.test.tsx
git commit -m "feat: add target-value discovery and never-auto-apply label mapping rows"
```

### Task 3.5: New wizard page wiring it all together

**Files:**
- Create: `frontend/src/pages/CreateEvaluationDraftPage.tsx`
- Modify: `frontend/src/App.tsx` (add route, e.g. `/evaluations/new-v2`, alongside existing `/evaluations/new`)
- Test: `frontend/src/pages/CreateEvaluationDraftPage.test.tsx`

**Interfaces:**
- Consumes: `DatasetIntakeForm` (3.2), `ColumnRoleMappingForm` (3.3/3.4), `apiFetch`.
- Produces: a page component that steps through model selection (reuse existing model-picker logic from `CreateEvaluationPage.tsx` rather than rewriting it) → creates a draft → shows `DatasetIntakeForm` + `ColumnRoleMappingForm` for Fairness and/or Robustness (each optional, a checkbox to enable) → confirm buttons per dimension → a "Continue" button disabled until every enabled dimension is confirmed.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/CreateEvaluationDraftPage.test.tsx
import { render, screen } from "@testing-library/react";

import CreateEvaluationDraftPage from "./CreateEvaluationDraftPage";

test("renders dimension toggles", () => {
  render(<CreateEvaluationDraftPage />);
  expect(screen.getByLabelText(/configure fairness/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/configure robustness/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/pages/CreateEvaluationDraftPage.test.tsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement** (skeleton — model-picker step reuses the existing pattern from `CreateEvaluationPage.tsx`'s `load()`/model-select step; copy that step's JSX and data-fetching verbatim rather than re-deriving it)

```tsx
// frontend/src/pages/CreateEvaluationDraftPage.tsx
import { useState } from "react";

import { apiFetch } from "../api/client";
import ColumnRoleMappingForm from "../components/ColumnRoleMappingForm";
import DatasetIntakeForm from "../components/DatasetIntakeForm";
import type { DatasetContentRead, EvaluationDraftRead } from "../api/types";

export default function CreateEvaluationDraftPage() {
  const [modelId, setModelId] = useState<number | null>(null);
  const [draft, setDraft] = useState<EvaluationDraftRead | null>(null);
  const [enableFairness, setEnableFairness] = useState(false);
  const [enableRobustness, setEnableRobustness] = useState(false);
  const [fairnessContent, setFairnessContent] = useState<DatasetContentRead | null>(null);
  const [robustnessContent, setRobustnessContent] = useState<DatasetContentRead | null>(null);

  async function startDraft() {
    if (modelId === null) return;
    const created = await apiFetch<EvaluationDraftRead>("/v1/evaluation-drafts", {
      method: "POST",
      body: { model_id: modelId },
    });
    setDraft(created);
  }

  const readyToContinue =
    draft !== null &&
    (!enableFairness || draft.fairness_confirmed) &&
    (!enableRobustness || draft.robustness_confirmed);

  return (
    <div>
      {/* Model picker step: reuse CreateEvaluationPage.tsx's existing model-select
          markup/data-fetching verbatim here instead of re-deriving it. */}
      <button type="button" onClick={() => void startDraft()} disabled={modelId === null || draft !== null}>
        Start draft
      </button>

      {draft ? (
        <>
          <label>
            <input type="checkbox" checked={enableFairness} onChange={(e) => setEnableFairness(e.target.checked)} />
            Configure Fairness
          </label>
          {enableFairness ? (
            <>
              <DatasetIntakeForm onContentReady={setFairnessContent} />
              {fairnessContent ? (
                <ColumnRoleMappingForm
                  draftId={draft.id}
                  dimension="FAIRNESS"
                  content={fairnessContent}
                  onValidated={() => {}}
                />
              ) : null}
            </>
          ) : null}

          <label>
            <input
              type="checkbox"
              checked={enableRobustness}
              onChange={(e) => setEnableRobustness(e.target.checked)}
            />
            Configure Robustness
          </label>
          {enableRobustness ? (
            <>
              <DatasetIntakeForm onContentReady={setRobustnessContent} />
              {robustnessContent ? (
                <ColumnRoleMappingForm
                  draftId={draft.id}
                  dimension="ROBUSTNESS"
                  content={robustnessContent}
                  onValidated={() => {}}
                />
              ) : null}
            </>
          ) : null}

          <button type="button" disabled={!readyToContinue}>
            Continue to review
          </button>
        </>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Add route**

In `frontend/src/App.tsx`, alongside the existing `<Route path="/evaluations/new" element={<CreateEvaluationPage />} />`, add:

```tsx
<Route path="/evaluations/new-v2" element={<CreateEvaluationDraftPage />} />
```

- [ ] **Step 5: Run to verify pass**

Run: `cd frontend && npx vitest run src/pages/CreateEvaluationDraftPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/CreateEvaluationDraftPage.tsx frontend/src/App.tsx frontend/src/pages/CreateEvaluationDraftPage.test.tsx
git commit -m "feat: add new draft-based evaluation creation wizard at /evaluations/new-v2"
```

**Phase 3 complete when:** all tasks above pass; a user can reach `/evaluations/new-v2`, pick a model, fetch/validate/confirm a Fairness and/or Robustness dataset, and see "Continue to review" enable — the old `/evaluations/new` wizard is untouched and still the default link target.

---

## Phase 4 — New EvaluationContractV1 and evaluation creation/worker consumption

**Rollback/safety boundary:** This is the first phase that touches shared, already-in-use code (`EvaluationContractV1`, `ProbeContext`, `run_all_probes`). Mitigate by introducing the new contract shape as `EvaluationContractV2` (a new Pydantic model, new module) rather than mutating `EvaluationContractV1` in place, and by making `ProbeContext.evaluation_contract` accept either shape via a union type during this phase only — the old `EvaluationContractV1` and its `build_evaluation_contract` path keep working unchanged for any evaluation created via the old `POST /v1/evaluations` body shape. Rollback = stop routing new evaluations through the new path; nothing already-created is affected either way since contracts are frozen per-evaluation at creation time.

**What old behavior remains temporarily:** Old `POST /v1/evaluations` (pairing/dataset_key/proxy_lr body) keeps creating evaluations with the old flat `EvaluationContractV1`. A new `POST /v1/evaluations-v2 {draft_id, evaluation_mode}` creates evaluations with the new per-dimension contract. Both paths' evaluations run through the same worker/probe code, which is taught to branch on which contract shape it received.

**What becomes impossible after this phase:** Nothing yet for existing users — this is additive at the API level. It does establish the real worker-side contract consumption, which Phase 6 will make the only path.

### Task 4.1: New contract schemas (`FairnessContractV2`/`RobustnessContractV2`/`EvaluationContractV2`)

**Files:**
- Create: `backend/app/schemas/evaluation_contract_v2.py`
- Test: `backend/tests/test_evaluation_contract_v2_schema.py`

**Interfaces:**
- Produces: `LabelMappingEntry`, `ModelLabelSnapshot`, `FairnessContractV2`, `RobustnessContractV2`, `EvaluationContractV2` — exact shape from the Global Constraints / earlier design ("A. Recommended EvaluationContractV1" from the design conversation).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_evaluation_contract_v2_schema.py
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    FairnessContractV2,
    LabelMappingEntry,
    ModelLabelSnapshot,
)


def test_contract_allows_both_dimensions_null():
    contract = EvaluationContractV2(
        model_ref="distilbert-base-uncased-finetuned-sst-2-english",
        model_revision="main",
        resolved_model_sha="abc123",
        model_label_snapshot=ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}),
        fairness=None,
        robustness=None,
    )
    assert contract.fairness is None
    assert contract.robustness is None


def test_fairness_contract_requires_sensitive_column():
    fairness = FairnessContractV2(
        dataset_content_id="00000000-0000-0000-0000-000000000001",
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[LabelMappingEntry(dataset_value="pos", model_label_index=1)],
        min_group_n=30,
    )
    assert fairness.sensitive_column == "group"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_evaluation_contract_v2_schema.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/app/schemas/evaluation_contract_v2.py
"""V1 redesign: per-dimension optional contract, content-addressed dataset
reference, explicit label mapping. Coexists with the legacy flat
EvaluationContractV1 in app.schemas.evaluation_contract during the
migration (Phases 4-6); the legacy module is deleted in Phase 7."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class LabelMappingEntry(BaseModel):
    dataset_value: str
    model_label_index: int


class ModelLabelSnapshot(BaseModel):
    num_labels: int
    id2label: dict[int, str]


class FairnessContractV2(BaseModel):
    dataset_content_id: uuid.UUID
    text_column: str
    target_column: str
    sensitive_column: str
    label_mapping: list[LabelMappingEntry]
    min_group_n: int


class RobustnessContractV2(BaseModel):
    dataset_content_id: uuid.UUID
    text_column: str
    target_column: str
    label_mapping: list[LabelMappingEntry]


class EvaluationContractV2(BaseModel):
    schema_version: Literal["v2"] = "v2"
    model_ref: str
    model_revision: str
    resolved_model_sha: str
    model_label_snapshot: ModelLabelSnapshot
    fairness: FairnessContractV2 | None = None
    robustness: RobustnessContractV2 | None = None


__all__ = [
    "LabelMappingEntry",
    "ModelLabelSnapshot",
    "FairnessContractV2",
    "RobustnessContractV2",
    "EvaluationContractV2",
]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_evaluation_contract_v2_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/evaluation_contract_v2.py backend/tests/test_evaluation_contract_v2_schema.py
git commit -m "feat: add EvaluationContractV2 schema (per-dimension, content-addressed)"
```

### Task 4.2: `methodology_version` on `Evaluation` + `Report`

**Files:**
- Modify: `backend/app/db/models.py` (`Evaluation` gets `methodology_version: Mapped[str]` non-nullable with a server default of the legacy tag; `Report` unaffected at the DB level — its version lives only inside the stored JSON, not a DB column, since `ReportV1` is a MinIO-stored document, not a queryable row)
- Create: `backend/alembic/versions/XXX_add_methodology_version.py`
- Modify: `backend/app/schemas/reports.py` (`ReportV1.methodology_version: str` required; `ReportRead.methodology_version: str | None`)
- Test: `backend/tests/test_methodology_version_migration.py`

**Interfaces:**
- Produces: `CURRENT_METHODOLOGY_VERSION = "v2-per-dimension-2026"` constant (module: `backend/app/scoring/methodology_version.py`), `LEGACY_METHODOLOGY_VERSION = "pre-v1-fixed-5dim"`.

- [ ] **Step 1: Add the constants module**

```python
# backend/app/scoring/methodology_version.py
"""Single source of truth for the methodology_version stamped onto every
Evaluation at creation time (immutable thereafter) and copied verbatim into
every newly generated ReportV1. Legacy evaluations/reports predating this
field carry LEGACY_METHODOLOGY_VERSION (backend) or None (ReportRead, since
old stored report.json blobs genuinely never recorded any value at all —
see docs/superpowers/plans/2026-09-10-v1-dataset-contract-redesign.md
Global Constraints)."""

CURRENT_METHODOLOGY_VERSION = "v2-per-dimension-2026"
LEGACY_METHODOLOGY_VERSION = "pre-v1-fixed-5dim"
```

- [ ] **Step 2: Add column + migration**

```python
# backend/app/db/models.py — modify Evaluation class, add one field

    methodology_version: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="pre-v1-fixed-5dim"
    )
```

Run: `cd backend && alembic revision --autogenerate -m "add methodology_version to evaluations"`

Verify the generated migration's `server_default` matches `LEGACY_METHODOLOGY_VERSION` exactly (`"pre-v1-fixed-5dim"`) so every pre-existing row is explicitly backfilled, never left `NULL` (per the locked decision — explicit legacy value, not NULL-as-convention). After confirming, remove the `server_default` from a second migration step if you don't want new rows silently inheriting it — new rows must always pass `methodology_version` explicitly from application code (Task 4.4), the server default only exists to backfill existing rows during this migration.

- [ ] **Step 3: Apply and verify**

Run: `cd backend && alembic upgrade head`

```python
# backend/tests/test_methodology_version_migration.py
from app.db.repositories.evaluation import EvaluationRepository
from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION


def test_existing_rows_backfilled_to_legacy_value(db_session, seeded_evaluation):
    row = EvaluationRepository(db_session).get_by_id(seeded_evaluation.id)
    assert row.methodology_version == LEGACY_METHODOLOGY_VERSION
```

Use whatever fixture already seeds a plain `Evaluation` row for existing tests (e.g. the one `test_evaluation_lifecycle.py` uses) as `seeded_evaluation` — don't invent a new one.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_methodology_version_migration.py -v`
Expected: PASS.

- [ ] **Step 5: Update report schemas**

```python
# backend/app/schemas/reports.py — modify ReportV1 and ReportRead

class ReportV1(BaseModel):
    ...
    methodology_version: str  # required, non-null for every newly generated report
    ...


class ReportRead(BaseModel):
    ...
    methodology_version: str | None = None  # None = legacy report, predates this field
    ...
```

Also modify `_to_read` in `backend/app/services/report_service.py` to pull `methodology_version` out of `report_json.get("methodology_version")` (returns `None` automatically for legacy blobs lacking the key — no sentinel injected, per the locked decision):

```python
# backend/app/services/report_service.py — modify _to_read

        return ReportRead(
            ...,
            methodology_version=report_json.get("methodology_version"),
        )
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/scoring/methodology_version.py backend/app/db/models.py backend/alembic/versions/ backend/app/schemas/reports.py backend/app/services/report_service.py backend/tests/test_methodology_version_migration.py
git commit -m "feat: add methodology_version to Evaluation (backfilled legacy) and ReportV1/ReportRead"
```

### Task 4.3: NOT_APPLICABLE-aware confidence aggregation, gated by `methodology_version`

**Files:**
- Modify: `backend/app/confidence/engine.py` (`summarize` gains a `methodology_version: str` parameter)
- Modify: `backend/app/osd/serialize.py` (`to_ai_suggestion` gains a `required_aspect_count: int` parameter, replacing the hardcoded `FRIES_ASPECT_COUNT`)
- Modify every call site of `summarize()`/`to_ai_suggestion()` (`evaluation_service.py::get_confidence_summary`, `tasks/evaluate_pipeline.py::_run_osd_agent`)
- Test: `backend/tests/test_confidence_engine.py` (extend)

**Interfaces:**
- Modifies: `summarize(rows, *, methodology_version: str) -> ConfidenceSummary` — when `methodology_version != LEGACY_METHODOLOGY_VERSION`, rows whose `metric_values.get("probe_status") == "not_applicable"` are excluded from the geometric mean (still present in `by_dimension` for display, valued `None`); when `methodology_version == LEGACY_METHODOLOGY_VERSION`, behavior is byte-for-byte unchanged from today (NOT_APPLICABLE rows still folded in at their stored confidence).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_confidence_engine.py — append

from app.confidence.engine import summarize
from app.db.enums import FriesDimension
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION, LEGACY_METHODOLOGY_VERSION


def _rows_with_not_applicable_fairness():
    return [
        (FriesDimension.FAIRNESS, 0.4, {"probe_status": "not_applicable"}),
        (FriesDimension.ROBUSTNESS, 0.9, {"clean_accuracy": 0.8}),
        (FriesDimension.INTEGRITY, 0.9, {}),
        (FriesDimension.EXPLAINABILITY, 0.9, {}),
        (FriesDimension.SAFETY, 0.9, {}),
    ]


def test_legacy_version_folds_not_applicable_into_overall():
    summary = summarize(_rows_with_not_applicable_fairness(), methodology_version=LEGACY_METHODOLOGY_VERSION)
    assert summary.by_dimension["FAIRNESS"] == 0.4
    assert summary.overall < 0.9  # dragged down by the included 0.4


def test_current_version_excludes_not_applicable_from_overall():
    summary = summarize(_rows_with_not_applicable_fairness(), methodology_version=CURRENT_METHODOLOGY_VERSION)
    assert summary.overall == pytest.approx(0.9, abs=1e-6)  # geometric mean of four 0.9s, FAIRNESS excluded
```

Add `import pytest` to the top of the test file if not already present.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_confidence_engine.py -v`
Expected: FAIL — `summarize()` doesn't accept `methodology_version`.

- [ ] **Step 3: Implement**

```python
# backend/app/confidence/engine.py — modify summarize()

from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION


def summarize(
    rows: Sequence[tuple[FriesDimension, float | None, dict[str, Any]]],
    *,
    methodology_version: str,
) -> ConfidenceSummary:
    by_dimension: dict[str, float | None] = {}
    included_values: list[float] = []
    for dimension, confidence, metric_values in rows:
        metric_values = metric_values or {}
        is_not_applicable = metric_values.get("probe_status") == "not_applicable"
        if confidence is not None:
            value = round(_clamp(float(confidence)), 4)
        else:
            value = refine(dimension, metric_values=metric_values, evidence_refs=[True]).confidence

        exclude = is_not_applicable and methodology_version != LEGACY_METHODOLOGY_VERSION
        by_dimension[dimension.value] = None if exclude else value
        if not exclude:
            included_values.append(value)

    overall = round(geometric_mean(included_values), 4) if included_values else 0.0
    return ConfidenceSummary(overall=overall, by_dimension=by_dimension)
```

`ConfidenceSummary.by_dimension` type changes from `dict[str, float]` to `dict[str, float | None]` — update its Pydantic field type in the same file.

- [ ] **Step 4: Update call sites**

```python
# backend/app/services/evaluation_service.py — modify get_confidence_summary

    def get_confidence_summary(self, evaluation_id: uuid.UUID) -> ConfidenceSummary | None:
        rows = self._probes.list_for_evaluation(evaluation_id)
        if not rows:
            return None
        evaluation = self.get_evaluation(evaluation_id)
        return summarize(
            [(row.dimension, row.confidence, row.metric_values or {}) for row in rows],
            methodology_version=evaluation.methodology_version,
        )
```

```python
# backend/app/tasks/evaluate_pipeline.py — modify _run_osd_agent's summarize() call

    confidence_summary = (
        summarize(
            [(row.dimension, row.confidence, row.metric_values or {}) for row in probe_rows],
            methodology_version=payload.methodology_version,
        ).model_dump()
        if probe_rows
        else None
    )
```

`EvaluateModelPayload` (`backend/app/schemas/internal.py`) needs a new `methodology_version: str` field threaded through from `EvaluationService.create_evaluation` — add it there in Task 4.4.

- [ ] **Step 5: Also gate `FRIES_ASPECT_COUNT`**

```python
# backend/app/osd/serialize.py — modify to_ai_suggestion

def to_ai_suggestion(result: AgentResult, *, required_aspect_count: int) -> dict[str, Any]:
    complete_count = sum(1 for aspect in result.aspects if osd_triple_complete(aspect))
    scoring_complete = complete_count == required_aspect_count
    ...
```

Update its one call site in `tasks/evaluate_pipeline.py::_run_osd_agent` to pass `required_aspect_count=FRIES_ASPECT_COUNT - not_applicable_dimension_count`, where `not_applicable_dimension_count` is derived from `probe_rows` the same way `summarize()` does — compute it once in `_run_osd_agent` and pass to both `summarize()`'s exclusion (already handled per-row above) and `to_ai_suggestion`.

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && pytest tests/test_confidence_engine.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/confidence/engine.py backend/app/services/evaluation_service.py backend/app/tasks/evaluate_pipeline.py backend/app/osd/serialize.py backend/tests/test_confidence_engine.py
git commit -m "feat: gate NOT_APPLICABLE confidence/FRIES exclusion by methodology_version"
```

### Task 4.4: `POST /v1/evaluations-v2` — consumes draft, freezes `EvaluationContractV2`

**Files:**
- Create: `backend/app/services/evaluation_service_v2.py`
- Modify: `backend/app/routers/v1/evaluations.py` (add new route, do not touch the existing `create_evaluation`)
- Modify: `backend/app/schemas/internal.py` (`EvaluateModelPayload` gains `methodology_version: str`, `evaluation_contract` stays `dict` — already schema-agnostic)
- Test: `backend/tests/test_evaluation_service_v2.py`

**Interfaces:**
- Produces: `EvaluationServiceV2.create_from_draft(draft_id: uuid.UUID, evaluation_mode: EvaluationMode) -> Evaluation`, `POST /v1/evaluations-v2 {draft_id, evaluation_mode}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_evaluation_service_v2.py
import pytest

from app.api.errors import ConflictError
from app.db.enums import EvaluationMode
from app.services.evaluation_service_v2 import EvaluationServiceV2


def test_create_from_confirmed_draft_freezes_contract(db_session, confirmed_fairness_draft):
    service = EvaluationServiceV2(db_session)
    evaluation = service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)
    contract = evaluation.probe_config["evaluation_contract"]
    assert contract["schema_version"] == "v2"
    assert contract["fairness"] is not None
    assert contract["robustness"] is None
    assert evaluation.methodology_version == "v2-per-dimension-2026"


def test_create_from_draft_rejects_stale_model_revision(db_session, confirmed_fairness_draft, seeded_model):
    seeded_model.revision = "a-different-revision"
    db_session.flush()
    service = EvaluationServiceV2(db_session)
    with pytest.raises(ConflictError, match="stale"):
        service.create_from_draft(confirmed_fairness_draft.id, EvaluationMode.AI_ASSISTED)


def test_create_from_draft_rejects_half_confirmed_dimension(db_session, half_confirmed_draft):
    service = EvaluationServiceV2(db_session)
    with pytest.raises(ConflictError, match="not confirmed"):
        service.create_from_draft(half_confirmed_draft.id, EvaluationMode.AI_ASSISTED)
```

Add `confirmed_fairness_draft` and `half_confirmed_draft` fixtures to `backend/tests/conftest.py`, built via `EvaluationDraftService` from Phase 2 (create a draft, validate + confirm Fairness only for the first; validate but *not* confirm for the second).

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_evaluation_service_v2.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/app/services/evaluation_service_v2.py
"""Consumes a validated EvaluationDraft atomically into a frozen Evaluation
with EvaluationContractV2. Re-verifies the draft is not stale (model
revision unchanged since the draft's model snapshot was captured) and that
every dimension the draft touched is either fully confirmed or fully
untouched (never half-filled) before freezing anything."""

from __future__ import annotations

import uuid

from app.api.errors import ConflictError, NotFoundError
from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import Evaluation
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_draft import EvaluationDraftRepository
from app.db.repositories.model import ModelRepository
from app.inference.model_inspection import inspect_model_config
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    FairnessContractV2,
    ModelLabelSnapshot,
    RobustnessContractV2,
)
from app.schemas.internal import EvaluateModelPayload
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION
from app.tasks.celery_client import enqueue_evaluate_model


class EvaluationServiceV2:
    def __init__(self, session) -> None:
        self._session = session
        self._drafts = EvaluationDraftRepository(session)
        self._models = ModelRepository(session)
        self._evals = EvaluationRepository(session)

    def create_from_draft(self, draft_id: uuid.UUID, evaluation_mode: EvaluationMode) -> Evaluation:
        draft = self._drafts.get_by_id(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found", details={"draft_id": str(draft_id)})
        if draft.status == "consumed":
            raise ConflictError("Draft already consumed", details={"draft_id": str(draft_id)})

        model = self._models.get_by_id(draft.model_id)
        current_snapshot = inspect_model_config(model.hf_repo_id, revision=model.revision, hf_token=None)
        if current_snapshot.resolved_sha != draft.resolved_model_sha:
            draft.status = "stale"
            self._session.flush()
            raise ConflictError(
                "Draft is stale — model revision changed since intake; re-validate before submitting",
                details={
                    "draft_id": str(draft_id),
                    "draft_sha": draft.resolved_model_sha,
                    "current_sha": current_snapshot.resolved_sha,
                },
            )

        fairness_contract: FairnessContractV2 | None = None
        robustness_contract: RobustnessContractV2 | None = None
        for dim in draft.dimensions:
            if dim.dataset_content_id is None:
                continue
            if dim.confirmed_at is None:
                raise ConflictError(
                    f"{dim.dimension} is configured but not confirmed — confirm or clear it before submitting",
                    details={"draft_id": str(draft_id), "dimension": dim.dimension},
                )
            label_mapping = [{"dataset_value": e["dataset_value"], "model_label_index": e["model_label_index"]} for e in dim.label_mapping]
            if dim.dimension == "FAIRNESS":
                fairness_contract = FairnessContractV2(
                    dataset_content_id=dim.dataset_content_id,
                    text_column=dim.text_column,
                    target_column=dim.target_column,
                    sensitive_column=dim.sensitive_column,
                    label_mapping=label_mapping,
                    min_group_n=dim.min_group_n or 30,
                )
            elif dim.dimension == "ROBUSTNESS":
                robustness_contract = RobustnessContractV2(
                    dataset_content_id=dim.dataset_content_id,
                    text_column=dim.text_column,
                    target_column=dim.target_column,
                    label_mapping=label_mapping,
                )

        contract = EvaluationContractV2(
            model_ref=model.hf_repo_id,
            model_revision=model.revision,
            resolved_model_sha=current_snapshot.resolved_sha,
            model_label_snapshot=ModelLabelSnapshot(
                num_labels=current_snapshot.num_labels, id2label=current_snapshot.id2label
            ),
            fairness=fairness_contract,
            robustness=robustness_contract,
        )

        probe_config = {"evaluation_contract": contract.model_dump(mode="json"), "assessment_engine": "deterministic"}
        row = self._evals.create(
            model_id=model.id,
            evaluation_mode=evaluation_mode,
            status=EvaluationStatus.PENDING,
            probe_config=probe_config,
            model_revision=model.revision,
        )
        row.methodology_version = CURRENT_METHODOLOGY_VERSION
        self._session.flush()

        draft.status = "consumed"
        self._session.flush()

        payload = EvaluateModelPayload(
            evaluation_id=row.id,
            model_ref=model.hf_repo_id,
            evaluation_mode=row.evaluation_mode,
            probe_config=row.probe_config or {},
            model_revision=row.model_revision,
            evaluation_contract=probe_config["evaluation_contract"],
            methodology_version=CURRENT_METHODOLOGY_VERSION,
        )
        enqueue_evaluate_model(payload)
        return row
```

Add `methodology_version: str` as a required field to `EvaluateModelPayload` in `backend/app/schemas/internal.py`.

- [ ] **Step 4: Add router**

```python
# backend/app/routers/v1/evaluations.py — add alongside existing create_evaluation

import uuid as _uuid

from app.db.enums import EvaluationMode
from app.services.evaluation_service_v2 import EvaluationServiceV2


@router.post("-v2", response_model=EvaluationRead, status_code=status.HTTP_201_CREATED)
def create_evaluation_v2(
    body: dict,
    db: Session = Depends(get_db),
) -> EvaluationRead:
    row = EvaluationServiceV2(db).create_from_draft(_uuid.UUID(body["draft_id"]), EvaluationMode(body["evaluation_mode"]))
    return EvaluationRead.model_validate(row)
```

Replace the `body: dict` placeholder with a proper `CreateEvaluationV2Request(BaseModel)` schema (`draft_id: uuid.UUID`, `evaluation_mode: EvaluationMode`) in `backend/app/schemas/evaluation_draft.py` before merging, matching the same correction noted in Task 2.5.

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && pytest tests/test_evaluation_service_v2.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/evaluation_service_v2.py backend/app/routers/v1/evaluations.py backend/app/schemas/internal.py backend/tests/test_evaluation_service_v2.py
git commit -m "feat: add POST /v1/evaluations-v2 consuming drafts into EvaluationContractV2"
```

### Task 4.5: Worker/probe consumption of `EvaluationContractV2`

**Files:**
- Modify: `backend/app/probes/base.py` (`ProbeContext.evaluation_contract` type becomes `EvaluationContractV1 | EvaluationContractV2 | None`)
- Modify: `backend/app/probes/runner.py` (`run_all_probes` detects `schema_version` to pick the right Pydantic model when parsing `payload.evaluation_contract`)
- Modify: `backend/app/probes/fairness.py` (`run()` branches: if `ctx.evaluation_contract` is a `EvaluationContractV2`, read `ctx.evaluation_contract.fairness`; if `None`, take the existing `_run_no_contract` path unchanged)
- Modify: `backend/app/probes/robustness.py` (same branching for `.robustness`)
- Modify: `backend/app/storage/evidence_store.py` is already done (Task 1.2's `DatasetContentStore`); wire it into `ProbeContext` as a new `dataset_content_store` field alongside the existing `dataset_store`
- Test: `backend/tests/test_fairness_contract_v2.py`, `backend/tests/test_robustness_contract_v2.py`

**Interfaces:**
- Modifies: `ProbeContext` gains `dataset_content_store: DatasetContentStore | None = None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_fairness_contract_v2.py
from app.db.enums import ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe
from app.schemas.evaluation_contract_v2 import EvaluationContractV2, ModelLabelSnapshot


def test_fairness_none_contract_is_not_applicable(fake_evidence_store, fake_probe_config):
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="m",
        model_metadata={},
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=EvaluationContractV2(
            model_ref="m", model_revision="r", resolved_model_sha="sha",
            model_label_snapshot=ModelLabelSnapshot(num_labels=2, id2label={0: "A", 1: "B"}),
            fairness=None, robustness=None,
        ),
    )
    output = FairnessProbe().run(ctx)
    assert output.status == ProbeEvaluationStatus.NOT_APPLICABLE
```

Reuse `fake_evidence_store`/`fake_probe_config` fixtures already used by existing `test_fairness_probe.py` — check that file's fixture names and import them the same way; add `import uuid` at the top.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_fairness_contract_v2.py -v`
Expected: FAIL — `FairnessProbe.run` doesn't understand `EvaluationContractV2`.

- [ ] **Step 3: Implement branching**

```python
# backend/app/probes/base.py — modify ProbeContext

from app.schemas.evaluation_contract_v2 import EvaluationContractV2
from app.storage.evidence_store import DatasetContentStore

@dataclass
class ProbeContext:
    ...
    evaluation_contract: EvaluationContractV1 | EvaluationContractV2 | None = None
    dataset_store: DatasetStore | None = None
    dataset_content_store: DatasetContentStore | None = None
```

```python
# backend/app/probes/runner.py — modify run_all_probes' contract parsing

from app.schemas.evaluation_contract_v2 import EvaluationContractV2

    raw_contract = payload.evaluation_contract
    contract: EvaluationContractV1 | EvaluationContractV2 | None = None
    if raw_contract:
        if raw_contract.get("schema_version") == "v2":
            contract = EvaluationContractV2.model_validate(raw_contract)
        else:
            contract = EvaluationContractV1.model_validate(raw_contract)
```

```python
# backend/app/probes/fairness.py — modify run(), at the very top, before existing `kind = contract.kind if ...` logic

from app.schemas.evaluation_contract_v2 import EvaluationContractV2

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        contract = ctx.evaluation_contract
        if isinstance(contract, EvaluationContractV2):
            return self._run_v2(ctx, contract)
        # ... existing V1 kind-dispatch logic unchanged below ...

    def _run_v2(self, ctx: ProbeContext, contract: EvaluationContractV2) -> ProbeOutput:
        if contract.fairness is None:
            return self._run_no_contract(ctx, contract=None, reason="Fairness was not configured for this evaluation")
        fc = contract.fairness
        content = ctx.dataset_content_store  # fetch bytes, hash-verify, parse — mirrors _run_user_dataset's
        # existing hash-verify-before-use pattern; full body follows the same
        # shape as _run_user_dataset (lines 916-1000+ of this file today),
        # substituting fc.dataset_content_id/label_mapping/min_group_n for
        # contract.user_dataset_id/target_column etc. Reuse compute_fairness_bundle/
        # evaluate_multiclass_fairness unchanged — only row/label loading differs.
        ...
```

Flesh out `_run_v2`'s body by directly adapting `_run_user_dataset`'s existing logic (same file, lines ~916 onward) — same hash-verify-before-use gate (reuse `hashes_equal`/`format_sha256`), same `discover_group_values`/`load_rows_for_evaluation` calls from `app.datasets.user_dataset`, except: fetch the `DatasetContent` row's `storage_uri`/`content_hash` via a new small lookup (worker has DB session access — add a `DatasetContentRepository` call here), and translate `fc.label_mapping` into the same label-encoding shape `load_rows_for_evaluation` expects instead of the old alphabetical `0..k-1` sort. This substitution is mechanical once the existing `_run_user_dataset` body is in view — do not rewrite `compute_fairness_bundle`/`evaluate_multiclass_fairness`, only the data-loading front end changes.

Apply the identical `isinstance(contract, EvaluationContractV2)` branch to `backend/app/probes/robustness.py::run()`, dispatching to a new `_run_v2` that mirrors `robustness_nlp.py`'s existing `TransformersCharSwapRunner.run` sample-loading, substituting `RobustnessContractV2`'s fields the same way.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_fairness_contract_v2.py tests/test_robustness_contract_v2.py -v`
Expected: PASS.

- [ ] **Step 5: Wire `dataset_content_store` into the pipeline**

```python
# backend/app/tasks/evaluate_pipeline.py — modify run_evaluation_pipeline's run_all_probes call

    from app.storage.evidence_store import get_dataset_content_store

    outputs = run_all_probes(
        session,
        payload,
        model_metadata=model.model_metadata or {},
        evidence_store=store,
        model_revision=payload.model_revision,
        model_checksum=model.checksum,
        dataset_store=get_dataset_store(get_settings()),
        dataset_content_store=get_dataset_content_store(get_settings()),
    )
```

Add the matching `dataset_content_store: DatasetContentStore | None = None` parameter to `run_all_probes`'s signature in `runner.py`, passed through into the `ProbeContext` construction.

- [ ] **Step 6: Commit**

```bash
git add backend/app/probes/base.py backend/app/probes/runner.py backend/app/probes/fairness.py backend/app/probes/robustness.py backend/app/tasks/evaluate_pipeline.py backend/tests/test_fairness_contract_v2.py backend/tests/test_robustness_contract_v2.py
git commit -m "feat: worker/probes consume EvaluationContractV2 alongside legacy V1"
```

**Phase 4 complete when:** all tasks above pass; `POST /v1/evaluations-v2` creates a real, working evaluation that runs through the actual worker and probes end-to-end with the new contract shape, side-by-side with the still-functioning legacy path.

---

## Phase 5 — NOT_APPLICABLE + methodology_version + scoring/report changes

**Rollback/safety boundary:** `methodology_version` gating (Task 4.3) already shipped in Phase 4. This phase finishes threading it through report generation and the executive summary, and adds the frontend's NOT_APPLICABLE display. All changes are additive/conditional on `methodology_version` — legacy evaluations' report generation is provably unchanged (covered by the byte-for-byte legacy-path tests already in Task 4.3). Revert = these are pure code changes with no schema migration in this phase; a `git revert` is safe.

**What old behavior remains temporarily:** Reports for evaluations created via the *old* `POST /v1/evaluations` path continue to generate exactly as before (legacy `methodology_version`, confirmed by Task 4.3's tests). Both wizards, both evaluation-creation endpoints, both contract shapes still coexist.

**What becomes impossible after this phase:** Nothing new — still additive.

### Task 5.1: Thread `methodology_version` through `build_report_json`

**Files:**
- Modify: `backend/app/reports/builder.py` (`build_report_json` copies `evaluation.methodology_version` into the returned `ReportV1`)
- Test: `backend/tests/test_report_builder.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_report_builder.py — append

def test_report_json_records_methodology_version(db_session, finalized_evaluation_v2):
    report = build_report_json(db_session, finalized_evaluation_v2, report_version=1)
    assert report["methodology_version"] == "v2-per-dimension-2026"


def test_legacy_report_json_records_legacy_methodology_version(db_session, finalized_evaluation_legacy):
    report = build_report_json(db_session, finalized_evaluation_legacy, report_version=1)
    assert report["methodology_version"] == "pre-v1-fixed-5dim"
```

Add `finalized_evaluation_v2`/`finalized_evaluation_legacy` fixtures reusing whatever pattern `test_autonomous_report_json` already uses to get a `FINALIZED` evaluation, just varying `methodology_version` on the row before finalizing.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_report_builder.py -v`
Expected: FAIL — `KeyError: 'methodology_version'`.

- [ ] **Step 3: Implement**

```python
# backend/app/reports/builder.py — modify build_report_json, near where the ReportV1(...) is constructed

    return ReportV1(
        ...,
        methodology_version=evaluation.methodology_version,
    ).model_dump(mode="json")
```

Locate the exact `ReportV1(...)` construction call (further down in `build_report_json` than what was shown earlier in this design conversation — search the file for `return ReportV1(` or `ReportV1(\n`) and add the field there; do not construct a second `ReportV1` elsewhere.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_report_builder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reports/builder.py backend/tests/test_report_builder.py
git commit -m "feat: record methodology_version in every newly generated ReportV1"
```

### Task 5.2: NOT_APPLICABLE display in `ReportTraceabilityEntry` and frontend

**Files:**
- Modify: `frontend/src/pages/ReportPage.tsx` (render a distinct "Not configured" badge for a dimension whose `status === "NOT_APPLICABLE"`, distinct from the existing `INSUFFICIENT_EVIDENCE` styling)
- Modify: `frontend/src/pages/EvaluationDetailPage.tsx` (same distinction on the live detail view's `DimensionCard`)
- Test: `frontend/src/pages/ReportPage.test.tsx` (extend)

**Interfaces:**
- No backend schema change needed — `ReportTraceabilityEntry.status` and `ProbeEvidenceRead.status` already carry the raw `ProbeEvaluationStatus` string (`"not_applicable"`, confirmed already emitted by `_run_no_contract`/the new `_run_v2` paths); this task is purely a frontend rendering distinction.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/ReportPage.test.tsx — append

test("renders NOT_APPLICABLE dimension distinctly from INSUFFICIENT_EVIDENCE", () => {
  const report = {
    ...baseReport,
    evidence_traceability: [
      { dimension: "FAIRNESS", status: "not_applicable", ... },
      { dimension: "ROBUSTNESS", status: "insufficient_evidence", ... },
    ],
  };
  render(<ReportPage report={report} />);
  expect(screen.getByText(/not configured/i)).toBeInTheDocument();
  expect(screen.getByText(/insufficient evidence/i)).toBeInTheDocument();
});
```

Fill `...` with whatever other required fields `ReportTraceabilityEntry`-shaped test fixtures already use elsewhere in this test file (check `baseReport`'s existing shape).

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/pages/ReportPage.test.tsx`
Expected: FAIL — both statuses currently render the same generic text (or whatever today's undifferentiated rendering produces — check the current `DimensionCard`/traceability-row component first to confirm the exact starting behavior before writing this assertion).

- [ ] **Step 3: Implement**

Find wherever `ReportPage.tsx`/`EvaluationDetailPage.tsx` currently renders a dimension's `status` string (likely a small label/badge component — check for a shared `Row`/`DimensionCard` component per the codegraph results from earlier in this design conversation, which listed `DimensionCard`, `FairnessBody`, `RobustnessBody`, `ReportTraceabilityPanel` all rendering via a shared `Row` component) and add a status-label map:

```tsx
const STATUS_LABELS: Record<string, string> = {
  not_applicable: "Not configured",
  insufficient_evidence: "Insufficient evidence",
  evaluated: "Evaluated",
  failed: "Failed",
};

function statusLabel(status: string | null): string {
  return status ? STATUS_LABELS[status] ?? status : "—";
}
```

Use `statusLabel(entry.status)` wherever the raw status string is currently interpolated directly, in both `ReportPage.tsx` and `EvaluationDetailPage.tsx`'s shared `Row`/`DimensionCard` component — locate the shared component first (per the codegraph note above) and make the change there once, rather than in each page separately, since both already render through it.

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/pages/ReportPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReportPage.tsx frontend/src/pages/EvaluationDetailPage.tsx frontend/src/pages/ReportPage.test.tsx
git commit -m "feat: render NOT_APPLICABLE distinctly from INSUFFICIENT_EVIDENCE in report and detail views"
```

**Phase 5 complete when:** both tasks pass; a new-methodology evaluation with an unconfigured dimension shows "Not configured" in both the live detail view and the generated report, distinct from a genuinely-attempted-but-insufficient dimension; legacy reports are provably unaffected (Task 4.3 + 5.1 tests both cover this).

---

## Phase 6 — Cut over fully to the new path

**Rollback/safety boundary:** This is the first phase with real user-facing consequence — the old wizard stops being the default entry point and the old creation endpoint is marked deprecated (but still present and functional, not yet deleted — deletion is Phase 7). Rollback = flip the default route back; both endpoints still exist side by side until Phase 7, so this is reversible without a deploy of Phase 7's deletions.

**What old behavior remains temporarily:** `POST /v1/evaluations` (old body shape) and `/evaluations/new` (old wizard) still exist and still function, reachable directly by URL/API call, but are no longer linked from the main UI.

**What becomes impossible after this phase:** A user browsing the UI normally can no longer reach the old wizard — only the new draft-based flow is discoverable. (Direct API/URL access to the old path still works until Phase 7.)

### Task 6.1: Make the new wizard the default entry point

**Files:**
- Modify: `frontend/src/App.tsx` (swap route paths: `/evaluations/new` now renders `CreateEvaluationDraftPage`, old page moves to `/evaluations/new-legacy`)
- Modify: every place linking to "New evaluation" (`grep -rn "evaluations/new" frontend/src` first to find every link site — likely `OverviewPage.tsx`, `ModelDetailPage.tsx`, nav components — update all of them)
- Test: `frontend/src/App.test.tsx` (or wherever routing is currently tested) — extend to assert `/evaluations/new` renders the draft-based page.

- [ ] **Step 1: Write the failing test**

```tsx
test("evaluations/new renders the draft-based wizard by default", () => {
  render(<App />, { route: "/evaluations/new" });
  expect(screen.getByLabelText(/configure fairness/i)).toBeInTheDocument();
});
```

Adapt to however this codebase's existing route tests set the initial route (check an existing test in the same file for the pattern — e.g. a custom `render` wrapper with a `MemoryRouter initialEntries`).

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run` (whichever file covers routing)
Expected: FAIL — old page still renders at that path.

- [ ] **Step 3: Swap routes**

```tsx
// frontend/src/App.tsx
<Route path="/evaluations/new" element={<CreateEvaluationDraftPage />} />
<Route path="/evaluations/new-legacy" element={<CreateEvaluationPage />} />
```

Update every link found by the grep above from implicitly relying on `/evaluations/new` meaning the old page to explicitly pointing wherever intended (most should just keep pointing at `/evaluations/new`, now correctly resolving to the new page with no further change needed).

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: make the draft-based wizard the default /evaluations/new entry point"
```

### Task 6.2: Deprecate (not delete) the old backend creation endpoint

**Files:**
- Modify: `backend/app/routers/v1/evaluations.py` (mark `create_evaluation`'s OpenAPI `deprecated=True`, add a log line noting legacy-path usage for observability during the transition)
- Test: `backend/tests/test_evaluation_enqueue.py` (extend to assert the endpoint still works, just flagged)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_evaluation_enqueue.py — append

def test_legacy_create_endpoint_still_functions_but_is_deprecated(client, seeded_model):
    resp = client.post("/v1/evaluations", json={"model_id": seeded_model.id, "evaluation_mode": "AI_ASSISTED"})
    assert resp.status_code == 201  # still works — not removed yet
```

Check the OpenAPI schema directly for the `deprecated` flag rather than asserting on response body (it's a docs-metadata flag, not a runtime behavior change):

```python
def test_legacy_create_endpoint_marked_deprecated_in_openapi(client):
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/v1/evaluations"]["post"]["deprecated"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_evaluation_enqueue.py -v`
Expected: FAIL — `deprecated` key absent/False.

- [ ] **Step 3: Implement**

```python
# backend/app/routers/v1/evaluations.py — modify the existing @router.post("", ...) decorator

@router.post(
    "",
    response_model=EvaluationRead,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
    summary="[DEPRECATED — use POST /v1/evaluations-v2] Create evaluation and enqueue stub job",
    description=(
        "Deprecated: use POST /v1/evaluations-v2 with a validated draft instead. "
        "This endpoint remains functional during the migration window and is "
        "removed once the new path is fully adopted (see implementation plan "
        "Phase 7)."
    ),
    responses={404: {"model": ErrorResponse}},
)
def create_evaluation(...):
    logger.warning("legacy_evaluation_create_used model_id=%s", body.model_id)
    ...
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_evaluation_enqueue.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/v1/evaluations.py backend/tests/test_evaluation_enqueue.py
git commit -m "chore: mark legacy POST /v1/evaluations deprecated, log usage for migration observability"
```

**Phase 6 complete when:** both tasks pass; the new draft-based wizard is what every normal user reaches; the old path is observably deprecated but not yet removed, giving a safety window to confirm nothing still depends on it before Phase 7 deletes it.

---

## Phase 7 — Delete pairing/registry/proxy_lr/old contract and related dead code

**Rollback/safety boundary:** This phase is destructive — it removes code, not just adds it. Do not start this phase until Phase 6 has been running with zero legacy-path usage (check the `legacy_evaluation_create_used` log line added in Task 6.2 shows no hits over a real observation window) and until Phase 8's regression suite (next phase, but run its migration-verification portion first as a gate) confirms every existing evaluation/report still reads correctly. Rollback here is `git revert` of this phase's commits — safe as long as no new evaluations were created via the deleted endpoints in between (impossible, since they'll no longer exist).

**What old behavior remains temporarily:** Nothing — this phase removes it.

**What becomes impossible after this phase:** Creating an evaluation via `pairing_id`/`dataset_key`/`contract_kind=proxy_lr`; any code importing `app.inference.pairing`, `app.probes.robustness_compat`, or the registry portions of `app.datasets.registry`; the old `/evaluations/new-legacy` frontend route and `CreateEvaluationPage.tsx`.

### Task 7.1: Delete backend pairing/registry/proxy_lr code

**Files to delete entirely:**
- `backend/app/inference/pairing.py`
- `backend/app/probes/robustness_compat.py`
- `backend/app/services/evaluation_options.py`
- `backend/app/inference/adapters/hatexplain.py` (only reachable via the now-deleted pairing config)

**Files to modify (remove dead code, keep the rest):**
- `backend/app/datasets/registry.py` — remove `FairnessSensitiveAttribute`, `FairnessDatasetConfig`, `DatasetsConfigV1`, `load_datasets_config`, `get_dataset_spec`, `validate_probe_config_datasets`, `_cached_default_config`; **keep** nothing if nothing else in this file is used post-deletion — check for any remaining referenced symbol with `grep -rn "from app.datasets.registry import" backend/` after removing the above; if the grep is empty, delete the whole file.
- `backend/app/datasets/loader.py` — delete `load_pinned_subset`/`load_pairing_subset`/`load_fairness_subset` (registry/pairing-only, superseded by the `_run_v2` dataset-content loading path from Task 4.5); keep `normalize_row`/`DatasetLoadError` only if still referenced elsewhere (check first).
- `backend/app/inference/adapters/registry.py` — remove the `HatexplainPostTokensAdapter` entry, leaving only `PlainTextAdapter`.
- `backend/app/probes/fairness.py` — delete `_run_pairing_faithful`, `_run_legacy`, `_run_no_contract`'s old signature (keep the NOT_APPLICABLE-producing logic, just simplify since `contract` is always `None` or `EvaluationContractV2.fairness is None` now — no more `EvaluationContractV1` branch needed), `_resolve_sensitive_pairing`, `_applicability_class`, `_PROXY_LR_DATASET_KEY`, the entire V1 `kind`-dispatch block in `run()` — leaving only the `isinstance(contract, EvaluationContractV2)` branch from Task 4.5 (the `else` branch that called `_run_no_contract`/V1 logic is deleted, not just unreached).
- `backend/app/probes/robustness.py` — delete `_resolve_robustness_dataset`, `resolve_robustness_compat` import, the old V1 dispatch — leaving only the `_run_v2` path.
- `backend/app/schemas/evaluation_contract.py` — delete entirely (the old flat `EvaluationContractV1`).
- `backend/app/inference/evaluation_contract.py` — delete entirely (`build_evaluation_contract`).
- `backend/app/services/evaluation_service.py` — delete `create_evaluation` (the old method) and its `build_evaluation_contract` import.
- `backend/app/schemas/evaluations.py` — remove `contract_kind`/`pairing_id`/`dataset_key`/`user_dataset_id`/`target_column`/`group_column`/`text_column`/`included_group_values` from `EvaluationCreate` (the whole class may be deletable if `POST /v1/evaluations` itself is removed in the same pass — see Task 7.3).
- `backend/app/schemas/models.py` — delete `FairnessContractOption`, `RobustnessContractOption`, `EvaluationOptionsRead`.

**Test:**
- Delete now-obsolete test files: `backend/tests/test_pairing.py`, `test_pairing_integration.py`, `test_fairness_contract.py`, `test_fairness_multiclass.py` (only if it exclusively tests the deleted pairing path — check first, it may also cover `fairness_stats.py` math that must be preserved, in which case split rather than delete wholesale), `test_robustness_contract.py`, `test_robustness_compat.py`, `test_evaluation_options.py`, `test_evaluation_user_dataset_contract.py` (the old `user_dataset` contract path is superseded by `EvaluationContractV2`'s dataset-content path — confirm `UserDataset`/`DatasetStore` themselves are not deleted here, only their old *contract-kind* usage; the raw upload mechanism may still be referenced elsewhere — check before deleting this file wholesale).
- Keep and verify still-passing: `backend/tests/test_fairness_stats.py`, `test_fairness_probe.py` (adapt any fixture still constructing an old `EvaluationContractV1` to construct `EvaluationContractV2` instead, or delete if fully superseded by `test_fairness_contract_v2.py`), `test_robustness_probe.py`/`test_robustness_integration.py`/`test_robustness_nlp.py` similarly.

- [ ] **Step 1: Run the full backend test suite before deleting anything, to capture the current baseline**

Run: `cd backend && pytest -q`
Record the pass count.

- [ ] **Step 2: Delete files and dead code per the lists above**, one file/module at a time, running `pytest -q` after each deletion to catch breakage immediately rather than after a large batch.

- [ ] **Step 3: Fix every import error surfaced by each deletion**

Run: `cd backend && python -c "import app.main"` after each deletion batch to catch import-time breakage fast, before running the full (slower) test suite.

- [ ] **Step 4: Run full suite to confirm equal-or-greater pass count with old-path tests removed and new-path tests intact**

Run: `cd backend && pytest -q`
Expected: PASS, with the remaining test count reflecting exactly the deletions made (no unexplained drop from tests that should have been kept).

- [ ] **Step 5: Commit** (as several smaller commits, one per logical deletion group, not one giant commit — makes a future `git revert` of just one piece possible)

```bash
git add -A backend/app/inference/pairing.py backend/app/probes/robustness_compat.py backend/app/services/evaluation_options.py
git commit -m "chore: delete pairing/registry-compat/evaluation-options modules (superseded by EvaluationContractV2)"
# repeat per group: registry.py cleanup, loader.py cleanup, adapters cleanup,
# fairness.py/robustness.py V1-path deletion, old contract schema deletion,
# EvaluationCreate/models.py field cleanup
```

### Task 7.2: Delete frontend pairing/registry UI

**Files to delete entirely:**
- `frontend/src/pages/CreateEvaluationPage.tsx`
- `frontend/src/components/ContractCatalog.tsx`

**Files to modify:**
- `frontend/src/App.tsx` — remove the `/evaluations/new-legacy` route.
- `frontend/src/api/types.ts` — remove `EvaluationContractKind`, `EvaluationContractV1` (old shape), `FairnessContractOption`, `RobustnessContractOption`, `EvaluationOptionsRead`; rename `EvaluationContractV2`-derived types to drop the `V2` suffix now that there's only one shape (optional polish, not required).
- `frontend/src/lib/contract.ts` — remove `contractKindLabel`/`contractFamilyLabel` (old-kind-specific); keep `getEvaluationContract`/`shortRevision` if still used against the new contract shape, adapting their bodies to read `contract.fairness`/`contract.robustness` instead of `contract.kind`.

**Test:** delete `frontend/src/pages/CreateEvaluationPage.test.tsx` (if it exists) alongside the page; run the full frontend suite to confirm nothing else imports the deleted files.

- [ ] **Step 1: Run full frontend suite before deleting, to capture baseline**

Run: `cd frontend && npx vitest run`

- [ ] **Step 2: Delete files, fix every resulting import error**

Run: `cd frontend && npx tsc --noEmit` after each deletion to catch type errors before running the (slower) test suite.

- [ ] **Step 3: Run full suite**

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/pages/CreateEvaluationPage.tsx frontend/src/components/ContractCatalog.tsx frontend/src/App.tsx frontend/src/api/types.ts frontend/src/lib/contract.ts
git commit -m "chore: delete legacy pairing/registry wizard and contract-kind UI"
```

### Task 7.3: Delete Celery Beat from infrastructure

**Files:**
- Modify: `docker-compose.yml` and any `docker-compose.*.yml` variant (check `docker-compose.gpu.yml`/`docker-compose.cpu-only.yml` for a `beat` service definition — grep first: `grep -l "beat" docker-compose*.yml`)
- Modify: `worker/app/celery_app.py` if it references a beat schedule (confirmed earlier in this design conversation there is none — this step is a verification, not expected to find anything to remove)

- [ ] **Step 1: Confirm no beat service/schedule exists**

Run: `grep -rn "beat" docker-compose*.yml worker/app/`
Expected: no matches (already confirmed earlier in the design audit — this is a final verification before declaring the phase done, not new work).

- [ ] **Step 2: Commit** only if Step 1 actually found something to remove; otherwise this task requires no change — note in the PR description that Celery Beat was confirmed absent, not removed (nothing to remove).

**Phase 7 complete when:** every file/module listed above is deleted or cleaned, the full backend and frontend test suites pass with the expected (accounted-for) reduction in test count, and `grep -rn "pairing_id\|dataset_key\|proxy_lr\|EvaluationOptionsRead" backend/ frontend/src` returns zero matches outside of this plan document and historical migration files.

---

## Phase 8 — Full regression/migration verification

**Rollback/safety boundary:** This phase is verification-only — no new code changes expected unless a real regression is found, in which case stop and fix it as its own small commit before continuing verification. This is the final gate before considering the migration complete.

**What old behavior remains temporarily:** N/A — this phase confirms nothing old remains that shouldn't.

**What becomes impossible after this phase:** Declaring the migration "done" without evidence — this phase is what turns that into a verified claim.

### Task 8.1: Legacy data readback verification

**Files:**
- Create: `backend/tests/test_migration_legacy_readback.py`

- [ ] **Step 1: Write verification tests against real pre-migration data shapes**

```python
# backend/tests/test_migration_legacy_readback.py
"""Confirms every pre-existing Evaluation/Report created before this
migration still reads back correctly: correct methodology_version
backfill, correct legacy confidence semantics, correct null
methodology_version on legacy report reads."""

from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION


def test_pre_migration_evaluation_has_legacy_methodology_version(db_session, seeded_evaluation):
    assert seeded_evaluation.methodology_version == LEGACY_METHODOLOGY_VERSION


def test_pre_migration_evaluation_detail_read_unchanged(client, finalized_evaluation_legacy):
    resp = client.get(f"/v1/evaluations/{finalized_evaluation_legacy.id}")
    assert resp.status_code == 200
    # confidence_summary present and computed with legacy (non-excluding) semantics
    assert resp.json()["confidence_summary"] is not None


def test_pre_migration_report_read_returns_null_methodology_version(client, legacy_report_json_blob_in_minio):
    resp = client.get(f"/v1/reports/{legacy_report_json_blob_in_minio.evaluation_id}")
    assert resp.status_code == 200
    assert resp.json()["methodology_version"] is None
```

Add a `legacy_report_json_blob_in_minio` fixture that writes a hand-crafted `report.json` (matching the *old* schema, deliberately omitting `methodology_version`) directly to the fake/test MinIO store and a matching `Report` row — simulating a report generated before this migration shipped, rather than one generated by current code (which would always include the field).

- [ ] **Step 2: Run**

Run: `cd backend && pytest tests/test_migration_legacy_readback.py -v`
Expected: PASS. Any failure here is a real regression — stop and fix before proceeding, per this phase's rollback boundary above.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_migration_legacy_readback.py
git commit -m "test: verify legacy evaluations/reports read back unchanged post-migration"
```

### Task 8.2: End-to-end new-path smoke test

**Files:**
- Create: `backend/tests/test_e2e_draft_to_report.py`

- [ ] **Step 1: Write one full-lifecycle test**

```python
# backend/tests/test_e2e_draft_to_report.py
"""One evaluation, start to finish, through every new-path component built
in Phases 1-5: fetch dataset -> create draft -> validate/confirm Fairness
only (Robustness left NOT_APPLICABLE) -> create evaluation -> run worker
synchronously (test mode, no real Celery) -> finalize -> generate report ->
verify NOT_APPLICABLE Robustness excluded from confidence and correctly
labeled in the report."""

def test_full_lifecycle_fairness_only_robustness_not_applicable(
    client, seeded_model, httpserver, run_pipeline_synchronously
):
    httpserver.expect_request("/d.csv").respond_with_data(
        b"text,label,group\nhello,pos,a\nworld,neg,a\nfoo,pos,b\nbar,neg,b\n", content_type="text/csv"
    )
    content = client.post("/v1/dataset-fetches", json={"source_url": httpserver.url_for("/d.csv")}).json()

    draft = client.post("/v1/evaluation-drafts", json={"model_id": seeded_model.id}).json()
    client.put(
        f"/v1/evaluation-drafts/{draft['id']}/FAIRNESS",
        json={
            "dataset_content_id": content["id"], "text_column": "text", "target_column": "label",
            "sensitive_column": "group",
            "label_mapping": [{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
            "min_group_n": 1,
        },
    )
    client.post(f"/v1/evaluation-drafts/{draft['id']}/FAIRNESS/confirm")

    created = client.post("/v1/evaluations-v2", json={"draft_id": draft["id"], "evaluation_mode": "AI_AUTONOMOUS"}).json()
    run_pipeline_synchronously(created["id"])

    detail = client.get(f"/v1/evaluations/{created['id']}").json()
    assert detail["confidence_summary"]["by_dimension"]["ROBUSTNESS"] is None

    report = client.get(f"/v1/reports/{created['id']}").json()
    assert report["methodology_version"] == "v2-per-dimension-2026"
    robustness_entry = next(e for e in report["report_json"]["evidence_traceability"] if e["dimension"] == "ROBUSTNESS")
    assert robustness_entry["status"] == "not_applicable"
```

Add a `run_pipeline_synchronously(evaluation_id)` test fixture that calls `run_evaluation_pipeline` directly (in-process, bypassing real Celery) — check `test_evaluate_pipeline_evidence.py` for the existing pattern this codebase already uses to run the pipeline synchronously in tests, reuse it verbatim.

- [ ] **Step 2: Run**

Run: `cd backend && pytest tests/test_e2e_draft_to_report.py -v`
Expected: PASS. This is the single test that proves the entire redesign works end-to-end; any failure here means the migration is not actually complete regardless of how many smaller tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_e2e_draft_to_report.py
git commit -m "test: add end-to-end draft-to-report smoke test for the new architecture"
```

### Task 8.3: Full-suite final gate

- [ ] **Step 1: Run entire backend suite**

Run: `cd backend && pytest -q`
Expected: 100% pass, zero skips introduced by this migration.

- [ ] **Step 2: Run entire frontend suite**

Run: `cd frontend && npx vitest run`
Expected: 100% pass.

- [ ] **Step 3: Run frontend typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: zero errors.

- [ ] **Step 4: Grep-verify no dead references remain**

Run: `grep -rn "pairing_id\|dataset_key\|proxy_lr\|EvaluationOptionsRead\|CreateEvaluationPage\|ContractCatalog" backend/app frontend/src`
Expected: zero matches.

- [ ] **Step 5: Final commit tagging migration complete**

```bash
git commit --allow-empty -m "chore: V1 dataset/contract redesign migration complete — all phases verified"
```

**Phase 8 complete when:** all steps above pass with zero unexplained failures or skips. This is the definition of "the migration is done" for this plan.

---

## Self-Review

**Spec coverage:** Every Global Constraint traces to at least one task — DatasetContent/DatasetFetchEvent (Phase 1), drafts (Phase 2), wizard (Phase 3), EvaluationContractV2/worker (Phase 4), NOT_APPLICABLE/methodology_version/reports (Phase 4 Task 4.3 + Phase 5), cutover (Phase 6), deletion (Phase 7), Celery Beat removal (Phase 7 Task 7.3, confirmed already absent), verification (Phase 8).

**Placeholder scan:** No "TBD"/"handle edge cases" left in any Step — Task 4.5's `_run_v2` bodies for Fairness/Robustness are the one place given as "adapt the existing `_run_user_dataset`/`TransformersCharSwapRunner` body" rather than fully re-transcribed, because those bodies are large (80+ lines each), already exist verbatim in the current codebase, and the substitution is mechanical (swap old field names for new ones) — re-typing them here verbatim would just be copying, not planning; the instruction given is specific enough to execute directly against the real file.

**Type consistency:** `EvaluationContractV2`/`FairnessContractV2`/`RobustnessContractV2`/`LabelMappingEntry`/`ModelLabelSnapshot` names are used identically across Tasks 4.1, 4.4, 4.5, and 8.2. `DatasetContentRead`/`DimensionConfigUpdate`/`DimensionValidationRead`/`EvaluationDraftRead` are used identically across Tasks 2.4, 2.5, 3.1-3.5. `CURRENT_METHODOLOGY_VERSION`/`LEGACY_METHODOLOGY_VERSION` are defined once (Task 4.2) and referenced identically everywhere else.
