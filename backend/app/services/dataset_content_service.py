"""Fetches a dataset URL (SSRF-safe), sniffs its CSV schema, stores it
content-addressed, and records fetch provenance.

Reuses ``sniff_columns``/``count_rows`` from ``app.datasets.user_dataset``
verbatim (format-agnostic over raw bytes) and ``fetch_dataset_url`` from
``app.datasets.url_fetch`` (SSRF-hardened) without modification.
"""

from __future__ import annotations

from app.api.errors import ValidationAppError
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
        # DatasetContentStore.put() returns a "sha256:<hex>" formatted digest
        # (shared convention with EvidenceStore), but dataset_content.content_hash
        # is a bare hex column (String(64), unique) — normalize before persisting.
        bare_content_hash = content_hash.removeprefix("sha256:")
        content = self._content_repo.upsert(
            content_hash=bare_content_hash,
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

    def store_uploaded_file(self, data: bytes, *, filename: str) -> DatasetContentRead:
        """Same ingestion/validation/storage path as :meth:`fetch_and_store`,
        for a file the caller already has bytes for (a local upload) instead
        of one fetched from a URL. Reuses sniff_columns/count_rows verbatim
        (format-agnostic over raw bytes) -- no separate validation path to
        drift from the URL-fetch one. DatasetFetchEvent.source_url is
        NOT NULL with no upload-specific column, so a local upload is
        recorded with a synthetic ``local-upload://<filename>`` marker
        rather than a schema migration.
        """
        source_marker = f"local-upload://{filename}"
        try:
            columns = sniff_columns(data)
            row_count = count_rows(data)
        except Exception as exc:
            self._event_repo.create(
                source_url=source_marker,
                http_status=None,
                content_type=None,
                resolved_content_id=None,
                error_message=f"malformed CSV: {exc}",
            )
            raise ValidationAppError(f"uploaded file is not a valid CSV: {exc}") from exc

        storage_uri, content_hash = self._store.put(data, format=_SUPPORTED_FORMAT)
        bare_content_hash = content_hash.removeprefix("sha256:")
        content = self._content_repo.upsert(
            content_hash=bare_content_hash,
            storage_uri=storage_uri,
            byte_size=len(data),
            format=_SUPPORTED_FORMAT,
            row_count=row_count,
            columns=columns,
        )
        self._event_repo.create(
            source_url=source_marker,
            http_status=None,
            content_type=None,
            resolved_content_id=content.id,
        )
        return DatasetContentRead.model_validate(content, from_attributes=True)
