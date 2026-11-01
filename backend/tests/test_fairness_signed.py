"""Signed group gaps vs pooled (K11)."""

from __future__ import annotations

import random

from app.probes.fairness_signed import signed_group_gaps


def _pairs(rng: random.Random, n_pos: int, tpr: float) -> list[tuple[int, int]]:
    return [(1, int(rng.random() < tpr)) for _ in range(n_pos)]


def test_signed_gap_null_covers_zero():
    rng = random.Random(20261102)
    trials, covered = 500, {g: 0 for g in "ABCD"}
    for _ in range(trials):
        out = signed_group_gaps({g: _pairs(rng, 60, 0.5) for g in "ABCD"}, rate="tpr")
        for g, r in out.items():
            lo, hi = r["interval"]
            covered[g] += lo <= 0.0 <= hi
    assert all(c / trials >= 0.93 for c in covered.values()), covered


def test_signed_gap_sign():
    rng = random.Random(1)
    out = signed_group_gaps({"A": _pairs(rng, 200, 0.8), "B": _pairs(rng, 200, 0.5)}, rate="tpr")
    assert out["A"]["gap_vs_pooled"] > 0 and out["B"]["gap_vs_pooled"] < 0
    lo, _ = out["A"]["interval"]
    assert lo > 0
    assert out["A"]["applicability"] == "applicable"


def test_signed_gap_small_group_insufficient():
    rng = random.Random(2)
    out = signed_group_gaps({"A": _pairs(rng, 5, 0.5), "B": _pairs(rng, 100, 0.5)}, rate="tpr")
    assert out["A"]["applicability"].startswith("insufficient_evidence")
    assert out["A"]["interval"] is None


def test_signed_gap_single_group_no_reference():
    out = signed_group_gaps({"A": [(1, 1)] * 50}, rate="tpr")
    assert out["A"]["applicability"] == "insufficient_evidence(no_reference_group)"


def test_signed_gap_fpr_uses_negatives():
    pairs = {"A": [(0, 1)] * 30 + [(1, 0)] * 30, "B": [(0, 0)] * 30 + [(1, 1)] * 30}
    out = signed_group_gaps(pairs, rate="fpr")
    assert (out["A"]["k"], out["A"]["n"]) == (30, 30)
    assert out["A"]["gap_vs_pooled"] == 1.0
    lo, hi = out["A"]["interval"]
    assert lo > 0 and hi <= 1.0


def test_signed_gap_small_reference_insufficient():
    out = signed_group_gaps({"A": [(1, 1)] * 50, "B": [(1, 0)] * 5}, rate="tpr")
    assert out["A"]["applicability"] == "insufficient_evidence(reference_n<min)"
    assert out["A"]["interval"] is None
