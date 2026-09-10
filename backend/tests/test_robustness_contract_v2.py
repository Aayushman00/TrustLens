"""RobustnessProbe consumption of EvaluationContractV2 (Task 4.5)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.robustness import RobustnessProbe
from app.probes.robustness_nlp import RobustnessRunResult
from app.schemas.evaluation_contract_v2 import (
    EvaluationContractV2,
    LabelMappingEntry,
    ModelLabelSnapshot,
    RobustnessContractV2,
)
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import DatasetContentStore
from tests.fakes import FakeEvidenceStore


@pytest.fixture
def fake_evidence_store() -> FakeEvidenceStore:
    return FakeEvidenceStore()


@pytest.fixture
def fake_probe_config() -> ProbeConfigV1:
    return ProbeConfigV1()


def _v2_contract(*, robustness: RobustnessContractV2 | None) -> EvaluationContractV2:
    return EvaluationContractV2(
        model_ref="org/model",
        model_revision="a" * 40,
        resolved_model_sha="a" * 40,
        model_label_snapshot=ModelLabelSnapshot(num_labels=2, id2label={0: "NEG", 1: "POS"}),
        fairness=None,
        robustness=robustness,
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


def test_robustness_none_contract_is_not_applicable(
    fake_evidence_store: FakeEvidenceStore, fake_probe_config: ProbeConfigV1
) -> None:
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(robustness=None),
    )
    output = RobustnessProbe().run(ctx)
    assert output.status == ProbeEvaluationStatus.NOT_APPLICABLE
    assert output.dimension == FriesDimension.ROBUSTNESS


def _robustness_contract() -> RobustnessContractV2:
    return RobustnessContractV2(
        dataset_content_id=uuid.uuid4(),
        text_column="text",
        target_column="label",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
    )


def test_robustness_v2_missing_stores_is_failed(
    fake_evidence_store: FakeEvidenceStore, fake_probe_config: ProbeConfigV1
) -> None:
    rc = _robustness_contract()
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(robustness=rc),
        dataset_content_store=None,
        session=None,
    )
    output = RobustnessProbe().run(ctx)
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


class _FakeRunner:
    """Records the samples handed to it and returns a deterministic result
    sized to match — exercises the real evaluate_classification_robustness
    computation (small n -> INSUFFICIENT_EVIDENCE via G-ROB-N-EVAL) without
    needing torch/Transformers."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> RobustnessRunResult:
        self.calls.append(kwargs)
        samples = kwargs["samples"]
        n = len(samples)
        aligned = []
        for i, s in enumerate(samples):
            label = int(s["label"])
            yc = label  # clean always correct
            yr = label if i % 4 else (1 - label)  # 1-in-4 flipped by the attack
            aligned.append(
                {
                    "label": label,
                    "y_hat_clean": yc,
                    "y_hat_robust": yr,
                    "text": s["text"],
                    "attacked_text": s["text"] + "!",
                }
            )
        return RobustnessRunResult(
            n_samples=n,
            n_evaluated=n,
            n_label_compatible=n,
            n_successfully_perturbed=n,
            n_perturb_failed=0,
            perturbation_coverage=1.0,
            label_compat_fraction=1.0,
            aligned_rows=aligned,
        )


def test_robustness_v2_full_path_insufficient_evidence(
    fake_evidence_store: FakeEvidenceStore,
    fake_probe_config: ProbeConfigV1,
    db_session: Any,
) -> None:
    """Real CSV bytes through a fake content-addressed store, real label
    mapping translation (missing-text, missing-target, and unmapped-label
    rows all excluded and counted), and a real
    evaluate_classification_robustness computation via a fake runner."""
    from app.db.models import DatasetContent

    csv_bytes = (
        b"text,label\n"
        b"good film,pos\n"
        b"bad film,neg\n"
        b"okay film,pos\n"
        b"terrible film,neg\n"
        b"nice film,pos\n"
        b"awful film,neg\n"
        b"decent film,pos\n"
        b"horrible film,neg\n"
        b",pos\n"  # missing text -> excluded
        b"unknown film,maybe\n"  # unmapped label -> excluded
    )
    store = DatasetContentStore(_FakeS3Client(), "test-bucket")
    storage_uri, content_hash = store.put(csv_bytes, format="csv")

    content = DatasetContent(
        id=uuid.uuid4(),
        content_hash=content_hash.removeprefix("sha256:"),
        storage_uri=storage_uri,
        byte_size=len(csv_bytes),
        format="csv",
        row_count=10,
        columns=[
            {"name": "text", "inferred_type": "string"},
            {"name": "label", "inferred_type": "string"},
        ],
    )
    db_session.add(content)
    db_session.flush()

    rc = RobustnessContractV2(
        dataset_content_id=content.id,
        text_column="text",
        target_column="label",
        label_mapping=[
            LabelMappingEntry(dataset_value="pos", model_label_index=1),
            LabelMappingEntry(dataset_value="neg", model_label_index=0),
        ],
    )
    ctx = _ctx(
        probe_config=fake_probe_config,
        evidence_store=fake_evidence_store,
        evaluation_contract=_v2_contract(robustness=rc),
        dataset_content_store=store,
        session=db_session,
    )
    runner = _FakeRunner()
    probe = RobustnessProbe(runner=runner)

    output = probe.run(ctx)

    assert output.dimension == FriesDimension.ROBUSTNESS
    metrics = output.metric_values
    assert metrics["evaluation_class"] == "user_dataset_v2"
    assert metrics["dataset_content_id"] == str(content.id)
    assert metrics["label_encoding"] == {"pos": 1, "neg": 0}
    assert metrics["excluded_rows"]["missing_text"] == 1
    assert metrics["excluded_rows"]["unmapped_label"] == 1
    assert metrics["n_evaluated"] == 8
    # Below MIN_EVALUATED (100) -> a real, gated INSUFFICIENT_EVIDENCE result,
    # not a skip/error — evaluate_classification_robustness ran for real.
    assert output.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert len(runner.calls) == 1
    assert len(runner.calls[0]["samples"]) == 8
    assert len(fake_evidence_store.puts) == 1
    # Global Constraint: worker must pass the frozen model_label_snapshot
    # through to the runner so it can hard-fail on a mismatch at load time.
    assert runner.calls[0]["expected_label_snapshot"] == ModelLabelSnapshot(
        num_labels=2, id2label={0: "NEG", 1: "POS"}
    )
