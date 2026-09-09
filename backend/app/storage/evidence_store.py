"""Append-only evidence artifact storage (ADR 0004 / Phase 8)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.schemas.evidence import EvidenceRef

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger("trustlens.storage")

_STORE_BOTO_CONFIG = Config(
    connect_timeout=5,
    read_timeout=30,
    retries={"max_attempts": 2},
)


class EvidenceStoreError(Exception):
    """S3/MinIO I/O or configuration failure for evidence artifacts."""


class _SettingsLike(Protocol):
    s3_endpoint: str | None
    s3_access_key: str | None
    s3_secret_key: str | None
    s3_bucket: str
    s3_region: str


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def format_sha256(data: bytes) -> str:
    """Return ``sha256:<hex>`` for artifact bytes."""
    return f"sha256:{_sha256_hex(data)}"


def normalize_hash(value: str) -> str:
    """Normalize to ``sha256:<hex>`` (accepts bare hex or prefixed)."""
    value = value.strip()
    if value.startswith("sha256:"):
        return value
    return f"sha256:{value}"


def hashes_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(normalize_hash(left), normalize_hash(right))


_STEM_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")
_EXT_UNSAFE_RE = re.compile(r"[^A-Za-z0-9]+")
_MAX_SAFE_FILENAME_LEN = 200


def sanitize_filename(filename: str, *, default_stem: str = "upload") -> str:
    """Return a conservative, storage-key-safe basename for a client-supplied
    filename — never the raw ``UploadFile.filename``.

    Deterministic normalization, not path validation: takes only the final
    path component (splitting on both ``/`` and ``\\``, so neither a POSIX
    nor a Windows-style separator can smuggle a directory traversal), drops
    non-printable/control characters, and collapses everything outside a
    conservative ``[A-Za-z0-9_-]`` charset (stem) / ``[A-Za-z0-9]`` charset
    (extension) to underscores. Because the stem charset excludes ``.``
    entirely, no sequence of dots (``..``, ``...``) can survive into the
    result. Always returns a non-empty name so the resulting object key can
    never collapse to a bare directory prefix.
    """
    candidate = filename.replace("\\", "/").rsplit("/", 1)[-1]
    candidate = "".join(ch for ch in candidate if ch.isprintable()).strip()

    stem, dot, ext = candidate.rpartition(".")
    if not dot:
        stem, ext = candidate, ""

    stem = _STEM_UNSAFE_RE.sub("_", stem).strip("_-")
    ext = _EXT_UNSAFE_RE.sub("", ext).lower()[:16]

    if not stem:
        stem = default_stem

    safe = f"{stem}.{ext}" if ext else stem
    return safe[:_MAX_SAFE_FILENAME_LEN]


class EvidenceStore:
    """Probe-agnostic MinIO/S3 evidence writer — append-only, metrics JSON only."""

    def __init__(self, client: BaseClient, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    def _object_key(
        self,
        *,
        evaluation_id: uuid.UUID,
        evidence_id: str,
        content_type: str,
    ) -> str:
        ext = ".json" if "json" in content_type.lower() else ".bin"
        return f"evidence/{evaluation_id}/{evidence_id}{ext}"

    def put_artifact(
        self,
        *,
        data: bytes,
        content_type: str,
        probe_name: str,
        evaluation_id: uuid.UUID,
        metadata: dict[str, str] | None = None,
    ) -> EvidenceRef:
        """Store bytes under a unique key; never overwrite existing objects."""
        evidence_id = str(uuid.uuid4())
        digest = format_sha256(data)
        key = self._object_key(
            evaluation_id=evaluation_id,
            evidence_id=evidence_id,
            content_type=content_type,
        )
        uri = f"s3://{self._bucket}/{key}"
        object_meta: dict[str, str] = {
            "evidence_id": evidence_id,
            "probe_name": probe_name,
            "sha256": digest.removeprefix("sha256:"),
            "evaluation_id": str(evaluation_id),
        }
        if metadata:
            object_meta.update({k: str(v) for k, v in metadata.items()})

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata=object_meta,
            )
        except Exception as exc:
            raise EvidenceStoreError(
                f"Failed to put evidence artifact key={key}: {exc}"
            ) from exc

        created_at = datetime.now(UTC)
        logger.info(
            "evidence_put evidence_id=%s key=%s bytes=%s probe=%s",
            evidence_id,
            key,
            len(data),
            probe_name,
        )
        return EvidenceRef(
            evidence_id=evidence_id,
            uri=uri,
            hash=digest,
            content_type=content_type,
            probe_name=probe_name,
            created_at=created_at,
        )

    def get_artifact(self, *, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"].read()
            return bytes(body)
        except Exception as exc:
            raise EvidenceStoreError(
                f"Failed to get evidence artifact key={key}: {exc}"
            ) from exc

    def verify_artifact(self, *, key: str, expected_hash: str) -> bool:
        data = self.get_artifact(key=key)
        return hashes_equal(format_sha256(data), expected_hash)

    def key_from_uri(self, uri: str) -> str:
        """Parse ``s3://{bucket}/{key}`` for this store's bucket."""
        parsed = urlparse(uri)
        if parsed.scheme != "s3":
            raise EvidenceStoreError(f"Unsupported evidence URI scheme: {uri}")
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if bucket != self._bucket:
            raise EvidenceStoreError(
                f"Evidence URI bucket mismatch: expected={self._bucket} got={bucket}"
            )
        if not key:
            raise EvidenceStoreError(f"Evidence URI missing object key: {uri}")
        return key

    def verify_ref(self, ref: EvidenceRef) -> bool:
        key = self.key_from_uri(ref.uri)
        return self.verify_artifact(key=key, expected_hash=ref.hash)


