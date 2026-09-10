import uuid
from datetime import datetime, UTC

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import DatasetContent, DatasetFetchEvent


def test_dataset_content_unique_content_hash(db_session):
    row = DatasetContent(
        content_hash="a" * 64,
        storage_uri="s3://trustlens/datasets/" + "a" * 64,
        byte_size=100,
        format="csv",
        row_count=10,
        columns=[{"name": "text", "inferred_type": "string"}],
    )
    db_session.add(row)
    db_session.flush()
    assert row.id is not None

    dup = DatasetContent(
        content_hash="a" * 64,
        storage_uri="s3://trustlens/datasets/" + "a" * 64,
        byte_size=100,
        format="csv",
        row_count=10,
        columns=[],
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_dataset_fetch_event_records_provenance(db_session):
    content = DatasetContent(
        content_hash="b" * 64,
        storage_uri="s3://trustlens/datasets/" + "b" * 64,
        byte_size=50,
        format="csv",
        row_count=5,
        columns=[],
    )
    db_session.add(content)
    db_session.flush()

    event = DatasetFetchEvent(
        source_url="https://example.com/data.csv",
        requested_at=datetime.now(UTC),
        http_status=200,
        content_type="text/csv",
        resolved_content_id=content.id,
    )
    db_session.add(event)
    db_session.flush()
    assert event.resolved_content_id == content.id
