"""Multiclass fairness evaluator tests (F-FAIR-PERF, network-free)."""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.enums import ProbeEvaluationStatus
from app.probes.base import ProbeContext
from app.probes.fairness import FairnessProbe, _validate_sensitive_attribute
from app.probes.fairness_multiclass import evaluate_multiclass_fairness
from app.probes.fairness_stats import perf_trigger_fires
from app.datasets.registry import get_dataset_spec
from app.schemas.probe_config import ProbeConfigV1
from tests.fakes import FakeEvidenceStore, FakeInferenceBackend

_HATEXPLAIN_MODEL = "Hate-speech-CNERG/bert-base-uncased-hatexplain"
_HATEXPLAIN_REV = "e487c81b768c7532bf474bd5e486dedea4cf3848"
_MIN_TOTAL = 200
_MIN_GROUP = 50


def _rows(group: str, n: int, accuracy: float) -> list[dict]:
    correct = int(round(accuracy * n))
    out: list[dict] = []
    for i in range(n):
        label = i % 3
        y_hat = label if i < correct else (label + 1) % 3
        out.append({"label": label, "y_hat": y_hat, "sensitive": group, "text": "t"})
    return out


def _make_aligned(
    group_accuracies: dict[str, float],
    n_per_group: int = 60,
) -> list[dict]:
    aligned: list[dict] = []
    for group, acc in group_accuracies.items():
        aligned.extend(_rows(group, n_per_group, acc))
    return aligned


def test_clear_unfairness_triggers_f_fair_perf() -> None:
    # n_per_group=300 keeps bootstrap gap CI width below 0.15 (G-FAIR-CI-WIDE).
    aligned = _make_aligned({"A": 0.95, "B": 0.50, "C": 0.90}, n_per_group=300)
    assert len(aligned) >= _MIN_TOTAL
    result = evaluate_multiclass_fairness(
        aligned,
        seed=42,
        min_total_n=_MIN_TOTAL,
        min_group_n=_MIN_GROUP,
        sensitive_attribute="target_community",
    )
    assert result.status is ProbeEvaluationStatus.EVALUATED
    assert result.scored_risk_id == "F-FAIR-PERF"
    assert result.aspect_scoring == "scored_risk"
    assert result.risks_triggered == ["F-FAIR-PERF"]
    gap = result.metrics["subgroup_worst_group_acc_gap"]
    ci_lower = result.uncertainty["subgroup_worst_group_acc_gap"]["ci_lower"]
    assert gap > 0.02
    assert ci_lower > 0.02


def test_small_gap_no_scored_risk() -> None:
    aligned = _make_aligned({"A": 0.80, "B": 0.79, "C": 0.785}, n_per_group=100)
    result = evaluate_multiclass_fairness(
        aligned,
        seed=7,
        min_total_n=_MIN_TOTAL,
        min_group_n=_MIN_GROUP,
        sensitive_attribute="target_community",
    )
    assert result.scored_risk_id is None
    assert result.aspect_scoring == "no_material_risk"
    assert result.risks_triggered == []


def test_ci_wide_blocks_mapping_without_f_fair_perf() -> None:
    aligned = _make_aligned({"A": 0.80, "B": 0.50}, n_per_group=100)
    result = evaluate_multiclass_fairness(
        aligned,
        seed=42,
        min_total_n=_MIN_TOTAL,
        min_group_n=_MIN_GROUP,
        sensitive_attribute="target_community",
    )
    ci = result.uncertainty["subgroup_worst_group_acc_gap"]
    assert (float(ci["ci_upper"]) - float(ci["ci_lower"])) > 0.15
    assert result.status is ProbeEvaluationStatus.EVALUATED
    assert result.aspect_scoring == "mapping_blocked"
    assert "wide_ci" in result.flags
    assert "G-FAIR-CI-WIDE" in result.reliability["failed_gates"]
    assert result.reliability["gates_passed"] is False
    assert result.scored_risk_id is None
    assert result.risks_triggered == []
    assert "F-FAIR-PERF" not in result.risks_triggered


