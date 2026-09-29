"""Local filesystem object storage (replaces MinIO/S3, ADR 0014).

Objects live at ``{storage_dir}/{bucket}/{key}``. The client keeps the tiny
``put_object`` / ``get_object`` subset of the boto3 S3 API that the stores
already call, so EvidenceStore / DatasetContentStore / ReportStore and their
in-memory test fakes are unchanged. Artifact URIs keep the ``s3://{bucket}/{key}``
shape purely as a logical ref — existing DB rows stay readable.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Any

# Logical namespace in artifact URIs (s3://trustlens/...). Not configurable:
# every persisted URI already uses it.
BUCKET = "trustlens"


class LocalObjectClient:
    """boto3-S3-shaped client backed by a directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def _path(self, bucket: str, key: str) -> Path:
        path = (self._root / bucket / key).resolve()
        # Keys come from DB-stored URIs — never let one escape the root.
        if not path.is_relative_to(self._root / bucket):
            raise ValueError(f"Object key escapes storage root: {key!r}")
        return path

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str | None = None,
        Metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        # ContentType/Metadata accepted for API parity; every reader re-derives
        # them (hash is recomputed from bytes, type from the key/DB row).
        path = self._path(Bucket, Key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: a crash never leaves a half-written artifact that
        # would later fail its hash check.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(Body)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": io.BytesIO(self._path(Bucket, Key).read_bytes())}


def get_object_client(storage_dir: str | None) -> LocalObjectClient | None:
    """Client for ``storage_dir``, or None when storage is not configured."""
    if not storage_dir:
        return None
    return LocalObjectClient(storage_dir)


def check_storage(storage_dir: str | None) -> str:
    """Return 'ok', 'error', or 'skipped'. Non-critical for API /health."""
    if not storage_dir:
        return "skipped"
    try:
        root = Path(storage_dir)
        root.mkdir(parents=True, exist_ok=True)
        return "ok" if os.access(root, os.W_OK) else "error"
    except OSError:
        return "error"

