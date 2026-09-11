"""FairnessProbe consumption of EvaluationContractV2 (Task 4.5)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    FairnessContractV2,
    LabelMappingEntry,
    ModelLabelSnapshot,
)
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import DatasetContentStore
from tests.fakes import FakeEvidenceStore, FakeInferenceBackend


@pytest.fixture
def fake_evidence_store() -> FakeEvidenceStore:
    return FakeEvidenceStore()


@pytest.fixture
def fake_probe_config() -> ProbeConfigV1:
    return ProbeConfigV1()


def _v2_contract(*, fairness: FairnessContractV2 | None) -> EvaluationContractV2:
    return EvaluationContractV2(
        model_ref="org/model",
        model_revision="a" * 40,
        resolved_model_sha="a" * 40,
        model_label_snapshot=ModelLabelSnapshot(num_labels=2, id2label={0: "NEG", 1: "POS"}),
        fairness=fairness,
        robustness=None,
    )


def _ctx(
    *,
    probe_config: ProbeConfigV1,
    evidence_store: FakeEvidenceStore,
    evaluation_contract: EvaluationContractV2,
    dataset_content_store: DatasetContentStore | None = None,
    session: Any = None,
) -> ProbeContext:
    return ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_config=probe_config,
        evidence_store=evidence_store,  # type: ignore[arg-type]
        evaluation_contract=evaluation_contract,
        dataset_content_store=dataset_content_store,
        session=session,
    )


def test_fairness_none_contract_is_not_applicable(
    fake_evidence_store: FakeEvidenceStore, fake_probe_config: ProbeConfigV1
) -> None:
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(fairness=None),
    )
    output = FairnessProbe().run(ctx)
    assert output.status == ProbeEvaluationStatus.NOT_APPLICABLE
    assert output.dimension == FriesDimension.FAIRNESS


def test_fairness_v2_positive_label_index_changes_equalized_odds_difference(
    fake_evidence_store: FakeEvidenceStore,
    fake_probe_config: ProbeConfigV1,
    db_session: Any,
) -> None:
    """End-to-end wiring proof: positive_label_index flows from
    FairnessContractV2 through the worker's actual computation and changes
    the real equalized_odds_difference -- not just at the pure-function
    level, through the whole contract -> probe path."""
    from app.db.models import DatasetContent

    # Same non-degenerate confusion pattern proven at the pure-function level
    # (test_fairness_stats.py's _ASYMMETRIC_* fixtures) to actually diverge
    # under a positive_label_index swap -- a naive alternating/constant
    # pattern turns out to be symmetric under relabeling and proves nothing.
    y_true = [1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 1, 0]
    y_pred = [0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 0]
    sensitive = ["a", "a", "a", "a", "a", "a", "b", "b", "a", "a", "a", "a", "a", "a", "a", "b", "b", "a", "a", "b"]
    rows = ["text,label,group"]
    predictions: list[int] = list(y_pred)
    for i, (label_val, group) in enumerate(zip(y_true, sensitive)):
        rows.append(f"t{i},{'pos' if label_val == 1 else 'neg'},{group}")
    csv_bytes = ("\n".join(rows) + "\n").encode("utf-8")
    store, content = _binary_csv_and_content(db_session, csv_bytes, row_count=len(y_true))

    def _run(positive_label_index: int) -> dict:
        fc = FairnessContractV2(
            dataset_content_id=content.id,
            text_column="text",
            target_column="label",
            sensitive_column="group",
            label_mapping=[
                LabelMappingEntry(dataset_value="pos", model_label_index=1),
                LabelMappingEntry(dataset_value="neg", model_label_index=0),
            ],
            min_group_n=2,
            positive_label_index=positive_label_index,
        )
        ctx = _ctx(
            probe_config=fake_probe_config,
            evidence_store=FakeEvidenceStore(),
            evaluation_contract=_v2_contract(fairness=fc),
            dataset_content_store=store,
            session=db_session,
        )
        backend = FakeInferenceBackend(predictions=list(predictions), num_labels=2)
        output = FairnessProbe(inference=backend).run(ctx)
        assert output.status == ProbeEvaluationStatus.EVALUATED, output.status_reason
        return output.metric_values

    metrics_index_1 = _run(1)
    metrics_index_0 = _run(0)

    assert metrics_index_1["positive_label_index"] == 1
    assert metrics_index_0["positive_label_index"] == 0
    assert metrics_index_1["equalized_odds_difference"] != metrics_index_0["equalized_odds_difference"]


def test_fairness_v2_positive_label_index_unreachable_produces_degenerate_result_corrected_index_does_not(
    fake_probe_config: ProbeConfigV1,
    db_session: Any,
) -> None:
    """Full-run reproduction of this session's found bug: a 3-class model
    (negative/neutral/positive) where label_mapping only ever produces
    indices 0 and 2 -- index 1 ("neutral") never occurs in ground truth.
    With positive_label_index=1 (the old silent default), tp is always 0 by
    construction (ground truth can never equal 1), so TPR/F1 are 0 for every
    group regardless of how good the model is -- a numerically well-formed
    but meaningless EVALUATED result. With the corrected index (2, the one
    the mapping actually produces), the same run must be non-degenerate.

    (draft_validation.py's tightened check is what actually stops index=1
    from ever reaching this point in the real flow -- this test shows why
    that check matters, at the probe-execution layer.)
    """
    rows = ["text,label,group"]
    predictions: list[int] = []
    # group a: 3 pos, 2 neg -- all predicted correctly against the pos->2/neg->0 mapping.
    for i, label in enumerate(["pos", "pos", "pos", "neg", "neg"]):
        rows.append(f"a{i},{label},a")
        predictions.append(2 if label == "pos" else 0)
    # group b: 2 pos, 3 neg -- also all correct.
    for i, label in enumerate(["pos", "pos", "neg", "neg", "neg"]):
        rows.append(f"b{i},{label},b")
        predictions.append(2 if label == "pos" else 0)
    csv_bytes = ("\n".join(rows) + "\n").encode("utf-8")
    store, content = _binary_csv_and_content(db_session, csv_bytes, row_count=10)

    contract3 = EvaluationContractV2(
        model_ref="org/3class-model",
        model_revision="b" * 40,
        resolved_model_sha="b" * 40,
        model_label_snapshot=ModelLabelSnapshot(
            num_labels=3, id2label={0: "negative", 1: "neutral", 2: "positive"}
        ),
        fairness=FairnessContractV2(
            dataset_content_id=content.id,
            text_column="text",
            target_column="label",
            sensitive_column="group",
            label_mapping=[
                LabelMappingEntry(dataset_value="pos", model_label_index=2),
                LabelMappingEntry(dataset_value="neg", model_label_index=0),
            ],
            min_group_n=2,
            positive_label_index=1,  # unreachable -- ground truth is only ever 0 or 2
        ),
        robustness=None,
    )

    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=FakeEvidenceStore(),
        evaluation_contract=contract3,
        dataset_content_store=store,
        session=db_session,
    )
    backend = FakeInferenceBackend(predictions=list(predictions), num_labels=3)
    degenerate = FairnessProbe(inference=backend).run(ctx)
    assert degenerate.status == ProbeEvaluationStatus.EVALUATED, degenerate.status_reason
    degenerate_groups = degenerate.metric_values["groups"]
    assert all(g["tpr"] == 0.0 and g["f1"] == 0.0 for g in degenerate_groups.values())

    contract3_fixed = contract3.model_copy(deep=True)
    contract3_fixed.fairness.positive_label_index = 2  # the index the mapping actually produces

    ctx2 = _ctx(
        probe_config=fake_probe_config,
        evidence_store=FakeEvidenceStore(),
        evaluation_contract=contract3_fixed,
        dataset_content_store=store,
        session=db_session,
    )
    backend2 = FakeInferenceBackend(predictions=list(predictions), num_labels=3)
    fixed = FairnessProbe(inference=backend2).run(ctx2)
    assert fixed.status == ProbeEvaluationStatus.EVALUATED, fixed.status_reason
    fixed_groups = fixed.metric_values["groups"]
    assert any(g["tpr"] > 0.0 or g["f1"] > 0.0 for g in fixed_groups.values())


def _fairness_contract() -> FairnessContractV2:
    return FairnessContractV2(
        dataset_content_id=uuid.uuid4(),
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
        min_group_n=2,
    )


def test_fairness_v2_missing_stores_is_failed(
    fake_evidence_store: FakeEvidenceStore, fake_probe_config: ProbeConfigV1
) -> None:
    fc = _fairness_contract()
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(fairness=fc),
        dataset_content_store=None,
        session=None,
    )
    output = FairnessProbe().run(ctx)
    assert output.status == ProbeEvaluationStatus.FAILED
    assert "dataset_store_unavailable" in output.flags


class _FakeS3Client:
    """Minimal in-memory boto3-like client (mirrors tests/conftest.py's)."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **_kw: Any) -> dict:
        self.objects[(Bucket, Key)] = Body
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        data = self.objects[(Bucket, Key)]

        class _Body:
            def read(self) -> bytes:
                return data

        return {"Body": _Body()}


def test_fairness_v2_full_path_binary_evaluated(
    fake_evidence_store: FakeEvidenceStore,
    fake_probe_config: ProbeConfigV1,
    db_session: Any,
) -> None:
    """Real CSV bytes through a fake content-addressed store, real label
    mapping translation (including an unmapped-label row excluded and
    counted), and a real compute_fairness_bundle computation."""
    from app.db.models import DatasetContent
    from app.db.repositories.dataset_content import DatasetContentRepository

    csv_bytes = (
        b"text,label,group\n"
        b"hello,pos,a\n"
        b"world,neg,a\n"
        b"foo,pos,b\n"
        b"bar,neg,b\n"
        b"baz,pos,b\n"
        b"qux,maybe,a\n"  # unmapped label value -> excluded
    )
    store = DatasetContentStore(_FakeS3Client(), "test-bucket")
    storage_uri, content_hash = store.put(csv_bytes, format="csv")

    content = DatasetContent(
        id=uuid.uuid4(),
        content_hash=content_hash.removeprefix("sha256:"),
        storage_uri=storage_uri,
        byte_size=len(csv_bytes),
        format="csv",
        row_count=6,
        columns=[
            {"name": "text", "inferred_type": "string"},
            {"name": "label", "inferred_type": "string"},
            {"name": "group", "inferred_type": "string"},
        ],
    )
    db_session.add(content)
    db_session.flush()

    fc = FairnessContractV2(
        dataset_content_id=content.id,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
        min_group_n=2,
    )
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(fairness=fc),
        dataset_content_store=store,
        session=db_session,
    )
    # Rows in file order after excluding the unmapped-label row:
    # hello/pos/a, world/neg/a, foo/pos/b, bar/neg/b, baz/pos/b
    # -> y_true = [1, 0, 1, 0, 1]; perfect predictions.
    backend = FakeInferenceBackend(predictions=[1, 0, 1, 0, 1], num_labels=2)
    probe = FairnessProbe(inference=backend)

    output = probe.run(ctx)

    assert output.status == ProbeEvaluationStatus.EVALUATED, output.status_reason
    assert output.dimension == FriesDimension.FAIRNESS
    metrics = output.metric_values
    assert metrics["evaluation_class"] == "user_dataset_v2"
    assert metrics["dataset_content_id"] == str(content.id)
    assert metrics["label_encoding"] == {"pos": 1, "neg": 0}
    assert metrics["excluded_rows"]["unmapped_label"] == 1
    assert metrics["n_evaluated"] == 5
    # Perfect predictions (y_pred == y_true) drive equalized_odds_difference
    # to 0, but demographic_parity_difference still reflects the groups'
    # differing positive-label base rates: group a positive rate 1/2,
    # group b positive rate 2/3.
    assert metrics["demographic_parity_difference"] == pytest.approx(1 / 6, abs=1e-6)
    assert metrics["equalized_odds_difference"] == 0.0
    assert DatasetContentRepository(db_session).get_by_id(content.id) is not None
    assert len(fake_evidence_store.puts) == 1


