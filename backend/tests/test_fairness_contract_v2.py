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
