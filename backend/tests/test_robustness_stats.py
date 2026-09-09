"""Unit tests for robustness_stats (network-free)."""

from __future__ import annotations

import pytest

from app.probes.robustness_stats import (
    BOOTSTRAP_B,
    EPSILON_DROP,
    accuracy_drop,
    paired_bootstrap_accuracy_drop_ci,
    pert_trigger_fires,
    relative_degradation,
    wilson_interval,
)


def _aligned(n: int, *, clean_acc: float, robust_acc: float) -> list[dict]:
    clean_correct = int(round(clean_acc * n))
    robust_correct = int(round(robust_acc * n))
    rows: list[dict] = []
    for i in range(n):
        label = i % 2
        yc = label if i < clean_correct else (1 - label)
        yr = label if i < robust_correct else (1 - label)
        rows.append({"label": label, "y_hat_clean": yc, "y_hat_robust": yr})
    return rows


def test_accuracy_drop_and_relative_degradation() -> None:
    assert accuracy_drop(0.9, 0.7) == pytest.approx(0.2)
    assert relative_degradation(0.0, 0.5) == pytest.approx(0.5 / 0.05)


def test_bootstrap_reproducible_with_fixed_seed() -> None:
    aligned = _aligned(120, clean_acc=0.9, robust_acc=0.6)
    a = paired_bootstrap_accuracy_drop_ci(aligned, B=BOOTSTRAP_B, seed=42)
    b = paired_bootstrap_accuracy_drop_ci(aligned, B=BOOTSTRAP_B, seed=42)
    assert a["ci_lower"] == b["ci_lower"]
    assert a["ci_upper"] == b["ci_upper"]
    assert a["point"] is not None


def test_pert_trigger_requires_both_point_and_ci_lower() -> None:
    assert pert_trigger_fires(0.08, 0.06) is True
    assert pert_trigger_fires(0.08, 0.04) is False
    assert pert_trigger_fires(0.04, 0.06) is False
    assert pert_trigger_fires(None, 0.06) is False


def test_wilson_interval_bounded() -> None:
    lo, hi = wilson_interval(50, 100)
    assert 0.0 <= lo <= hi <= 1.0


def test_ci_width_computable() -> None:
    aligned = _aligned(150, clean_acc=0.85, robust_acc=0.55)
    ci = paired_bootstrap_accuracy_drop_ci(aligned, B=200, seed=7)
    assert ci["ci_lower"] is not None
    assert ci["ci_upper"] is not None
    width = float(ci["ci_upper"]) - float(ci["ci_lower"])
    assert width > 0
    assert float(ci["point"]) > EPSILON_DROP or float(ci["ci_lower"]) <= EPSILON_DROP