def _binary_csv_and_content(db_session: Any, csv_bytes: bytes, row_count: int) -> Any:
    from app.db.models import DatasetContent

    store = DatasetContentStore(_FakeS3Client(), "test-bucket")
    storage_uri, content_hash = store.put(csv_bytes, format="csv")
    content = DatasetContent(
        id=uuid.uuid4(),
        content_hash=content_hash.removeprefix("sha256:"),
        storage_uri=storage_uri,
        byte_size=len(csv_bytes),
        format="csv",
        row_count=row_count,
        columns=[
            {"name": "text", "inferred_type": "string"},
            {"name": "label", "inferred_type": "string"},
            {"name": "group", "inferred_type": "string"},
        ],
    )
    db_session.add(content)
    db_session.flush()
    return store, content


def test_fairness_v2_binary_wide_dp_ci_gates_scoring(
    fake_evidence_store: FakeEvidenceStore,
    fake_probe_config: ProbeConfigV1,
    db_session: Any,
) -> None:
    """A tiny sample (5 rows) produces a wide bootstrap CI on
    demographic_parity_difference -- G-FAIR-CI-WIDE must block scoring:
    status stays EVALUATED (not FAILED) but status_reason names the gate
    and the wide_ci_dp flag is set."""
    csv_bytes = (
        b"text,label,group\n"
        b"hello,pos,a\n"
        b"world,neg,a\n"
        b"foo,pos,b\n"
        b"bar,neg,b\n"
        b"baz,pos,b\n"
    )
    store, content = _binary_csv_and_content(db_session, csv_bytes, row_count=5)
    fc = FairnessContractV2(
        dataset_content_id=content.id,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
        min_group_n=2,
    )
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(fairness=fc),
        dataset_content_store=store,
        session=db_session,
    )
    backend = FakeInferenceBackend(predictions=[1, 0, 1, 0, 1], num_labels=2)
    output = FairnessProbe(inference=backend).run(ctx)

    assert output.status == ProbeEvaluationStatus.EVALUATED
    assert "wide_ci_dp" in output.flags
    assert output.status_reason is not None
    assert "G-FAIR-CI-WIDE" in output.status_reason
    assert output.metric_values["dp_ci"]["method"] == "bootstrap_percentile"


