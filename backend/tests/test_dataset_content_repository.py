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