def test_missing_bootstrap_ci_is_insufficient_not_no_material_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aligned = _make_aligned({"A": 0.95, "B": 0.50, "C": 0.90}, n_per_group=300)
    measured_gap = None

    def _missing_ci(aligned_rows, *, min_group_n, B, seed):  # noqa: ARG001
        nonlocal measured_gap
        from app.probes.fairness_stats import (
            filter_compared_groups,
            group_accuracies_from_aligned,
            subgroup_worst_group_acc_gap,
        )

        compared, _ = filter_compared_groups(
            group_accuracies_from_aligned(aligned_rows), min_group_n
        )
        measured_gap = subgroup_worst_group_acc_gap(compared)
        return {
            "point": round(measured_gap, 6),
            "ci_lower": None,
            "ci_upper": None,
            "method": "bootstrap_percentile",
            "B": B,
        }

    monkeypatch.setattr(
        "app.probes.fairness_multiclass.bootstrap_gap_ci",
        _missing_ci,
    )
    result = evaluate_multiclass_fairness(
        aligned,
        seed=42,
        min_total_n=_MIN_TOTAL,
        min_group_n=_MIN_GROUP,
        sensitive_attribute="target_community",
    )
    assert result.metrics["subgroup_worst_group_acc_gap"] == pytest.approx(measured_gap)
    assert result.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert result.aspect_scoring == "not_scored"
    assert result.scored_risk_id is None
    assert result.risks_triggered == []
    assert "F-FAIR-PERF" not in result.flags
    assert result.aspect_scoring != "no_material_risk"
    assert "missing_bootstrap_ci" in result.flags
    assert result.status_reason is not None
    assert "bootstrap" in result.status_reason.lower()


def test_large_gap_low_ci_lower_does_not_trigger() -> None:
    assert perf_trigger_fires(0.10, 0.01) is False


def test_thin_group_insufficient_when_one_compared_group() -> None:
    aligned = _rows("A", 60, 0.8) + _rows("B", 30, 0.5)
    result = evaluate_multiclass_fairness(
        aligned,
        seed=1,
        min_total_n=50,
        min_group_n=_MIN_GROUP,
        sensitive_attribute="target_community",
    )
    assert result.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-FAIR-N-GROUP" in result.reliability["failed_gates"]
    assert result.scored_risk_id is None


def test_total_n_below_minimum_insufficient() -> None:
    aligned = _make_aligned({"A": 0.8, "B": 0.6}, n_per_group=75)
    assert len(aligned) == 150
    result = evaluate_multiclass_fairness(
        aligned,
        seed=1,
        min_total_n=_MIN_TOTAL,
        min_group_n=_MIN_GROUP,
        sensitive_attribute="target_community",
    )
    assert result.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-FAIR-N-TOTAL" in result.reliability["failed_gates"]
    assert result.metrics["subgroup_worst_group_acc_gap"] is None


def test_bootstrap_reproducibility() -> None:
    aligned = _make_aligned({"A": 0.95, "B": 0.50, "C": 0.90}, n_per_group=70)
    r1 = evaluate_multiclass_fairness(
        aligned, seed=99, min_total_n=_MIN_TOTAL, min_group_n=_MIN_GROUP,
        sensitive_attribute="target_community",
    )
    r2 = evaluate_multiclass_fairness(
        aligned, seed=99, min_total_n=_MIN_TOTAL, min_group_n=_MIN_GROUP,
        sensitive_attribute="target_community",
    )
    u1 = r1.uncertainty["subgroup_worst_group_acc_gap"]
    u2 = r2.uncertainty["subgroup_worst_group_acc_gap"]
    assert u1["ci_lower"] == u2["ci_lower"]
    assert u1["ci_upper"] == u2["ci_upper"]


def test_validate_sensitive_attribute_hatexplain() -> None:
    spec = get_dataset_spec("hatexplain_fairness")
    assert _validate_sensitive_attribute("target_community", spec) is None
    assert _validate_sensitive_attribute("not_declared", spec) is not None


def _ctx(
    *,
    probe_config: ProbeConfigV1 | None = None,
    store: FakeEvidenceStore | None = None,
) -> tuple[ProbeContext, FakeEvidenceStore]:
    evidence = store or FakeEvidenceStore()
    ctx = ProbeContext(
        evaluation_id=uuid.uuid4(),
        model_ref=_HATEXPLAIN_MODEL,
        model_revision=_HATEXPLAIN_REV,
        model_metadata={"pipeline_tag": "text-classification"},
        probe_config=probe_config or ProbeConfigV1(datasets={"fairness": "hatexplain_fairness"}),
        evidence_store=evidence,  # type: ignore[arg-type]
    )
    return ctx, evidence


