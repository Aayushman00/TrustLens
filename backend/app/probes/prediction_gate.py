"""Detect single-class prediction collapse before behavioural metrics are scored.

A model that answers one class for (almost) every row is trivially "fair" and
"robust"; scoring it would reward a broken evaluation (see report chapter 7,
original toxic-bert run).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

COLLAPSE_THRESHOLD = 0.98
FLAG_CONSTANT_PREDICTOR = "constant_predictor"


def prediction_collapse(
    preds: Sequence[int], threshold: float = COLLAPSE_THRESHOLD
) -> tuple[bool, int | None, float]:
    if not preds:
        return False, None, 0.0
    cls, n = Counter(preds).most_common(1)[0]
    share = n / len(preds)
    return share >= threshold, cls, share
