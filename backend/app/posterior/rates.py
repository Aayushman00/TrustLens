"""Exact rate intervals (K13): Jeffreys for a rate, Newcombe for a difference.

Replaces percentile bootstrap / Wald for rates (0.39 coverage at n=10, S3-A).
"""

from __future__ import annotations

import math

from scipy.stats import beta, norm

from app.probes.fairness_stats import wilson_interval


def jeffreys_interval(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Equal-tailed Beta(k+1/2, n-k+1/2) interval; pinned to 0 / 1 at the edges."""
    a = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else float(beta.ppf(a, k + 0.5, n - k + 0.5))
    hi = 1.0 if k == n else float(beta.ppf(1.0 - a, k + 0.5, n - k + 0.5))
    return lo, hi


def p_exceeds(k: int, n: int, tau: float) -> float:
    """P(rate > tau) under the Jeffreys posterior."""
    return float(beta.sf(tau, k + 0.5, n - k + 0.5))


def newcombe_interval(
    ka: int, na: int, kb: int, nb: int, level: float = 0.95
) -> tuple[float, float]:
    """Newcombe hybrid-score interval for p_a - p_b (method 10), from Wilson bounds."""
    z = float(norm.ppf(1.0 - (1.0 - level) / 2.0))
    la, ua = wilson_interval(ka, na, z=z)
    lb, ub = wilson_interval(kb, nb, z=z)
    pa, pb = ka / na, kb / nb
    d = pa - pb
    return (
        d - math.sqrt((pa - la) ** 2 + (ub - pb) ** 2),
        d + math.sqrt((ua - pa) ** 2 + (pb - lb) ** 2),
    )


def bonferroni_level(level: float, max_looks: int) -> float:
    return 1.0 - (1.0 - level) / max_looks
