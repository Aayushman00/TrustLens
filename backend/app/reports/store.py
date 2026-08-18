"""Versioned report artifact storage in MinIO/S3 (Phase 19).

Append-only like the evidence store, but with deterministic keys:
``reports/{evaluation_id}/v{version}/report.json`` (+ ``report.pdf``).
A new report version always writes new keys — existing objects are never
overwritten.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from botocore.client import BaseClient

from app.core.s3 import get_s3_client
from app.storage.evidence_store import format_sha256

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger("trustlens.reports")


class ReportStoreError(Exception):
    """S3/MinIO I/O or configuration failure for report artifacts."""


class ReportStore:
    """Append-only writer/reader for versioned report artifacts."""

    def __init__(self, client: BaseClient, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    @staticmethod
    def object_key(evaluation_id: uuid.UUID, version: int, filename: str) -> str:
        return f"reports/{evaluation_id}/v{version}/{filename}"

    def put_report(
        self,
        *,
        evaluation_id: uuid.UUID,
        version: int,
        data: bytes,
        content_type: str,
        filename: str,
    ) -> tuple[str, str]:
        """Store bytes under the deterministic versioned key → (uri, sha256 hash)."""
        digest = format_sha256(data)
        key = self.object_key(evaluation_id, version, filename)
        uri = f"s3://{self._bucket}/{key}"
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={
                    "evaluation_id": str(evaluation_id),
                    "report_version": str(version),
                    "sha256": digest.removeprefix("sha256:"),
                },
            )
        except Exception as exc:
            raise ReportStoreError(f"Failed to put report artifact key={key}: {exc}") from exc
        logger.info(
            "report_put key=%s bytes=%s content_type=%s", key, len(data), content_type
        )
        return uri, digest

    def get_bytes(self, *, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return bytes(response["Body"].read())
        except Exception as exc:
            raise ReportStoreError(f"Failed to get report artifact key={key}: {exc}") from exc

    def key_from_uri(self, uri: str) -> str:
        """Parse ``s3://{bucket}/{key}`` for this store's bucket."""
        prefix = f"s3://{self._bucket}/"
        if not uri.startswith(prefix) or len(uri) == len(prefix):
            raise ReportStoreError(f"Unsupported report URI for bucket {self._bucket}: {uri}")
        return uri[len(prefix) :]


def get_report_store(settings: Settings) -> ReportStore | None:
    """Build a ReportStore from settings, or None if S3 is not configured."""
    client = get_s3_client(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )
    if client is None:
        return None
    return ReportStore(client, settings.s3_bucket)
