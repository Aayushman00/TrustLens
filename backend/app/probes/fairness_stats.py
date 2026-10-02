"""Fairness statistics (tl-methodology-v1.0) — stdlib only.

Originally multiclass-only; ``bootstrap_gap_ci``'s resampling/percentile-CI
machinery is stat-agnostic (it just needs a "row sample -> gap or None"
function), so binary Fairness's DP/EO/F1-spread bootstrap CI reuses it via
the ``stat_fn`` parameter instead of duplicating the resampling loop.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Callable, Hashable, Sequence

from app.probes.fairness_metrics import (
    demographic_parity_difference,
    equal_opportunity_difference,
    equalized_odds_difference,
    label_rate_gap,
    subgroup_f1_spread,
)

EPSILON = 0.02
BOOTSTRAP_B = 1000
CI_WIDE_THRESHOLD = 0.15
SCORED_RISK_ID = "F-FAIR-PERF"
METHODOLOGY_VERSION = "tl-methodology-v1.0"

# Binary fairness risk rule (round 3, L4.1): the equal-opportunity (TPR) gap
# with the methodology-wide EPSILON and the same "point > ε AND bootstrap
# ci_lower > ε" structure as multiclass F-FAIR-PERF. tl-fairness-binary-v1.1
# (excess_dpd_v2 trigger) was an exploratory candidate, rejected after
# inspection for its base-rate dependence; this rule was chosen after that
# inspection, not pre-registered before it.
BINARY_METHODOLOGY_VERSION = "tl-fairness-binary-v1.2"
BINARY_RISK_ID = "F-FAIR-EOPP"
# TPR needs TP + FN > 0 in every eligible group; precision beyond that is
# handled by the G-FAIR-CI-WIDE gate on the EOD CI, not by a larger floor.
MIN_GROUP_POSITIVES = 1


def wilson_interval(
    successes: int,
    n: int,
    *,
    z: float = 1.96,
) -> tuple[float, float]:
    """Wilson score 95% interval for a binomial proportion."""
    if n <= 0:
        return 0.0, 0.0
    p_hat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))
    return max(0.0, center - margin), min(1.0, center + margin)


def group_accuracies_from_aligned(
    aligned: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Per-group accuracy from aligned rows using normalized ``sensitive`` field."""
    buckets: dict[Hashable, list[tuple[int, int]]] = defaultdict(list)
    for row in aligned:
        label = int(row["label"])
        pred = int(row["y_hat"])
        group = row["sensitive"]
        buckets[group].append((label, pred))
    out: dict[str, dict[str, Any]] = {}
    for group, pairs in buckets.items():
        correct = sum(1 for yt, yp in pairs if yt == yp)
        n = len(pairs)
        out[str(group)] = {
            "n": n,
            "correct": correct,
            "accuracy": correct / n if n else 0.0,
        }
    return out


