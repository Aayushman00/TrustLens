"""Optional SAFETY dimension on EvaluationDraft -> EvaluationContractV2.safety
(hardening Task 9): behavioural safety needs a severe-harm marker column."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest

from app.api.errors import ValidationAppError
from app.db.enums import EvaluationMode
from app.inference.model_inspection import ModelLabelSnapshot
from app.services.evaluation_draft_service import EvaluationDraftService
from app.services.evaluation_service_v2 import EvaluationServiceV2

_SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="sha-1")
_MAPPING = [
    {"dataset_value": "pos", "model_label_index": 1},
    {"dataset_value": "neg", "model_label_index": 0},
]


@pytest.fixture
def safety_content(db_session, fake_s3_client, monkeypatch) -> Any:
    from app.db.models import DatasetContent
    from app.services import evaluation_draft_service as draft_service_module
    from app.storage.evidence_store import DatasetContentStore

    csv_bytes = b"text,label,severe,bad\nhello,pos,1,x\nworld,neg,0,y\nfoo,pos,0,z\nbar,neg,0,x\n"
    store = DatasetContentStore(fake_s3_client, "test-bucket")
    storage_uri, content_hash = store.put(csv_bytes, format="csv")
    content = DatasetContent(
        id=uuid.uuid4(),
        content_hash=content_hash.removeprefix("sha256:"),
        storage_uri=storage_uri,
        byte_size=len(csv_bytes),
        format="csv",
        row_count=4,
        columns=[{"name": c, "inferred_type": "string"} for c in ("text", "label", "severe", "bad")],
    )
    db_session.add(content)
    db_session.flush()
    monkeypatch.setattr(draft_service_module, "get_dataset_content_store", lambda settings: store)
    return content


def _body(content, **over):
    return {
        "dataset_content_id": content.id,
        "text_column": "text",
        "target_column": "label",
        "severe_column": "severe",
        "label_mapping": _MAPPING,
        **over,
    }


def test_safety_dimension_flows_into_frozen_contract(db_session, seeded_model, safety_content):
    service = EvaluationDraftService(db_session)
    draft = service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=_SNAPSHOT):
        read = service.update_dimension(draft.id, "SAFETY", _body(safety_content))
    assert read.ok, read.errors
    confirmed = service.confirm_dimension(draft.id, "SAFETY")
    assert confirmed.safety_confirmed is True
    with patch("app.services.evaluation_service_v2.inspect_model_config", return_value=_SNAPSHOT):
        evaluation = EvaluationServiceV2(db_session).create_from_draft(draft.id, EvaluationMode.AI_ASSISTED)
    safety = evaluation.probe_config["evaluation_contract"]["safety"]
    assert safety["severe_column"] == "severe"
    assert safety["positive_label_index"] == 1


def test_safety_requires_severe_column(db_session, seeded_model, safety_content):
    service = EvaluationDraftService(db_session)
    draft = service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=_SNAPSHOT):
        with pytest.raises(ValidationAppError, match="severe_column"):
            service.update_dimension(draft.id, "SAFETY", _body(safety_content, severe_column=None))


def test_safety_rejects_non_binary_severe_column(db_session, seeded_model, safety_content):
    service = EvaluationDraftService(db_session)
    draft = service.create(seeded_model.id)
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=_SNAPSHOT):
        read = service.update_dimension(draft.id, "SAFETY", _body(safety_content, severe_column="bad"))
    assert read.ok is False
    assert any("severe_column" in e for e in read.errors)


def test_safety_rejects_unreachable_harmful_class(db_session, seeded_model, safety_content):
    service = EvaluationDraftService(db_session)
    draft = service.create(seeded_model.id)
    three = ModelLabelSnapshot(num_labels=3, id2label={0: "a", 1: "b", 2: "c"}, resolved_sha="sha-1")
    mapping = [{"dataset_value": "pos", "model_label_index": 2}, {"dataset_value": "neg", "model_label_index": 0}]
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=three):
        read = service.update_dimension(
            draft.id, "SAFETY", _body(safety_content, label_mapping=mapping, positive_label_index=1)
        )
    assert read.ok is False
    assert any("positive_label_index" in e for e in read.errors)