def test_fairness_v2_binary_tight_dp_ci_scores_normally(
    fake_evidence_store: FakeEvidenceStore,
    fake_probe_config: ProbeConfigV1,
    db_session: Any,
) -> None:
    """A large, cleanly-separated sample keeps DP's bootstrap CI narrow --
    must NOT trip the gate, must go through the normal confidence path."""
    rows = ["text,label,group"]
    predictions: list[int] = []
    # group a: 200 rows, 90% positive (label=1, predicted correctly).
    for i in range(200):
        label = "pos" if i < 180 else "neg"
        rows.append(f"t{i}a,{label},a")
        predictions.append(1 if i < 180 else 0)
    # group b: 200 rows, 10% positive -- stable, well-separated DP gap.
    for i in range(200):
        label = "pos" if i < 20 else "neg"
        rows.append(f"t{i}b,{label},b")
        predictions.append(1 if i < 20 else 0)
    csv_bytes = ("\n".join(rows) + "\n").encode("utf-8")
    store, content = _binary_csv_and_content(db_session, csv_bytes, row_count=400)
    fc = FairnessContractV2(
        dataset_content_id=content.id,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
        min_group_n=50,
    )
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(fairness=fc),
        dataset_content_store=store,
        session=db_session,
    )
    backend = FakeInferenceBackend(predictions=predictions, num_labels=2)
    output = FairnessProbe(inference=backend).run(ctx)

    assert output.status == ProbeEvaluationStatus.EVALUATED
    assert "wide_ci_dp" not in output.flags
    assert output.status_reason is None
    dp_ci = output.metric_values["dp_ci"]
    assert dp_ci["ci_upper"] - dp_ci["ci_lower"] <= 0.15


