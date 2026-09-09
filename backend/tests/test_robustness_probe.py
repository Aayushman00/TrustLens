"""RobustnessProbe unit tests — mocked runner, no torch/Hub."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.datasets.registry import get_dataset_spec
from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.robustness import RobustnessProbe
from app.probes.robustness_nlp import RobustnessRunResult
from app.schemas.evaluation_contract import EvaluationContractV1
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import EvidenceStoreError
from tests.fakes import FakeEvidenceStore

_AG_NEWS_MODEL = "textattack/bert-base-uncased-ag-news"
_AG_NEWS_REV = "fe417ad660b1657142f66353a184dc0c7e6d2e48"


def _ag_news_contract() -> EvaluationContractV1:
    """Registry contract matching the exact approved compat pin."""
    spec = get_dataset_spec("ag_news_robustness")
    return EvaluationContractV1(
        kind="registry",
        dataset_key="ag_news_robustness",
        dataset_revision=spec.revision,
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
        task_type=spec.task_type,
        modality=spec.modality,
    )


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
    evaluation_contract: EvaluationContractV1 | None = None,
    model_ref: str = "org/text-clf",
    model_revision: str | None = "a" * 40,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence = store or FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref=model_ref,
        model_metadata=metadata
        or {
            "pipeline_tag": "text-classification",
            "task": "text-classification",
            "tags": ["text-classification"],
        },
        probe_config=probe_config or ProbeConfigV1(),
        evidence_store=evidence,  # type: ignore[arg-type]
        model_revision=model_revision,
        evaluation_contract=evaluation_contract,
    )
    return ctx, evidence


def test_no_implicit_dataset_not_applicable() -> None:
    """A/B collapse here too: no contract at all -> N/A, no auto-selection."""
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
            extra={"seed": 42, "max_samples": 200},
        ),
        evaluation_contract=_ag_news_contract(),
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
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
        evaluation_contract=_ag_news_contract(),
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
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


def test_unapproved_dataset_key_is_not_applicable_no_substitution() -> None:
    """C/F: an explicit dataset_key with no compat entry at all -> N/A.

    Previously ``probe_config.datasets.robustness`` could select an arbitrary
    (even non-NLP) dataset directly; that entrypoint is removed. Since
    ``supported_robustness_compat_v1.yaml`` never lists a vision dataset, this
    also proves there is no fallback substitution — never a different dataset,
    just NOT_APPLICABLE.
    """
    contract = EvaluationContractV1(
        kind="registry",
        dataset_key="cifar10_subset",
        model_ref="org/text-clf",
        model_revision="a" * 40,
    )
    ctx, _ = _ctx(evaluation_contract=contract)
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert "no_compatible_dataset" in out.flags
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert out.metric_values["dataset"]["logical_key"] is None
    assert out.metric_values["dataset_key"] is None


def test_attack_budget_flows_into_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(
            attack_budget=0.05,
            extra={"seed": 7},
        ),
        evaluation_contract=_ag_news_contract(),
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
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
        evaluation_contract=_ag_news_contract(),
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
    )
    out = RobustnessProbe(runner=_FakeRunner(error=RuntimeError("no weights"))).run(ctx)
    assert "model_load_failed" in out.flags
    assert "attack_skipped" in out.flags
    assert out.status is ProbeEvaluationStatus.FAILED
    assert out.metric_values["probe_status"] == "FAILED"
    assert out.metric_values["clean_accuracy"] is None
    assert out.metric_values["inference_executed"] is False


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
        evaluation_contract=_ag_news_contract(),
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
    )
    out = RobustnessProbe(runner=_FakeRunner(result=insufficient)).run(ctx)
    assert out.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-ROB-LABEL-COMPAT" in out.metric_values["reliability"]["failed_gates"]
    assert out.metric_values["inference_executed"] is False


def test_robustness_dataset_load_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.datasets.loader import DatasetLoadError

    def _boom(*_a, **_k):
        raise DatasetLoadError("failed to load ag_news_robustness: boom")

    monkeypatch.setattr("app.probes.robustness.load_pinned_subset", _boom)
    ctx, _ = _ctx(
        evaluation_contract=_ag_news_contract(),
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
    )
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert out.status is ProbeEvaluationStatus.FAILED
    assert out.status is not ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "dataset_load_failed" in out.flags
    assert out.metric_values["clean_accuracy"] is None


def test_mismatched_dataset_for_pinned_model_is_not_applicable_no_substitution() -> None:
    """H: an explicit dataset_key that disagrees with this model's approved pin
    is rejected outright (N/A) rather than silently falling back to the
    model's *actual* approved dataset, or running the wrong-domain dataset
    anyway. (The wide/hard domain-mismatch statistical gate itself,
    G-ROB-DOMAIN, is unchanged and still covered directly in
    test_robustness_eval.py — this test proves it is no longer reachable via
    a mismatched contract, because compat validation rejects it earlier.)
    """
    contract = EvaluationContractV1(
        kind="registry",
        dataset_key="sst2_robustness",  # wrong dataset for this exact model pin
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
    )
    ctx, _ = _ctx(
        evaluation_contract=contract,
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
    )
    out = RobustnessProbe(runner=_FakeRunner()).run(ctx)
    assert out.status is ProbeEvaluationStatus.NOT_APPLICABLE
    assert "no_compatible_dataset" in out.flags
    assert out.metric_values["dataset_key"] is None


def test_evidence_store_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.probes.robustness.load_pinned_subset",
        lambda *_a, **_k: [{"text": "hello world", "label": 0}] * 200,
    )
    ctx, _ = _ctx(
        evaluation_contract=_ag_news_contract(),
        model_ref=_AG_NEWS_MODEL,
        model_revision=_AG_NEWS_REV,
        store=_BoomStore(),
    )
    with pytest.raises(EvidenceStoreError):
        RobustnessProbe(runner=_FakeRunner()).run(ctx)
