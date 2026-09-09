"""Unit tests for EvidenceStore (mocked boto3 — no MinIO required)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.storage.evidence_store import (
    DatasetStore,
    EvidenceStore,
    EvidenceStoreError,
    format_sha256,
    sanitize_filename,
)


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


# --- sanitize_filename / DatasetStore object-key hygiene (audit P1-1) -------


def test_sanitize_filename_normal_name_is_unchanged() -> None:
    assert sanitize_filename("results.csv") == "results.csv"


def test_sanitize_filename_strips_posix_path_traversal() -> None:
    assert sanitize_filename("../../etc/passwd.csv") == "passwd.csv"


def test_sanitize_filename_strips_windows_path_separators() -> None:
    assert sanitize_filename("..\\..\\windows\\win.csv") == "win.csv"
    assert sanitize_filename("C:\\Users\\evil\\data.csv") == "data.csv"


def test_sanitize_filename_collapses_repeated_dots() -> None:
    result = sanitize_filename("a..b...c.csv")
    assert ".." not in result
    assert result.endswith(".csv")


def test_sanitize_filename_rejects_pure_dot_segments() -> None:
    assert sanitize_filename("..") not in ("..", ".")
    assert sanitize_filename("...") not in ("...", "..", ".")


def test_sanitize_filename_strips_control_characters() -> None:
    result = sanitize_filename("evil\x00\x01name.csv")
    assert "\x00" not in result
    assert "\x01" not in result
    assert result.endswith(".csv")


def test_sanitize_filename_empty_name_falls_back_to_default() -> None:
    result = sanitize_filename("", default_stem="dataset")
    assert result == "dataset"
    assert result != ""


def test_sanitize_filename_only_extension_falls_back_to_default_stem() -> None:
    result = sanitize_filename(".csv", default_stem="dataset")
    assert result.startswith("dataset")


def test_sanitize_filename_unicode_name_is_normalized_deterministically() -> None:
    result = sanitize_filename("café-données.csv")
    assert result == sanitize_filename("café-données.csv")  # deterministic
    assert all(ch.isascii() for ch in result)
    assert result.endswith(".csv")


def test_sanitize_filename_never_returns_empty() -> None:
    for raw in ["", ".", "..", "...", "/", "\\", "\\..\\..\\", "   ", "\x00\x01\x02"]:
        assert sanitize_filename(raw) != ""


class _FakeDatasetBoto:
    def __init__(self) -> None:
        self.put_calls: list[dict] = []

    def put_object(self, **kwargs):  # noqa: ANN003
        self.put_calls.append(kwargs)


def test_dataset_store_object_key_stays_within_dataset_prefix() -> None:
    client = _FakeDatasetBoto()
    store = DatasetStore(client, "trustlens")
    dataset_id = uuid.uuid4()
    expected_prefix = f"datasets/{dataset_id}/"

    for malicious_name in [
        "../../../etc/passwd.csv",
        "..\\..\\secrets.csv",
        "a..b...csv",
        "evil\x00name.csv",
        "",
        "....csv",
    ]:
        store.put_dataset(
            data=b"a,b\n1,2\n",
            dataset_id=dataset_id,
            filename=malicious_name,
        )
        key = client.put_calls[-1]["Key"]
        assert key.startswith(expected_prefix)
        # Object key must resolve to a single path segment under the prefix —
        # no embedded "/" that could escape it via a MinIO virtual path.
        assert "/" not in key[len(expected_prefix) :]
        assert ".." not in key