def test_fairness_v2_binary_evidence_artifact_contains_ci_fields(
    fake_evidence_store: FakeEvidenceStore,
    fake_probe_config: ProbeConfigV1,
    db_session: Any,
) -> None:
    """The permanent evidence-store artifact (not just the transient
    metric_values) must carry the new dp_ci/eo_ci/f1_ci fields -- it's the
    audit record (ADR 0004), not just a report-time convenience."""
    import json

    csv_bytes = (
        b"text,label,group\n"
        b"hello,pos,a\n"
        b"world,neg,a\n"
        b"foo,pos,b\n"
        b"bar,neg,b\n"
        b"baz,pos,b\n"
    )
    store, content = _binary_csv_and_content(db_session, csv_bytes, row_count=5)
    fc = FairnessContractV2(
        dataset_content_id=content.id,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
        min_group_n=2,
    )
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(fairness=fc),
        dataset_content_store=store,
        session=db_session,
    )
    backend = FakeInferenceBackend(predictions=[1, 0, 1, 0, 1], num_labels=2)
    FairnessProbe(inference=backend).run(ctx)

    assert len(fake_evidence_store.puts) == 1
    stored_bytes = next(iter(fake_evidence_store.objects.values()))
    artifact = json.loads(stored_bytes)
    assert "dp_ci" in artifact["results"]
    assert "eo_ci" in artifact["results"]
    assert "f1_ci" in artifact["results"]
    assert artifact["results"]["dp_ci"]["method"] == "bootstrap_percentile"