def filter_compared_groups(
    per_group: dict[str, dict[str, Any]],
    min_group_n: int,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Exclude thin groups; return compared groups and excluded group names."""
    compared: dict[str, dict[str, Any]] = {}
    excluded: list[str] = []
    for name, stats in per_group.items():
        n = int(stats["n"])
        if n < min_group_n:
            excluded.append(name)
            continue
        compared[name] = dict(stats)
    return compared, excluded


def subgroup_worst_group_acc_gap(acc_by_group: dict[str, dict[str, Any]]) -> float:
    """max_g acc_g - min_g acc_g on compared groups."""
    if len(acc_by_group) < 2:
        return 0.0
    accs = [float(g["accuracy"]) for g in acc_by_group.values()]
    return float(max(accs) - min(accs))


def _gap_from_resampled(
    sample: Sequence[dict[str, Any]],
    min_group_n: int,
) -> float | None:
    per_group = group_accuracies_from_aligned(sample)
    compared, _ = filter_compared_groups(per_group, min_group_n)
    if len(compared) < 2:
        return None
    return subgroup_worst_group_acc_gap(compared)


def _filtered_group_rows(
    sample: Sequence[dict[str, Any]], min_group_n: int
) -> list[dict[str, Any]] | None:
    """Same thin-group exclusion as ``_gap_from_resampled``, factored out so
    the DP/EO/F1 adapters below apply the identical min_group_n policy:
    drop rows whose group has n < min_group_n, then require at least 2
    groups remain (a gap needs 2+ groups to compare)."""
    counts: dict[Any, int] = defaultdict(int)
    for row in sample:
        counts[row["sensitive"]] += 1
    kept_groups = {g for g, n in counts.items() if n >= min_group_n}
    if len(kept_groups) < 2:
        return None
    return [row for row in sample if row["sensitive"] in kept_groups]


def _dp_gap_from_resampled(
    sample: Sequence[dict[str, Any]], min_group_n: int, *, positive_label_index: int = 1
) -> float | None:
    """``stat_fn`` adapter: bootstraps demographic_parity_difference instead
    of accuracy gap, reusing bootstrap_gap_ci's resampling loop unchanged.
    ``positive_label_index`` must come from the same contract value
    fairness.py resolves for the point estimate -- never hardcoded 1 here,
    since a valid label_mapping can assign the favorable outcome elsewhere."""
    rows = _filtered_group_rows(sample, min_group_n)
    if rows is None:
        return None
    y_pred = [int(r["y_hat"]) for r in rows]
    sensitive = [r["sensitive"] for r in rows]
    return demographic_parity_difference(y_pred, sensitive, positive_label_index=positive_label_index)


def _eo_gap_from_resampled(
    sample: Sequence[dict[str, Any]], min_group_n: int, *, positive_label_index: int = 1
) -> float | None:
    """``stat_fn`` adapter: bootstraps equalized_odds_difference."""
    rows = _filtered_group_rows(sample, min_group_n)
    if rows is None:
        return None
    y_true = [int(r["label"]) for r in rows]
    y_pred = [int(r["y_hat"]) for r in rows]
    sensitive = [r["sensitive"] for r in rows]
    return equalized_odds_difference(y_true, y_pred, sensitive, positive_label_index=positive_label_index)


def _f1_gap_from_resampled(
    sample: Sequence[dict[str, Any]], min_group_n: int, *, positive_label_index: int = 1
) -> float | None:
    """``stat_fn`` adapter: bootstraps subgroup_f1_spread."""
    rows = _filtered_group_rows(sample, min_group_n)
    if rows is None:
        return None
    y_true = [int(r["label"]) for r in rows]
    y_pred = [int(r["y_hat"]) for r in rows]
    sensitive = [r["sensitive"] for r in rows]
    return subgroup_f1_spread(y_true, y_pred, sensitive, positive_label_index=positive_label_index)


def bootstrap_gap_ci(
    aligned: Sequence[dict[str, Any]],
    *,
    min_group_n: int,
    B: int = BOOTSTRAP_B,
    seed: int,
    stat_fn: Callable[[Sequence[dict[str, Any]], int], float | None] = _gap_from_resampled,
) -> dict[str, Any]:
    """Bootstrap percentile CI for a row-resampled statistic.

    ``stat_fn`` computes the statistic for one row sample (the original full
    dataset for the point estimate, then each of ``B`` resamples) and
    returns ``None`` when the sample can't support it (e.g. fewer than 2
    groups survive thin-group exclusion). Defaults to
    ``subgroup_worst_group_acc_gap`` (the original, multiclass, behavior) --
    every existing caller that omits ``stat_fn`` is unaffected. Binary
    Fairness passes ``_dp_gap_from_resampled``/``_eo_gap_from_resampled``/
    ``_f1_gap_from_resampled`` instead to bootstrap DP/EO/F1-spread with the
    exact same resampling machinery.
    """
    rows = list(aligned)
    n = len(rows)
    if n == 0:
        return {
            "point": None,
            "ci_lower": None,
            "ci_upper": None,
            "method": "bootstrap_percentile",
            "B": B,
        }

    point = stat_fn(rows, min_group_n)
    rng = random.Random(seed)
    bootstrap_values: list[float] = []
    for _ in range(B):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        gap = stat_fn(sample, min_group_n)
        if gap is not None:
            bootstrap_values.append(gap)

    if point is None or not bootstrap_values:
        return {
            "point": point,
            "ci_lower": None,
            "ci_upper": None,
            "method": "bootstrap_percentile",
            "B": B,
        }

    bootstrap_values.sort()
    lo_idx = max(0, int(0.025 * len(bootstrap_values)))
    hi_idx = min(len(bootstrap_values) - 1, int(math.ceil(0.975 * len(bootstrap_values)) - 1))
    return {
        "point": round(point, 6),
        "ci_lower": round(bootstrap_values[lo_idx], 6),
        "ci_upper": round(bootstrap_values[hi_idx], 6),
        "method": "bootstrap_percentile",
        "B": B,
    }


def per_group_wilson_uncertainty(
    per_group: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Wilson 95% CI for each group's accuracy."""
    out: dict[str, dict[str, Any]] = {}
    for name, stats in per_group.items():
        correct = int(stats["correct"])
        n = int(stats["n"])
        lo, hi = wilson_interval(correct, n)
        out[name] = {
            "point": round(float(stats["accuracy"]), 6),
            "ci_lower": round(lo, 6),
            "ci_upper": round(hi, 6),
            "method": "wilson_score",
        }
    return out


