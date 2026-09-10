"""Multiclass fairness evaluator tests (F-FAIR-PERF, network-free)."""

from __future__ import annotations

import pytest

from app.db.enums import ProbeEvaluationStatus
from app.probes.fairness_multiclass import evaluate_multiclass_fairness
from app.probes.fairness_stats import perf_trigger_fires

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