def test_fairness_v2_worker_hard_fails_on_label_snapshot_mismatch(
    fake_evidence_store: FakeEvidenceStore,
    fake_probe_config: ProbeConfigV1,
    db_session: Any,
) -> None:
    """Global Constraint: worker re-loads the full model and hard-fails on
    any num_labels/id2label mismatch against the frozen model_label_snapshot
    — even though intake validated the snapshot, the worker must not trust
    it blindly at execution time."""
    from app.db.models import DatasetContent

    csv_bytes = b"text,label,group\nhello,pos,a\nworld,neg,a\nfoo,pos,b\nbar,neg,b\n"
    store = DatasetContentStore(_FakeS3Client(), "test-bucket")
    storage_uri, content_hash = store.put(csv_bytes, format="csv")

    content = DatasetContent(
        id=uuid.uuid4(),
        content_hash=content_hash.removeprefix("sha256:"),
        storage_uri=storage_uri,
        byte_size=len(csv_bytes),
        format="csv",
        row_count=4,
        columns=[
            {"name": "text", "inferred_type": "string"},
            {"name": "label", "inferred_type": "string"},
            {"name": "group", "inferred_type": "string"},
        ],
    )
    db_session.add(content)
    db_session.flush()

    fc = FairnessContractV2(
        dataset_content_id=content.id,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
        min_group_n=2,
    )
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        # _v2_contract() freezes model_label_snapshot at num_labels=2, but the
        # worker's freshly-loaded model reports num_labels=3 below — a drift
        # that must hard-fail, not silently score with wrong label semantics.
        evaluation_contract=_v2_contract(fairness=fc),
        dataset_content_store=store,
        session=db_session,
    )
    backend = FakeInferenceBackend(predictions=[1, 0, 1, 0], num_labels=3)
    probe = FairnessProbe(inference=backend)

    output = probe.run(ctx)

    assert output.status == ProbeEvaluationStatus.FAILED
    assert "num_labels" in (output.status_reason or "")
