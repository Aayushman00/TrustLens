"""SafetyProbe behavioural branch (hardening Task 9): runs the imported model on
a severe-marked dataset; separate from the card-disclosure checklist."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.enums import ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.safety import SafetyProbe
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    LabelMappingEntry,
    ModelLabelSnapshot,
    SafetyContractV2,
)
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import DatasetContentStore
from tests.fakes import FakeEvidenceStore, FakeInferenceBackend


def _ctx(db_session: Any, fake_s3_client: Any, rows: list[tuple[str, str, str]]) -> ProbeContext:
    from app.db.models import DatasetContent

    csv_bytes = ("text,label,severe\n" + "".join(f"{t},{lbl},{s}\n" for t, lbl, s in rows)).encode()
    store = DatasetContentStore(fake_s3_client, "test-bucket")
    storage_uri, content_hash = store.put(csv_bytes, format="csv")
    content = DatasetContent(
        id=uuid.uuid4(),
        content_hash=content_hash.removeprefix("sha256:"),
        storage_uri=storage_uri,
        byte_size=len(csv_bytes),
        format="csv",
        row_count=len(rows),
        columns=[{"name": c, "inferred_type": "string"} for c in ("text", "label", "severe")],
    )
    db_session.add(content)
    db_session.flush()
    contract = EvaluationContractV2(
        model_ref="org/model",
        model_revision="a" * 40,
        resolved_model_sha="a" * 40,
        model_label_snapshot=ModelLabelSnapshot(num_labels=2, id2label={0: "NEG", 1: "POS"}),
        safety=SafetyContractV2(
            dataset_content_id=content.id,
            text_column="text",
            target_column="label",
            severe_column="severe",
            label_mapping=[
                LabelMappingEntry(dataset_value="1", model_label_index=1),
                LabelMappingEntry(dataset_value="0", model_label_index=0),
            ],
        ),
    )
    return ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={"card_text": "# Card\n"},
        probe_config=ProbeConfigV1(),
        evidence_store=FakeEvidenceStore(),  # type: ignore[arg-type]
        evaluation_contract=contract,
        dataset_content_store=store,
        session=db_session,
    )


def _rows() -> list[tuple[str, str, str]]:
    return (
        [(f"s{i}", "1", "1") for i in range(40)]
        + [(f"p{i}", "1", "0") for i in range(20)]
        + [(f"n{i}", "0", "0") for i in range(40)]
    )


def test_model_missing_every_severe_row_has_severe_fnr_one(db_session, fake_s3_client) -> None:
    preds = [0] * 40 + [1] * 20 + [0] * 40
    out = SafetyProbe(inference=FakeInferenceBackend(predictions=preds)).run(
        _ctx(db_session, fake_s3_client, _rows())
    )
    behavior = out.metric_values["behavior"]
    assert behavior["status"] == ProbeEvaluationStatus.EVALUATED.value
    assert out.metric_values["severe_fnr"] == 1.0
    assert behavior["severe_n"] == 40 and behavior["benign_fpr"] == 0.0
    # Disclosure evidence is still produced alongside, never replaced.
    assert "coverage_ratio" in out.metric_values


def test_never_toxic_constant_predictor_is_measured_not_skipped(db_session, fake_s3_client) -> None:
    """Missing every harmful row IS the safety measurement (unlike fairness)."""
    out = SafetyProbe(inference=FakeInferenceBackend(predictions=[0] * 100)).run(
        _ctx(db_session, fake_s3_client, _rows())
    )
    assert out.metric_values["behavior"]["status"] == ProbeEvaluationStatus.EVALUATED.value
    assert "constant_predictor" in out.metric_values["behavior"]["flags"]
    assert out.metric_values["severe_fnr"] == 1.0


def test_always_toxic_constant_predictor_is_insufficient(db_session, fake_s3_client) -> None:
    out = SafetyProbe(inference=FakeInferenceBackend(predictions=[1] * 100)).run(
        _ctx(db_session, fake_s3_client, _rows())
    )
    assert out.metric_values["behavior"]["status"] == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value
    assert out.metric_values.get("severe_fnr") is None


def test_no_safety_contract_records_behavior_not_tested(db_session, fake_s3_client) -> None:
    ctx = _ctx(db_session, fake_s3_client, _rows())
    ctx.evaluation_contract.safety = None
    out = SafetyProbe(inference=FakeInferenceBackend()).run(ctx)
    assert out.metric_values["behavior"]["status"] == ProbeEvaluationStatus.NOT_APPLICABLE.value
    assert "severe_fnr" not in out.metric_values
