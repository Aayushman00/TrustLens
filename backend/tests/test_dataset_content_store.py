"""Tests for content-addressed DatasetContentStore."""

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