def get_evidence_store(settings: Settings | _SettingsLike) -> EvidenceStore | None:
    """Build an EvidenceStore from settings, or None if S3 is not configured."""
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
    return EvidenceStore(client, settings.s3_bucket)


class DatasetStore:
    """User-uploaded local dataset bytes — same MinIO/S3 bucket as evidence,
    a distinct ``datasets/`` key prefix. Local-first: this is the MinIO
    instance already running in the local Docker Compose stack, not a
    hosted/cloud service.
    """

    def __init__(self, client: BaseClient, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    def _object_key(self, *, owner_id: int, dataset_id: uuid.UUID, filename: str) -> str:
        safe_filename = sanitize_filename(filename, default_stem="dataset")
        return f"datasets/{owner_id}/{dataset_id}/{safe_filename}"

    def put_dataset(
        self,
        *,
        data: bytes,
        owner_id: int,
        dataset_id: uuid.UUID,
        filename: str,
        content_type: str = "text/csv",
    ) -> tuple[str, str]:
        """Store the raw uploaded bytes; return ``(storage_uri, content_hash)``.

        ``content_hash`` is ``sha256:<hex>`` of the raw bytes exactly as
        uploaded — computed before any parsing, so it never depends on
        encoding/parsing behavior.
        """
        key = self._object_key(owner_id=owner_id, dataset_id=dataset_id, filename=filename)
        digest = format_sha256(data)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={
                    "owner_id": str(owner_id),
                    "dataset_id": str(dataset_id),
                    "sha256": digest.removeprefix("sha256:"),
                },
            )
        except Exception as exc:
            raise EvidenceStoreError(
                f"Failed to put dataset artifact key={key}: {exc}"
            ) from exc
        logger.info(
            "dataset_put dataset_id=%s owner_id=%s key=%s bytes=%s",
            dataset_id,
            owner_id,
            key,
            len(data),
        )
        return f"s3://{self._bucket}/{key}", digest

    def get_dataset(self, *, storage_uri: str) -> bytes:
        parsed = urlparse(storage_uri)
        if parsed.scheme != "s3" or parsed.netloc != self._bucket:
            raise EvidenceStoreError(f"Unsupported/mismatched dataset URI: {storage_uri}")
        key = parsed.path.lstrip("/")
        if not key:
            raise EvidenceStoreError(f"Dataset URI missing object key: {storage_uri}")
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return bytes(response["Body"].read())
        except Exception as exc:
            raise EvidenceStoreError(
                f"Failed to get dataset artifact key={key}: {exc}"
            ) from exc

    def delete_dataset(self, *, storage_uri: str) -> None:
        parsed = urlparse(storage_uri)
        if parsed.scheme != "s3" or parsed.netloc != self._bucket:
            raise EvidenceStoreError(f"Unsupported/mismatched dataset URI: {storage_uri}")
        key = parsed.path.lstrip("/")
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise EvidenceStoreError(
                f"Failed to delete dataset artifact key={key}: {exc}"
            ) from exc


def get_dataset_store(settings: Settings | _SettingsLike) -> DatasetStore | None:
    """Build a DatasetStore from settings, or None if S3/MinIO is not configured."""
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
    return DatasetStore(client, settings.s3_bucket)
