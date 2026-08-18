"""Unit tests for EvidenceStore (mocked boto3 — no MinIO required)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.storage.evidence_store import EvidenceStore, EvidenceStoreError, format_sha256


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def _store_with_client(client: MagicMock, bucket: str = "trustlens") -> EvidenceStore:
    return EvidenceStore(client, bucket)


def test_put_artifact_returns_hash_and_uri() -> None:
    client = MagicMock()
    store = _store_with_client(client)
    evaluation_id = uuid.uuid4()
    data = b'{"stub":true}'

    ref = store.put_artifact(
        data=data,
        content_type="application/json",
        probe_name="integrity",
        evaluation_id=evaluation_id,
    )

    assert ref.hash == format_sha256(data)
    assert ref.hash.startswith("sha256:")
    assert ref.probe_name == "integrity"
    assert ref.content_type == "application/json"
    assert ref.uri == f"s3://trustlens/evidence/{evaluation_id}/{ref.evidence_id}.json"
    client.put_object.assert_called_once()
    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "trustlens"
    assert kwargs["Key"] == f"evidence/{evaluation_id}/{ref.evidence_id}.json"
    assert kwargs["Body"] == data


def test_put_artifact_append_only_unique_ids() -> None:
    client = MagicMock()
    store = _store_with_client(client)
    evaluation_id = uuid.uuid4()
    data = b"{}"

    first = store.put_artifact(
        data=data,
        content_type="application/json",
        probe_name="integrity",
        evaluation_id=evaluation_id,
    )
    second = store.put_artifact(
        data=data,
        content_type="application/json",
        probe_name="integrity",
        evaluation_id=evaluation_id,
    )
    assert first.evidence_id != second.evidence_id
    assert first.uri != second.uri
    assert client.put_object.call_count == 2


def test_verify_artifact_passes_and_fails_on_tamper() -> None:
    client = MagicMock()
    store = _store_with_client(client)
    data = b'{"ok":true}'
    digest = format_sha256(data)
    key = "evidence/x/y.json"

    client.get_object.return_value = {"Body": _FakeBody(data)}
    assert store.verify_artifact(key=key, expected_hash=digest) is True

    client.get_object.return_value = {"Body": _FakeBody(b'{"tampered":true}')}
    assert store.verify_artifact(key=key, expected_hash=digest) is False


def test_verify_ref_roundtrip() -> None:
    client = MagicMock()
    store = _store_with_client(client)
    evaluation_id = uuid.uuid4()
    data = b'{"probe":"integrity"}'
    ref = store.put_artifact(
        data=data,
        content_type="application/json",
        probe_name="integrity",
        evaluation_id=evaluation_id,
    )
    client.get_object.return_value = {"Body": _FakeBody(data)}
    assert store.verify_ref(ref) is True

    client.get_object.return_value = {"Body": _FakeBody(b"nope")}
    assert store.verify_ref(ref) is False


def test_put_artifact_s3_failure_raises() -> None:
    client = MagicMock()
    client.put_object.side_effect = RuntimeError("boom")
    store = _store_with_client(client)
    with pytest.raises(EvidenceStoreError, match="Failed to put"):
        store.put_artifact(
            data=b"{}",
            content_type="application/json",
            probe_name="integrity",
            evaluation_id=uuid.uuid4(),
        )


def test_key_from_uri_rejects_wrong_bucket() -> None:
    store = _store_with_client(MagicMock())
    with pytest.raises(EvidenceStoreError, match="bucket mismatch"):
        store.key_from_uri("s3://other/evidence/x/y.json")