def test_probe_evidence_has_no_osd(monkeypatch: pytest.MonkeyPatch) -> None:
    aligned = _make_aligned({"A": 0.95, "B": 0.50, "C": 0.90}, n_per_group=200)
    fake = FakeInferenceBackend(predictions=[r["y_hat"] for r in aligned], num_labels=3)

    def _fake_load(*_a, **_k):
        return [
            {"text": r["text"], "label": r["label"], "sensitive": r["sensitive"]}
            for r in aligned
        ], 0

    monkeypatch.setattr(
        "app.probes.fairness.load_pairing_subset",
        lambda *_a, **_k: _fake_load(),
    )
    ctx, store = _ctx()
    out = FairnessProbe(inference=fake).run(ctx)
    ref = store.puts[0]
    key = ref.uri.split(f"s3://{store.bucket}/", 1)[1]
    artifact = json.loads(store.objects[key].decode("utf-8"))
    assert artifact["methodology_version"] == "tl-methodology-v1.0"
    assert artifact["osd_proposals"] == []
    assert artifact["metrics"].get("proposed_mapping") is False
    assert artifact["dataset"]["sensitive_attribute"] == "target_community"
    assert out.metric_values.get("subgroup_worst_group_acc_gap") is not None


def test_probe_invalid_sensitive_attribute_fails() -> None:
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(
            datasets={"fairness": "hatexplain_fairness"},
            extra={"sensitive_attribute": "not_declared"},
        )
    )
    out = FairnessProbe(inference=FakeInferenceBackend()).run(ctx)
    assert out.status is ProbeEvaluationStatus.FAILED
    assert "invalid_sensitive_attribute" in out.flags
    assert out.metric_values.get("subgroup_worst_group_acc_gap") is None


def test_pairing_probe_insufficient_on_tiny_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"text": "hello world", "label": 1, "sensitive": "GroupA"},
        {"text": "bad post", "label": 0, "sensitive": "GroupB"},
    ]
    fake = FakeInferenceBackend(predictions=[1, 2], num_labels=3)
    monkeypatch.setattr(
        "app.probes.fairness.load_pairing_subset",
        lambda *_a, **_k: (rows, 0),
    )
    ctx, _ = _ctx()
    out = FairnessProbe(inference=fake).run(ctx)
    assert out.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert out.metric_values["sensitive_attribute"] == "target_community"
    assert "multiclass_metrics_deferred" not in out.flags


def _run_pairing_with_extra_min_group_n(
    monkeypatch: pytest.MonkeyPatch,
    extra_min_group_n: int,
    aligned: list[dict],
):
    rows = [
        {"text": r["text"], "label": r["label"], "sensitive": r["sensitive"]}
        for r in aligned
    ]
    fake = FakeInferenceBackend(
        predictions=[r["y_hat"] for r in aligned],
        num_labels=3,
    )
    monkeypatch.setattr(
        "app.probes.fairness.load_pairing_subset",
        lambda *_a, **_k: (rows, 0),
    )
    ctx, _ = _ctx(
        probe_config=ProbeConfigV1(
            datasets={"fairness": "hatexplain_fairness"},
            extra={"min_group_n": extra_min_group_n},
        )
    )
    return FairnessProbe(inference=fake).run(ctx)


def test_pairing_min_group_n_cannot_weaken_dataset_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aligned = _rows("A", 160, 0.80) + _rows("B", 40, 0.50)
    assert len(aligned) == 200
    out = _run_pairing_with_extra_min_group_n(monkeypatch, 10, aligned)
    assert out.metric_values["min_group_n"] == 50
    assert out.status is ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert "G-FAIR-N-GROUP" in out.metric_values["reliability"]["failed_gates"]
    assert "B" in out.metric_values["excluded_groups"]
    assert out.metric_values["aspect_scoring"] == "not_scored"
    per_group = out.metric_values["per_group"]
    assert per_group["B"]["n"] == 40
    assert per_group["B"].get("excluded") is True


def test_pairing_min_group_n_cannot_raise_dataset_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aligned = _rows("A", 70, 0.80) + _rows("B", 70, 0.50) + _rows("C", 70, 0.70)
    assert len(aligned) == 210
    out = _run_pairing_with_extra_min_group_n(monkeypatch, 100, aligned)
    assert out.metric_values["min_group_n"] == 50
    assert "G-FAIR-N-GROUP" not in out.metric_values["reliability"]["failed_gates"]
    assert out.metric_values["excluded_groups"] == []
    assert out.status is not ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    per_group = out.metric_values["per_group"]
    assert per_group["A"]["n"] == 70
    assert per_group["B"]["n"] == 70
    assert per_group["C"]["n"] == 70
    assert not per_group["A"].get("excluded")
    assert not per_group["B"].get("excluded")
    assert not per_group["C"].get("excluded")
