"""Unit tests for fairness_stats (network-free)."""

from __future__ import annotations

import pytest

from app.probes.fairness_stats import (
    BOOTSTRAP_B,
    CI_WIDE_THRESHOLD,
    _dp_gap_from_resampled,
    _eo_gap_from_resampled,
    _f1_gap_from_resampled,
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


def _binary_rows(group: str, n: int, positive_rate: float, correct: bool = True) -> list[dict]:
    """Binary (label/y_hat in {0,1}) rows for DP/EO/F1-spread adapters --
    _rows() above is 3-class, wrong shape for these."""
    n_pos = int(round(positive_rate * n))
    out: list[dict] = []
    for i in range(n):
        label = 1 if i < n_pos else 0
        y_hat = label if correct else 1 - label
        out.append({"label": label, "y_hat": y_hat, "sensitive": group})
    return out


def test_dp_gap_from_resampled_matches_demographic_parity_difference() -> None:
    from app.probes.fairness_metrics import demographic_parity_difference

    rows = _binary_rows("a", 50, 0.8) + _binary_rows("b", 50, 0.2)
    y_pred = [r["y_hat"] for r in rows]
    sensitive = [r["sensitive"] for r in rows]
    expected = demographic_parity_difference(y_pred, sensitive)
    assert _dp_gap_from_resampled(rows, min_group_n=10) == pytest.approx(expected)


def test_eo_gap_from_resampled_matches_equalized_odds_difference() -> None:
    from app.probes.fairness_metrics import equalized_odds_difference

    rows = _binary_rows("a", 50, 0.5) + _binary_rows("b", 50, 0.5, correct=False)
    y_true = [r["label"] for r in rows]
    y_pred = [r["y_hat"] for r in rows]
    sensitive = [r["sensitive"] for r in rows]
    expected = equalized_odds_difference(y_true, y_pred, sensitive)
    assert _eo_gap_from_resampled(rows, min_group_n=10) == pytest.approx(expected)


def test_f1_gap_from_resampled_matches_subgroup_f1_spread() -> None:
    from app.probes.fairness_metrics import subgroup_f1_spread

    rows = _binary_rows("a", 50, 0.5) + _binary_rows("b", 50, 0.5, correct=False)
    y_true = [r["label"] for r in rows]
    y_pred = [r["y_hat"] for r in rows]
    sensitive = [r["sensitive"] for r in rows]
    expected = subgroup_f1_spread(y_true, y_pred, sensitive)
    assert _f1_gap_from_resampled(rows, min_group_n=10) == pytest.approx(expected)


def test_dp_gap_from_resampled_returns_none_when_thin_groups_leave_fewer_than_2() -> None:
    rows = _binary_rows("a", 50, 0.8) + _binary_rows("b", 3, 0.2)
    assert _dp_gap_from_resampled(rows, min_group_n=10) is None


def test_bootstrap_gap_ci_with_dp_stat_fn_is_reproducible_with_fixed_seed() -> None:
    """stat_fn wiring works end to end through bootstrap_gap_ci's resampling
    loop, and stays deterministic under a fixed seed (same contract the
    existing accuracy-gap default already has)."""
    rows = _binary_rows("a", 100, 0.9) + _binary_rows("b", 100, 0.1)
    a = bootstrap_gap_ci(rows, min_group_n=50, B=200, seed=42, stat_fn=_dp_gap_from_resampled)
    b = bootstrap_gap_ci(rows, min_group_n=50, B=200, seed=42, stat_fn=_dp_gap_from_resampled)
    assert a["ci_lower"] == b["ci_lower"]
    assert a["ci_upper"] == b["ci_upper"]
    assert a["point"] == pytest.approx(0.8, abs=1e-6)


def test_bootstrap_gap_ci_omitting_stat_fn_still_bootstraps_accuracy_gap() -> None:
    """Regression guard: every existing caller (evaluate_multiclass_fairness)
    omits stat_fn -- must still get exactly the original accuracy-gap
    behavior, not a changed default."""
    from app.probes.fairness_stats import _gap_from_resampled

    rows = _rows("G1", 100, 0.9) + _rows("G2", 100, 0.5)
    with_default = bootstrap_gap_ci(rows, min_group_n=50, B=BOOTSTRAP_B, seed=42)
    explicit_original_stat = bootstrap_gap_ci(
        rows, min_group_n=50, B=BOOTSTRAP_B, seed=42, stat_fn=_gap_from_resampled
    )
    assert with_default["point"] == explicit_original_stat["point"]
    assert with_default["ci_lower"] == explicit_original_stat["ci_lower"]
    assert with_default["ci_upper"] == explicit_original_stat["ci_upper"]


def test_bootstrap_gap_ci_wide_ci_on_small_noisy_dp_sample() -> None:
    """A tiny, noisy sample produces a wide bootstrap CI on DP -- the
    scenario the G-FAIR-CI-WIDE gate exists to catch."""
    rows = _binary_rows("a", 4, 0.5) + _binary_rows("b", 4, 0.5, correct=False)
    result = bootstrap_gap_ci(rows, min_group_n=2, B=500, seed=42, stat_fn=_dp_gap_from_resampled)
    assert result["ci_upper"] is not None and result["ci_lower"] is not None
    assert (result["ci_upper"] - result["ci_lower"]) > CI_WIDE_THRESHOLD


def _three_way_rows(group: str, *, n1: int, n0: int, n2: int) -> list[dict]:
    """Rows with a THIRD possible y_hat value (2) besides 0/1 -- needed to
    show demographic_parity_difference actually depends on
    positive_label_index. With only two possible prediction values, rate_0
    and rate_1 are complements (sum to 1), so DP's unsigned max-min spread
    is coincidentally identical either way; a real >=3-class model (or a
    binary target with a stray predicted index) breaks that coincidence."""
    out: list[dict] = []
    for i in range(n1):
        out.append({"label": 1, "y_hat": 1, "sensitive": group})
    for i in range(n0):
        out.append({"label": 0, "y_hat": 0, "sensitive": group})
    for i in range(n2):
        out.append({"label": 0, "y_hat": 2, "sensitive": group})
    return out


def test_dp_gap_from_resampled_uses_passed_positive_label_index_not_literal_1() -> None:
    """The adapter must read positive_label_index from its own argument, not
    assume 1 -- a real (>=3-class) model can produce a predicted index
    outside {0,1}, at which point which index counts as "positive" changes
    the actual DP value, not just its sign."""
    rows = _three_way_rows("a", n1=30, n0=15, n2=5) + _three_way_rows("b", n1=10, n0=15, n2=25)
    gap_index_1 = _dp_gap_from_resampled(rows, min_group_n=10, positive_label_index=1)
    gap_index_0 = _dp_gap_from_resampled(rows, min_group_n=10, positive_label_index=0)
    assert gap_index_1 == pytest.approx(0.4, abs=1e-9)
    assert gap_index_0 == pytest.approx(0.0, abs=1e-9)
    assert gap_index_1 != gap_index_0


_ASYMMETRIC_Y_TRUE = [1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 1, 0]
_ASYMMETRIC_Y_PRED = [0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 0]
_ASYMMETRIC_SENSITIVE = ["a", "a", "a", "a", "a", "a", "b", "b", "a", "a", "a", "a", "a", "a", "a", "b", "b", "a", "a", "b"]


def test_equalized_odds_difference_depends_on_positive_label_index() -> None:
    """EO (TPR/FPR) is asymmetric under a 0/1 relabel for a non-degenerate
    confusion matrix -- flipping positive_label_index must change the
    computed value, proving the metric function itself (not just the
    resampling adapter) reads the parameter rather than hardcoding 1."""
    from app.probes.fairness_metrics import equalized_odds_difference

    eo_1 = equalized_odds_difference(
        _ASYMMETRIC_Y_TRUE, _ASYMMETRIC_Y_PRED, _ASYMMETRIC_SENSITIVE, positive_label_index=1
    )
    eo_0 = equalized_odds_difference(
        _ASYMMETRIC_Y_TRUE, _ASYMMETRIC_Y_PRED, _ASYMMETRIC_SENSITIVE, positive_label_index=0
    )
    assert eo_1 == pytest.approx(0.454545, abs=1e-5)
    assert eo_0 == pytest.approx(0.545455, abs=1e-5)
    assert eo_1 != eo_0


def test_subgroup_f1_spread_depends_on_positive_label_index() -> None:
    from app.probes.fairness_metrics import subgroup_f1_spread

    f1_1 = subgroup_f1_spread(
        _ASYMMETRIC_Y_TRUE, _ASYMMETRIC_Y_PRED, _ASYMMETRIC_SENSITIVE, positive_label_index=1
    )
    f1_0 = subgroup_f1_spread(
        _ASYMMETRIC_Y_TRUE, _ASYMMETRIC_Y_PRED, _ASYMMETRIC_SENSITIVE, positive_label_index=0
    )
    assert f1_1 != f1_0


def test_positive_label_index_defaults_to_1_matching_pre_change_behavior() -> None:
    """Regression guard: every caller that omits positive_label_index must
    get exactly the pre-change (hardcoded-1) numeric result."""
    from app.probes.fairness_metrics import demographic_parity_difference, equalized_odds_difference

    y_true = [1, 0, 1, 0, 1, 0]
    y_pred = [1, 0, 0, 0, 1, 1]
    sensitive = ["a", "a", "a", "b", "b", "b"]

    assert demographic_parity_difference(y_pred, sensitive) == demographic_parity_difference(
        y_pred, sensitive, positive_label_index=1
    )
    assert equalized_odds_difference(y_true, y_pred, sensitive) == equalized_odds_difference(
        y_true, y_pred, sensitive, positive_label_index=1
    )


def test_bootstrap_gap_ci_tight_ci_on_large_stable_dp_sample() -> None:
    """A larger, cleanly-separated sample produces a tight bootstrap CI on
    DP -- must NOT trip the wide-CI gate."""
    rows = _binary_rows("a", 200, 0.9) + _binary_rows("b", 200, 0.1)
    result = bootstrap_gap_ci(rows, min_group_n=50, B=500, seed=42, stat_fn=_dp_gap_from_resampled)
    assert result["ci_upper"] is not None and result["ci_lower"] is not None
    assert (result["ci_upper"] - result["ci_lower"]) <= CI_WIDE_THRESHOLD
