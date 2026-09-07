"""Unit tests for fairness_stats (network-free)."""

from __future__ import annotations

import pytest

from app.probes.fairness_stats import (
    BOOTSTRAP_B,
    bootstrap_gap_ci,
    filter_compared_groups,
    group_accuracies_from_aligned,
    perf_trigger_fires,
    subgroup_worst_group_acc_gap,
    wilson_interval,
)


def _rows(group: str, n: int, accuracy: float) -> list[dict]:
    correct = int(round(accuracy * n))
    out: list[dict] = []
    for i in range(n):
        label = i % 3
        y_hat = label if i < correct else (label + 1) % 3
        out.append({"label": label, "y_hat": y_hat, "sensitive": group, "text": "t"})
    return out


def test_subgroup_gap_on_compared_groups() -> None:
    per_group = {
        "A": {"n": 60, "correct": 57, "accuracy": 0.95},
        "B": {"n": 60, "correct": 30, "accuracy": 0.5},
        "C": {"n": 60, "correct": 54, "accuracy": 0.9},
    }
    assert subgroup_worst_group_acc_gap(per_group) == pytest.approx(0.45)


def test_filter_compared_groups_excludes_thin() -> None:
    per_group = {
        "A": {"n": 60, "correct": 50, "accuracy": 0.83},
        "B": {"n": 30, "correct": 20, "accuracy": 0.67},
    }
    compared, excluded = filter_compared_groups(per_group, min_group_n=50)
    assert list(compared) == ["A"]
    assert excluded == ["B"]


def test_bootstrap_reproducible_with_fixed_seed() -> None:
    aligned = _rows("G1", 100, 0.9) + _rows("G2", 100, 0.5)
    a = bootstrap_gap_ci(aligned, min_group_n=50, B=BOOTSTRAP_B, seed=42)
    b = bootstrap_gap_ci(aligned, min_group_n=50, B=BOOTSTRAP_B, seed=42)
    assert a["ci_lower"] == b["ci_lower"]
    assert a["ci_upper"] == b["ci_upper"]


def test_perf_trigger_requires_both_point_and_ci_lower() -> None:
    assert perf_trigger_fires(0.05, 0.03) is True
    assert perf_trigger_fires(0.05, 0.02) is False
    assert perf_trigger_fires(0.02, 0.03) is False


def test_wilson_interval_bounded() -> None:
    lo, hi = wilson_interval(50, 100)
    assert 0.0 <= lo <= hi <= 1.0


def test_group_accuracies_from_aligned() -> None:
    aligned = _rows("X", 10, 0.8)
    stats = group_accuracies_from_aligned(aligned)
    assert stats["X"]["n"] == 10
