"""Optional MinIO / S3 client init stub (no artifact I/O in Phase 2)."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config

_BOTO_CONFIG = Config(
    connect_timeout=2,
    read_timeout=2,
    retries={"max_attempts": 1},
)


def get_s3_client(
    *,
    endpoint: str | None,
    access_key: str | None,
    secret_key: str | None,
    region: str = "us-east-1",
) -> BaseClient | None:
    """Build a boto3 S3 client when endpoint + credentials are configured."""
    if not endpoint or not access_key or not secret_key:
        return None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=_BOTO_CONFIG,
    )


def check_s3(
    *,
    endpoint: str | None,
    access_key: str | None,
    secret_key: str | None,
    bucket: str,
    region: str = "us-east-1",
) -> str:
    """Return 'ok', 'error', or 'skipped'. Non-critical for API /health."""
    client = get_s3_client(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
    )
    if client is None:
        return "skipped"
    try:
        client.head_bucket(Bucket=bucket)
        return "ok"
    except Exception:
        # head_bucket can fail if bucket not yet created; try list as soft check
        try:
            client.list_buckets()  # type: ignore[attr-defined]
            return "ok"
        except Exception:
            return "error"


def s3_settings_summary(
    *,
    endpoint: str | None,
    bucket: str,
) -> dict[str, Any]:
    return {"endpoint": endpoint, "bucket": bucket}
