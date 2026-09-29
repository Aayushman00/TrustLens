"""LocalObjectClient — filesystem replacement for MinIO (ADR 0014)."""

from __future__ import annotations

import pytest

from app.core.storage import BUCKET, LocalObjectClient, check_storage
from app.storage.evidence_store import DatasetContentStore, EvidenceStoreError


def test_roundtrip_and_overwrite(tmp_path) -> None:
    c = LocalObjectClient(tmp_path)
    c.put_object(Bucket=BUCKET, Key="a/b.json", Body=b"{}")
    assert c.get_object(Bucket=BUCKET, Key="a/b.json")["Body"].read() == b"{}"
    c.put_object(Bucket=BUCKET, Key="a/b.json", Body=b"x")
    assert c.get_object(Bucket=BUCKET, Key="a/b.json")["Body"].read() == b"x"
    assert not list(tmp_path.rglob(".tmp-*"))


@pytest.mark.parametrize("key", ["../x", "../../etc/passwd", "a/../../x"])
def test_rejects_traversal(tmp_path, key: str) -> None:
    with pytest.raises(ValueError):
        LocalObjectClient(tmp_path).get_object(Bucket=BUCKET, Key=key)


def test_store_over_local_client(tmp_path) -> None:
    store = DatasetContentStore(LocalObjectClient(tmp_path), BUCKET)
    uri, _ = store.put(b"text,label\n", format="csv")
    assert store.get(uri) == b"text,label\n"
    with pytest.raises(EvidenceStoreError):
        store.get(f"s3://{BUCKET}/datasets/" + "0" * 64)


def test_check_storage(tmp_path) -> None:
    assert check_storage(str(tmp_path / "new")) == "ok"
    assert check_storage(None) == "skipped"