def perf_trigger_fires(point: float | None, ci_lower: float | None) -> bool:
    """F-FAIR-PERF trigger: point > ε AND ci_lower > ε."""
    if point is None or ci_lower is None:
        return False
    return point > EPSILON and ci_lower > EPSILON


def excess_dpd_v1(
    y_true: Sequence[int], y_pred: Sequence[int], sensitive: Sequence[Any], *, positive_label_index: int = 1
) -> float:
    """Original (tl-methodology-v1.0) excess DPD: max(DPD - label-rate gap, 0).
    Direction-blind: compares two spreads, so a model that compresses or
    reverses the label gap reads as 0."""
    dpd = demographic_parity_difference(y_pred, sensitive, positive_label_index=positive_label_index)
    gap = label_rate_gap(y_true, sensitive, positive_label_index=positive_label_index)
    return max(dpd - gap, 0.0)


def _eopp_gap_from_resampled(
    sample: Sequence[dict[str, Any]], min_group_n: int, *, positive_label_index: int = 1
) -> float | None:
    """``stat_fn`` adapter: bootstraps equal_opportunity_difference over groups
    with n >= min_group_n; a replicate where a kept group has no positive
    label (TPR undefined) yields None."""
    rows = _filtered_group_rows(sample, min_group_n)
    if rows is None:
        return None
    try:
        return equal_opportunity_difference(
            [int(r["label"]) for r in rows],
            [int(r["y_hat"]) for r in rows],
            [r["sensitive"] for r in rows],
            positive_label_index=positive_label_index,
        )
    except ValueError:
        return None


def binary_eligibility(
    aligned: Sequence[dict[str, Any]], min_group_n: int, *, positive_label_index: int = 1
) -> dict[str, Any]:
    """Groups eligible for the EOD rule: n >= min_group_n, and every eligible
    group must hold >= MIN_GROUP_POSITIVES positive labels (TPR undefined
    otherwise). ``failed_gate`` is None when eligible."""
    n: dict[str, int] = defaultdict(int)
    pos: dict[str, int] = defaultdict(int)
    for r in aligned:
        g = str(r["sensitive"])
        n[g] += 1
        pos[g] += int(r["label"]) == positive_label_index
    eligible = sorted(g for g in n if n[g] >= min_group_n)
    failed_gate = None
    if len(eligible) < 2:
        failed_gate = "G-FAIR-N-GROUP"
    elif any(pos[g] < MIN_GROUP_POSITIVES for g in eligible):
        failed_gate = "G-FAIR-POSITIVES"
    return {
        "eligible_groups": eligible,
        "positives": {g: pos[g] for g in sorted(n)},
        "min_positives_per_group": MIN_GROUP_POSITIVES,
        "failed_gate": failed_gate,
    }


def binary_fairness_decision(ci: dict[str, Any]) -> dict[str, Any]:
    """Map the equal-opportunity-difference bootstrap result to a finding.

    FAIRNESS_RISK         point > ε and ci_lower > ε  -> risk_detected, [BINARY_RISK_ID]
    DISPARITY_OBSERVED    point > ε, ci_lower <= ε    -> disparity_observed (no risk)
    NO_MATERIAL_DISPARITY point <= ε                  -> no_material_risk
    INSUFFICIENT_EVIDENCE no point estimate or no CI  -> not_scored (abstain)
    """
    point, lo = ci.get("point"), ci.get("ci_lower")
    if point is None or lo is None or ci.get("ci_upper") is None:
        finding, aspect = "INSUFFICIENT_EVIDENCE", "not_scored"
    elif point <= EPSILON:
        finding, aspect = "NO_MATERIAL_DISPARITY", "no_material_risk"
    elif lo > EPSILON:
        finding, aspect = "FAIRNESS_RISK", "risk_detected"
    else:
        finding, aspect = "DISPARITY_OBSERVED", "disparity_observed"
    return {
        "finding": finding,
        "aspect_scoring": aspect,
        "risks_triggered": [BINARY_RISK_ID] if finding == "FAIRNESS_RISK" else [],
    }
