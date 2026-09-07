"""RobustnessProbe unit tests — mocked runner, no torch/Hub."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.robustness import RobustnessProbe
from app.probes.robustness_nlp import RobustnessRunResult
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import EvidenceStoreError
from tests.fakes import FakeEvidenceStore


def _aligned_rows(n: int, *, clean_acc: float = 0.9, robust_acc: float = 0.6) -> list[dict]:
    clean_correct = int(round(clean_acc * n))
    robust_correct = int(round(robust_acc * n))
    rows: list[dict] = []
    for i in range(n):
        label = i % 2
        yc = label if i < clean_correct else (1 - label)
        yr = label if i < robust_correct else (1 - label)
        rows.append(
            {
                "label": label,
                "y_hat_clean": yc,
                "y_hat_robust": yr,
                "text": f"t{i}",
                "attacked_text": f"x{i}",
            }
        )
    return rows


def _full_result(
    n: int = 120,
    *,
    clean_acc: float = 0.9,
    robust_acc: float = 0.6,
) -> RobustnessRunResult:
    aligned = _aligned_rows(n, clean_acc=clean_acc, robust_acc=robust_acc)
    clean_correct = sum(1 for r in aligned if r["y_hat_clean"] == r["label"])
    robust_correct = sum(1 for r in aligned if r["y_hat_robust"] == r["label"])
    flipped = sum(
        1
        for r in aligned
        if r["y_hat_clean"] == r["label"] and r["y_hat_robust"] != r["label"]
    )
    return RobustnessRunResult(
        clean_accuracy=clean_correct / n,
        robust_accuracy=robust_correct / n,
        attack_success_rate=flipped / n,
        n_samples=200,
        n_evaluated=n,
        n_label_compatible=n,
        n_successfully_perturbed=n,
        n_perturb_failed=0,
        perturbation_coverage=1.0,
        label_compat_fraction=1.0,
        aligned_rows=aligned,
    )


class _FakeRunner:
    def __init__(self, result: RobustnessRunResult | None = None, *, error: Exception | None = None):
        self.result = result or _full_result()
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> RobustnessRunResult:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class _BoomStore(FakeEvidenceStore):
    def put_artifact(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise EvidenceStoreError("boom")


def _ctx(
    *,
    metadata: dict | None = None,
    probe_config: ProbeConfigV1 | None = None,
    store: FakeEvidenceStore | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence = store or FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/text-clf",
        model_metadata=metadata
        or {
            "pipeline_tag": "text-classification",
            "task": "text-classification",
            "tags": ["text-classification"],
        },
        probe_config=probe_config or ProbeConfigV1(),
        evidence_store=evidence,  # type: ignore[arg-type]
        model_revision="a" * 40,
    )
    return ctx, evidence


def test_no_implicit_dataset_not_applicable() -> None:
    ctx, _ = _ctx()
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert "no_compatible_dataset" in out.flags
    assert out.metric_values["clean_accuracy"] is None


def test_fake_runner_accuracies_and_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _FakeRunner()
    samples = [{"text": "hello world", "label": 0}] * 200

    def _fake_load(*_a, **_k):
        return samples

    monkeypatch.setattr("app.probes.robustness.load_pinned_subset", _fake_load)
    ctx, store = _ctx(
        probe_config=ProbeConfigV1(
            attack_budget=0.03,
            datasets={"robustness": "ag_news_robustness"},
            extra={"seed": 42, "max_samples": 200},
        )
    )
    out = RobustnessProbe(runner=runner).run(ctx)
    assert out.dimension == FriesDimension.ROBUSTNESS
    assert out.metric_values["proposed_mapping"] is False
    assert out.metric_values["clean_accuracy"] == pytest.approx(0.9, rel=1e-2)
    assert out.metric_values["robust_accuracy"] == pytest.approx(0.6, rel=1e-2)
    assert out.metric_values["attack"] == "char_swap"
    assert out.metric_values["seed"] == 42
    assert out.metric_values["epsilon"] == 0.03
    assert out.metric_values["max_changes"] == 3
    assert out.metric_values["perturbation_coverage"] == 1.0
    assert len(store.puts) == 1
    assert store.puts[0].probe_name == "robustness"
    assert runner.calls and runner.calls[0]["max_changes"] == 3
    assert runner.calls[0]["seed"] == 42
    assert out.status is ProbeEvaluationStatus.EVALUATED
    assert out.metric_values["aspect_scoring"] in {
        "scored_risk",
        "no_material_risk",
        "mapping_blocked",
    }


def test_unsupported_modality_skips() -> None:
    ctx, store = _ctx(
        probe_config=ProbeConfigV1(datasets={"robustness": "ag_news_robustness"}),
        metadata={"pipeline_tag": "fill-mask", "tags": []},
    )
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert "unsupported_modality" in out.flags
    assert "attack_skipped" in out.flags
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert out.status_reason
    assert out.metric_values["probe_status"] == "NOT_APPLICABLE"
    assert out.confidence <= 0.5
    assert out.metric_values["clean_accuracy"] is None
    assert out.metric_values["proposed_mapping"] is False
    assert len(out.evidence_refs) == 1
    assert len(store.puts) == 1


def test_vision_dataset_unsupported() -> None:
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(datasets={"robustness": "cifar10_subset"}),
    )
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert "unsupported_modality" in out.flags
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert out.metric_values["dataset"]["logical_key"] == "cifar10_subset"


def test_attack_budget_flows_into_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(
            attack_budget=0.05,
            datasets={"robustness": "ag_news_robustness"},
            extra={"seed": 7},
        )
    )
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert out.metric_values["epsilon"] == 0.05
    assert out.metric_values["max_changes"] == 5
    assert out.metric_values["seed"] == 7


def test_model_load_failure_is_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(datasets={"robustness": "ag_news_robustness"}),
    )
    out = RobustnessProbe(runner=_FakeRunner(error=RuntimeError("no weights"))).run(ctx)
    assert "model_load_failed" in out.flags
    assert "attack_skipped" in out.flags
    assert out.status is ProbeEvaluationStatus.FAILED
    assert out.metric_values["probe_status"] == "FAILED"
    assert out.metric_values["clean_accuracy"] is None


def test_zero_eligible_insufficient_not_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    insufficient = RobustnessRunResult(
        n_samples=200,
        n_evaluated=0,
        n_label_compatible=0,
        insufficient_evidence=True,
        insufficient_reason="no label-compatible samples",
    )
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(datasets={"robustness": "ag_news_robustness"}),
    )
    out = RobustnessProbe(runner=_FakeRunner(result=insufficient)).run(ctx)
    assert out.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-ROB-LABEL-COMPAT" in out.metric_values["reliability"]["failed_gates"]


def test_robustness_dataset_load_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.datasets.loader import DatasetLoadError

    def _boom(*_a, **_k):
        raise DatasetLoadError("failed to load ag_news_robustness: boom")

    monkeypatch.setattr("app.probes.robustness.load_pinned_subset", _boom)
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(datasets={"robustness": "ag_news_robustness"}),
    )
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert out.status is ProbeEvaluationStatus.FAILED
    assert out.status is not ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "dataset_load_failed" in out.flags
    assert out.metric_values["clean_accuracy"] is None


def test_domain_gate_with_compat_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(
            datasets={"robustness": "sst2_robustness"},
        ),
        metadata={
            "pipeline_tag": "text-classification",
            "tags": ["text-classification"],
        },
    )
    ctx.model_ref = "textattack/bert-base-uncased-ag-news"
    ctx.model_revision = "fe417ad660b1657142f66353a184dc0c7e6d2e48"
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert out.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-ROB-DOMAIN" in out.metric_values["reliability"]["failed_gates"]


def test_evidence_store_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(datasets={"robustness": "ag_news_robustness"}),
        store=_BoomStore(),
    )
    with pytest.raises(EvidenceStoreError):
        RobustnessProbe(runner=_FakeRunner()).run(ctx)
