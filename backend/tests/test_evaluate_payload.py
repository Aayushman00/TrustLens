"""EvaluateModelPayload schema validation (Phase 7)."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.db.enums import EvaluationMode
from app.schemas.internal import EvaluateModelPayload


def test_payload_defaults_and_roundtrip() -> None:
    eid = uuid.uuid4()
    payload = EvaluateModelPayload(
        evaluation_id=eid,
        model_ref="distilbert-base-uncased",
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    assert payload.schema_version == "v1"
    assert payload.probe_config == {}
    dumped = payload.model_dump(mode="json")
    assert dumped["evaluation_id"] == str(eid)
    assert dumped["evaluation_mode"] == "AI_AUTONOMOUS"
    restored = EvaluateModelPayload.model_validate(dumped)
    assert restored.evaluation_id == eid


def test_payload_rejects_bad_schema_version() -> None:
    with pytest.raises(ValidationError):
        EvaluateModelPayload(
            schema_version="v2",  # type: ignore[arg-type]
            evaluation_id=uuid.uuid4(),
            model_ref="org/model",
            evaluation_mode=EvaluationMode.AI_ASSISTED,
        )


def test_payload_requires_model_ref() -> None:
    with pytest.raises(ValidationError):
        EvaluateModelPayload(
            evaluation_id=uuid.uuid4(),
            evaluation_mode=EvaluationMode.AI_ASSISTED,
        )  # type: ignore[call-arg]
