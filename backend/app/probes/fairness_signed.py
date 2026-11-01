"""Signed group gaps vs the pooled rest (replaces max - min decisions; K11)."""

from __future__ import annotations

from typing import Literal

from app.posterior.rates import newcombe_interval


def signed_group_gaps(
    pairs_by_group: dict[str, list[tuple[int, int]]],
    *,
    rate: Literal["tpr", "fpr"],
    positive_label_index: int = 1,
    min_group_n: int = 20,
    level: float = 0.95,
) -> dict[str, dict]:
    """Per group: rate minus the rate of all other groups combined, with a
    Newcombe interval on (group, rest). Eligible rows are positives for TPR,
    negatives for FPR; k = predicted-positive among them."""
    want_pos = rate == "tpr"
    counts: dict[str, tuple[int, int]] = {}
    for g, pairs in pairs_by_group.items():
        elig = [yp for yt, yp in pairs if (yt == positive_label_index) == want_pos]
        counts[g] = (sum(yp == positive_label_index for yp in elig), len(elig))
    total_k = sum(k for k, _ in counts.values())
    total_n = sum(n for _, n in counts.values())

    out: dict[str, dict] = {}
    for g, (k, n) in counts.items():
        row = {"k": k, "n": n, "rate": k / n if n else None, "gap_vs_pooled": None, "interval": None}
        kr, nr = total_k - k, total_n - n
        if n < min_group_n:
            row["applicability"] = "insufficient_evidence(group_n<min)"
        elif nr == 0:
            row["applicability"] = "insufficient_evidence(no_reference_group)"
        elif nr < min_group_n:
            row["applicability"] = "insufficient_evidence(reference_n<min)"
        else:
            row["gap_vs_pooled"] = k / n - kr / nr
            row["interval"] = newcombe_interval(k, n, kr, nr, level)
            row["applicability"] = "applicable"
        out[g] = row
    return out
