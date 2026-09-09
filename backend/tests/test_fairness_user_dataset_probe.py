"""FairnessProbe._run_user_dataset — the user-defined local Fairness path.

Verifies: exact selected model/revision loaded (no substitution), dataset
content-hash mismatch fails closed, missing-value pseudo-group is never
silently dropped, min-group-size exclusion is recorded with a reason, and
both the binary (compute_fairness_bundle) and multiclass
(evaluate_multiclass_fairness) statistics paths are reached unchanged.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.enums import ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe
from app.schemas.evaluation_contract import EvaluationContractV1
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import format_sha256
from tests.fakes import FakeDatasetStore, FakeEvidenceStore, FakeInferenceBackend

_MODEL_REF = "org/user-dataset-model"
_MODEL_REVISION = "b" * 40


def _binary_csv() -> bytes:
    rows = ["text,label,gender"]
    for i in range(40):
        label = i % 2
        gender = "Female" if i % 2 == 0 else "Male"
        rows.append(f"row{i} text,{label},{gender}")
    # a thin group that should be excluded by min_group_n
    for i in range(3):
        rows.append(f"thin{i} text,{i % 2},Non-binary")
    # explicit missing values
    rows.append("missing gender row,1,")
    rows.append("missing gender row2,0,N/A")
    return "\n".join(rows).encode("utf-8")


def _multiclass_csv() -> bytes:
    rows = ["text,label,gender"]
    labels = ["neg", "neutral", "pos"]
    for i in range(120):
        label = labels[i % 3]
        gender = "Female" if i % 2 == 0 else "Male"
        rows.append(f"row{i} text,{label},{gender}")
    return "\n".join(rows).encode("utf-8")


def _contract(*, dataset_bytes: bytes, target_column="label", group_column="gender", text_column="text"):
    digest = format_sha256(dataset_bytes)
    contract = EvaluationContractV1(
        kind="user_dataset",
        model_ref=_MODEL_REF,
        model_revision=_MODEL_REVISION,
        user_dataset_id=str(uuid.uuid4()),
        dataset_uri="s3://trustlens/datasets/1/abc/data.csv",
        dataset_content_hash=digest,
        target_column=target_column,
        group_column=group_column,
        text_column=text_column,
    )
    return contract


def _ctx(
    *,
    contract: EvaluationContractV1,
    dataset_store: FakeDatasetStore,
    probe_config: ProbeConfigV1 | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence_store = FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref=_MODEL_REF,
        model_revision=_MODEL_REVISION,
        model_metadata={},
        probe_config=probe_config or ProbeConfigV1(),
        evidence_store=evidence_store,  # type: ignore[arg-type]
        evaluation_contract=contract,
        dataset_store=dataset_store,  # type: ignore[arg-type]
    )
    return ctx, evidence_store


def _store_with(data: bytes, *, uri: str) -> FakeDatasetStore:
    store = FakeDatasetStore()
    key = uri.split(f"s3://{store.bucket}/", 1)[1]
    store.objects[key] = data
    return store


def test_binary_reaches_compute_fairness_bundle_and_loads_exact_model() -> None:
    data = _binary_csv()
    contract = _contract(dataset_bytes=data)
    store = _store_with(data, uri=contract.dataset_uri)
    ctx, _ = _ctx(contract=contract, dataset_store=store)
    fake = FakeInferenceBackend(predictions=[0, 1] * 30, num_labels=2)

    out = FairnessProbe(inference=fake).run(ctx)

    assert fake.load_calls[0]["model_ref"] == contract.model_ref
    assert fake.load_calls[0]["revision"] == contract.model_revision
    assert out.status is ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["fairness_mode"] == "user_defined_local"
    assert out.metric_values["evaluation_class"] == "user_dataset"
    assert out.metric_values["inference_executed"] is True
    assert "demographic_parity_difference" in out.metric_values
    assert "groups" in out.metric_values


def test_missing_group_pseudo_group_is_reported_not_dropped_silently() -> None:
    data = _binary_csv()
    contract = _contract(dataset_bytes=data)
    store = _store_with(data, uri=contract.dataset_uri)
    ctx, _ = _ctx(contract=contract, dataset_store=store)
    fake = FakeInferenceBackend(predictions=[0, 1] * 30, num_labels=2)

    out = FairnessProbe(inference=fake).run(ctx)

    observed = {g["value"]: g["count"] for g in out.metric_values["observed_groups"]}
    assert observed["(missing)"] == 2
    assert out.metric_values["excluded_rows"]["missing_group"] == 2


def test_thin_group_excluded_from_comparison_with_reason() -> None:
    data = _binary_csv()
    contract = _contract(dataset_bytes=data)
    store = _store_with(data, uri=contract.dataset_uri)
    probe_config = ProbeConfigV1(extra={"min_group_n": 10})
    ctx, _ = _ctx(contract=contract, dataset_store=store, probe_config=probe_config)
    fake = FakeInferenceBackend(predictions=[0, 1] * 30, num_labels=2)

    out = FairnessProbe(inference=fake).run(ctx)

    assert "Non-binary" in out.metric_values["excluded_groups"]
    assert "thin_groups_excluded" in out.flags


def test_content_hash_mismatch_fails_closed() -> None:
    data = _binary_csv()
    contract = _contract(dataset_bytes=data)
    # Corrupt the stored bytes so they no longer match the frozen contract hash.
    store = _store_with(data + b"\ncorrupted,1,X", uri=contract.dataset_uri)
    ctx, _ = _ctx(contract=contract, dataset_store=store)
    fake = FakeInferenceBackend()

    out = FairnessProbe(inference=fake).run(ctx)

    assert out.status is ProbeEvaluationStatus.FAILED
    assert "dataset_hash_mismatch" in out.flags
    assert fake.load_calls == []


def test_user_excluded_groups_are_never_evaluated() -> None:
    data = _binary_csv()
    contract = _contract(dataset_bytes=data)
    store = _store_with(data, uri=contract.dataset_uri)
    probe_config = ProbeConfigV1(extra={"included_group_values": ["Female", "Male"]})
    ctx, _ = _ctx(contract=contract, dataset_store=store, probe_config=probe_config)
    fake = FakeInferenceBackend(predictions=[0, 1] * 30, num_labels=2)

    out = FairnessProbe(inference=fake).run(ctx)

    assert "Non-binary" in out.metric_values["user_excluded_groups"]
    assert "Non-binary" not in out.metric_values["groups"]


def test_multiclass_reaches_evaluate_multiclass_fairness_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _multiclass_csv()
    contract = _contract(dataset_bytes=data)
    store = _store_with(data, uri=contract.dataset_uri)
    ctx, _ = _ctx(contract=contract, dataset_store=store)
    fake = FakeInferenceBackend(predictions=[0, 1, 2] * 40, num_labels=3)

    calls: list[dict] = []
    import app.probes.fairness as fairness_mod

    original = fairness_mod.evaluate_multiclass_fairness

    def _spy(aligned, **kwargs):
        calls.append({"n": len(aligned), **kwargs})
        return original(aligned, **kwargs)

    monkeypatch.setattr(fairness_mod, "evaluate_multiclass_fairness", _spy)

    out = FairnessProbe(inference=fake).run(ctx)

    assert len(calls) == 1
    assert calls[0]["sensitive_attribute"] == "gender"
    assert fake.load_calls[0]["model_ref"] == contract.model_ref
    assert fake.load_calls[0]["revision"] == contract.model_revision
    assert out.metric_values["evaluation_class"] == "user_dataset"


def test_no_group_column_selection_is_never_hardcoded() -> None:
    """The dataset's own column name (not "gender") is threaded through untouched."""
    csv_bytes = (
        "text,outcome,region\n"
        + "\n".join(f"sample {i},{i % 2},{'North' if i % 2 else 'South'}" for i in range(40))
    ).encode("utf-8")
    contract = _contract(
        dataset_bytes=csv_bytes,
        target_column="outcome",
        group_column="region",
        text_column="text",
    )
    store = _store_with(csv_bytes, uri=contract.dataset_uri)
    ctx, _ = _ctx(contract=contract, dataset_store=store)
    fake = FakeInferenceBackend(predictions=[0, 1] * 20, num_labels=2)

    out = FairnessProbe(inference=fake).run(ctx)

    assert out.metric_values["group_column"] == "region"
    assert set(out.metric_values["groups"]) == {"North", "South"}
