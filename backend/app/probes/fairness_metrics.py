"""Group fairness metric helpers (Phase 12).

Pure stdlib/numpy-free implementations so unit tests need no ML stack.

Formulas (binary positive class = 1):
- demographic_parity_difference = max_g P(Ŷ=1|A=g) − min_g P(Ŷ=1|A=g)
- equalized_odds_difference = max( |ΔTPR|, |ΔFPR| ) across groups
  (max_g TPR − min_g TPR and max_g FPR − min_g FPR)
- subgroup_f1_spread = max_g F1_g − min_g F1_g

These are objective evidence only — not a normative fair/unfair verdict and not O/S/D.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Hashable, Sequence


def _as_list(values: Sequence[Any]) -> list[Any]:
    return list(values)


def _groups(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    sensitive: Sequence[Hashable],
) -> dict[Hashable, list[tuple[int, int]]]:
    if not (len(y_true) == len(y_pred) == len(sensitive)):
        raise ValueError("y_true, y_pred, and sensitive must have equal length")
    buckets: dict[Hashable, list[tuple[int, int]]] = defaultdict(list)
    for yt, yp, a in zip(y_true, y_pred, sensitive, strict=True):
        buckets[a].append((int(yt), int(yp)))
    if len(buckets) < 2:
        raise ValueError("need at least two sensitive groups")
    return buckets


def _positive_rate(pairs: list[tuple[int, int]]) -> float:
    if not pairs:
        return 0.0
    return sum(1 for _, yp in pairs if yp == 1) / len(pairs)


def _tpr_fpr(pairs: list[tuple[int, int]]) -> tuple[float, float]:
    pos = [(yt, yp) for yt, yp in pairs if yt == 1]
    neg = [(yt, yp) for yt, yp in pairs if yt == 0]
    tpr = (sum(1 for _, yp in pos if yp == 1) / len(pos)) if pos else 0.0
    fpr = (sum(1 for _, yp in neg if yp == 1) / len(neg)) if neg else 0.0
    return tpr, fpr


def _f1(pairs: list[tuple[int, int]]) -> float:
    tp = sum(1 for yt, yp in pairs if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in pairs if yt == 0 and yp == 1)
    fn = sum(1 for yt, yp in pairs if yt == 1 and yp == 0)
    if tp == 0 and fp == 0 and fn == 0:
        return 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def demographic_parity_difference(
    y_pred: Sequence[Any],
    sensitive: Sequence[Hashable],
) -> float:
    """Max−min selection rate P(Ŷ=1|A) across sensitive groups."""
    # Pair with dummy y_true for grouping API
    y_true = [0] * len(y_pred)
    buckets = _groups(y_true, y_pred, sensitive)
    rates = [_positive_rate(pairs) for pairs in buckets.values()]
    return float(max(rates) - min(rates))


def equalized_odds_difference(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    sensitive: Sequence[Hashable],
) -> float:
    """Max of (max−min TPR) and (max−min FPR) across groups."""
    buckets = _groups(y_true, y_pred, sensitive)
    tprs: list[float] = []
    fprs: list[float] = []
    for pairs in buckets.values():
        tpr, fpr = _tpr_fpr(pairs)
        tprs.append(tpr)
        fprs.append(fpr)
    return float(max(max(tprs) - min(tprs), max(fprs) - min(fprs)))


def subgroup_f1_spread(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    sensitive: Sequence[Hashable],
) -> float:
    """Max−min binary F1 across sensitive groups."""
    buckets = _groups(y_true, y_pred, sensitive)
    scores = [_f1(pairs) for pairs in buckets.values()]
    return float(max(scores) - min(scores))


def per_group_stats(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    sensitive: Sequence[Hashable],
) -> dict[str, dict[str, float | int]]:
    """Per-group n, F1, positive_rate, TPR, FPR."""
    buckets = _groups(y_true, y_pred, sensitive)
    out: dict[str, dict[str, float | int]] = {}
    for group, pairs in buckets.items():
        tpr, fpr = _tpr_fpr(pairs)
        out[str(group)] = {
            "n": len(pairs),
            "f1": round(_f1(pairs), 6),
            "positive_rate": round(_positive_rate(pairs), 6),
            "tpr": round(tpr, 6),
            "fpr": round(fpr, 6),
        }
    return out


def compute_fairness_bundle(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    sensitive: Sequence[Hashable],
) -> dict[str, Any]:
    """Compute all Phase 12 fairness metrics in one pass."""
    groups = per_group_stats(y_true, y_pred, sensitive)
    return {
        "demographic_parity_difference": round(
            demographic_parity_difference(y_pred, sensitive), 6
        ),
        "equalized_odds_difference": round(
            equalized_odds_difference(y_true, y_pred, sensitive), 6
        ),
        "subgroup_f1_spread": round(
            subgroup_f1_spread(y_true, y_pred, sensitive), 6
        ),
        "groups": groups,
        "min_group_n_observed": min(int(g["n"]) for g in groups.values()),
    }
