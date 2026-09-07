"""Multiclass fairness statistics (tl-methodology-v1.0) — stdlib only."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Hashable, Sequence

EPSILON = 0.02
BOOTSTRAP_B = 1000
CI_WIDE_THRESHOLD = 0.15
SCORED_RISK_ID = "F-FAIR-PERF"
METHODOLOGY_VERSION = "tl-methodology-v1.0"


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


def bootstrap_gap_ci(
    aligned: Sequence[dict[str, Any]],
    *,
    min_group_n: int,
    B: int = BOOTSTRAP_B,
    seed: int,
) -> dict[str, Any]:
    """Bootstrap percentile CI for subgroup_worst_group_acc_gap (row resample)."""
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

    point = _gap_from_resampled(rows, min_group_n)
    rng = random.Random(seed)
    bootstrap_values: list[float] = []
    for _ in range(B):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        gap = _gap_from_resampled(sample, min_group_n)
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
