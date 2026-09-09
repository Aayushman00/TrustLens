"""Robustness statistics (tl-methodology-v1.0) — stdlib only."""

from __future__ import annotations

import math
import random
from typing import Any, Sequence

from app.probes.fairness_stats import wilson_interval

EPSILON_DROP = 0.05
BOOTSTRAP_B = 1000
CI_WIDE_THRESHOLD = 0.20
SCORED_RISK_ID = "R-ROB-PERT"
MIN_EVALUATED = 100
MIN_REQUESTED = 200
LABEL_COMPAT_MIN_FRACTION = 0.95
CLEAN_FLOOR = 0.20
REL_DEG_EPSILON = 0.05
METHODOLOGY_VERSION = "tl-methodology-v1.0"


def accuracy_drop(clean: float, robust: float) -> float:
    """Primary scored scalar: clean_accuracy − robust_accuracy."""
    return clean - robust


def relative_degradation(
    clean: float,
    robust: float,
    *,
    epsilon: float = REL_DEG_EPSILON,
) -> float:
    """robust / max(clean, ε) — evidence only."""
    return robust / max(clean, epsilon)


def _row_drop(row: dict[str, Any]) -> float:
    clean_ok = int(row["y_hat_clean"]) == int(row["label"])
    robust_ok = int(row["y_hat_robust"]) == int(row["label"])
    return float(clean_ok) - float(robust_ok)


def _accuracy_from_rows(rows: Sequence[dict[str, Any]], pred_key: str) -> float:
    if not rows:
        return 0.0
    correct = sum(1 for r in rows if int(r[pred_key]) == int(r["label"]))
    return correct / len(rows)


def paired_bootstrap_accuracy_drop_ci(
    aligned: Sequence[dict[str, Any]],
    *,
    B: int = BOOTSTRAP_B,
    seed: int,
) -> dict[str, Any]:
    """Bootstrap percentile CI for accuracy_drop (paired row resample)."""
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

    clean_acc = _accuracy_from_rows(rows, "y_hat_clean")
    robust_acc = _accuracy_from_rows(rows, "y_hat_robust")
    point = accuracy_drop(clean_acc, robust_acc)

    rng = random.Random(seed)
    bootstrap_values: list[float] = []
    for _ in range(B):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        c = _accuracy_from_rows(sample, "y_hat_clean")
        r = _accuracy_from_rows(sample, "y_hat_robust")
        bootstrap_values.append(accuracy_drop(c, r))

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


def accuracy_wilson_uncertainty(
    correct: int,
    n: int,
) -> dict[str, Any]:
    """Wilson 95% CI for an accuracy proportion."""
    lo, hi = wilson_interval(correct, n)
    point = correct / n if n else 0.0
    return {
        "point": round(point, 6),
        "ci_lower": round(lo, 6),
        "ci_upper": round(hi, 6),
        "method": "wilson_score",
    }


def pert_trigger_fires(point: float | None, ci_lower: float | None) -> bool:
    """R-ROB-PERT trigger: point > ε_drop AND ci_lower > ε_drop."""
    if point is None or ci_lower is None:
        return False
    return point > EPSILON_DROP and ci_lower > EPSILON_DROP
