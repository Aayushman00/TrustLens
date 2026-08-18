"""Original FRIES scorer (Phase 16) — pure functions, no DB/S3/Celery.

Implements exactly the frozen Phase 0 math (test oracle:
``shared/scoring/fixtures/fries_test_vectors.json``):

- O, S, D are **finalized** integers in 0..10; higher = better/safer
  (FRIES paper convention). The scorer never invents O/S/D from metrics —
  metric→O/S/D mapping is unresolved research (agent output is PROPOSED).
- Risk score ``Pi = cbrt(O * S * D)``.
- Veto: if any of O, S, D == 0 → ``Pi = 0``.
- Optimal: O = S = D = 10 → ``Pi = 10`` (cbrt identity; made explicit per
  fixture id 5).
- Aspect score ``Ti`` = arithmetic mean of ``Pi`` over that aspect's risks
  (no risks → 0; a vetoed risk drags the mean — matches fixtures).
- Final ``T = Σ ωᵢ·Tᵢ`` with default equal weights (0.2 per dimension).
- Weight constraints (fixture id 10): every ωᵢ ≥ 0.1 and Σωᵢ == 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, NamedTuple

FRIES_DIMENSIONS: tuple[str, ...] = (
    "FAIRNESS",
    "ROBUSTNESS",
    "INTEGRITY",
    "EXPLAINABILITY",
    "SAFETY",
)

_MIN_WEIGHT = 0.1
_WEIGHT_SUM_TOL = 1e-6


class OSDTriple(NamedTuple):
    """One finalized risk rating; fields follow the paper's O/S/D naming."""

    O: int
    S: int
    D: int


@dataclass
class FriesResult:
    fries_score: float
    dimension_scores: dict[str, float]
    per_risk: list[dict[str, Any]] = field(default_factory=list)


def _validate_component(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int in 0..10, got {value!r}")
    if not 0 <= value <= 10:
        raise ValueError(f"{name} must be within 0..10, got {value}")
    return value


def risk_pi(O: int, S: int, D: int) -> float:
    """``Pi = cbrt(O*S*D)``; veto to 0 if any component is 0."""
    o = _validate_component(O, "O")
    s = _validate_component(S, "S")
    d = _validate_component(D, "D")
    if 0 in (o, s, d):
        return 0.0
    if o == s == d == 10:
        return 10.0
    return math.cbrt(o * s * d)


def aspect_score(risks: list[OSDTriple]) -> float:
    """``Ti`` = mean of ``Pi`` over the aspect's risks; empty → 0."""
    if not risks:
        return 0.0
    return sum(risk_pi(r.O, r.S, r.D) for r in risks) / len(risks)


def _normalize_keys(mapping: dict[str, float], what: str) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, value in mapping.items():
        upper = str(key).upper()
        if upper in normalized:
            raise ValueError(f"duplicate {what} key after normalization: {key!r}")
        normalized[upper] = float(value)
    return normalized


def fries_total(
    aspect_scores: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """``T = Σ ωᵢ·Tᵢ``. Default equal weights; custom weights must cover the
    same aspects, each ≥ 0.1, summing to 1 (fixture id 10 floor rule)."""
    if not aspect_scores:
        raise ValueError("aspect_scores must not be empty")
    scores = _normalize_keys(aspect_scores, "aspect")
    if weights is None:
        share = 1.0 / len(scores)
        resolved = {key: share for key in scores}
    else:
        resolved = _normalize_keys(weights, "weight")
        if set(resolved) != set(scores):
            raise ValueError(
                f"weights keys {sorted(resolved)} must match aspects {sorted(scores)}"
            )
        if any(w < _MIN_WEIGHT for w in resolved.values()):
            raise ValueError(f"every weight must be >= {_MIN_WEIGHT} (paper constraint)")
        total_weight = sum(resolved.values())
        if abs(total_weight - 1.0) > _WEIGHT_SUM_TOL:
            raise ValueError(f"weights must sum to 1.0, got {total_weight}")
    return sum(resolved[key] * scores[key] for key in scores)


def _parse_risks(entry: dict[str, Any], aspect: str) -> list[OSDTriple]:
    raw_risks = entry.get("risks")
    if raw_risks is not None:
        if not isinstance(raw_risks, list) or not raw_risks:
            raise ValueError(f"aspect {aspect}: risks must be a non-empty list")
        sources: list[dict[str, Any]] = raw_risks
    else:
        sources = [entry]
    triples: list[OSDTriple] = []
    for source in sources:
        try:
            triples.append(
                OSDTriple(
                    _validate_component(source["O"], f"{aspect}.O"),
                    _validate_component(source["S"], f"{aspect}.S"),
                    _validate_component(source["D"], f"{aspect}.D"),
                )
            )
        except KeyError as exc:
            raise ValueError(f"aspect {aspect}: missing O/S/D key {exc}") from exc
    return triples


def score_from_finalized_osd(finalized_osd: dict[str, Any]) -> FriesResult:
    """Compute original FRIES from a finalized O/S/D document.

    Expected shape (MVP: one risk per aspect; ``risks`` list for multi-risk)::

        {
          "aspects": [
            {"aspect": "FAIRNESS", "O": 4, "S": 4, "D": 8},
            {"aspect": "ROBUSTNESS", "risks": [{"O":4,"S":8,"D":9}, ...]}
          ],
          "weights": {"FAIRNESS": 0.2, ...}   # optional; default equal
        }
    """
    aspects = finalized_osd.get("aspects")
    if not isinstance(aspects, list) or not aspects:
        raise ValueError("finalized_osd.aspects must be a non-empty list")

    dimension_scores: dict[str, float] = {}
    per_risk: list[dict[str, Any]] = []
    for entry in aspects:
        if not isinstance(entry, dict):
            raise TypeError(f"aspect entry must be a dict, got {type(entry).__name__}")
        aspect = str(entry.get("aspect", "")).upper()
        if not aspect:
            raise ValueError("aspect entry missing 'aspect' name")
        if aspect in dimension_scores:
            raise ValueError(f"duplicate aspect {aspect}; use a 'risks' list instead")
        triples = _parse_risks(entry, aspect)
        dimension_scores[aspect] = aspect_score(triples)
        per_risk.extend(
            {
                "aspect": aspect,
                "O": t.O,
                "S": t.S,
                "D": t.D,
                "pi": round(risk_pi(t.O, t.S, t.D), 4),
            }
            for t in triples
        )

    weights = finalized_osd.get("weights")
    total = fries_total(dimension_scores, weights)
    return FriesResult(
        fries_score=round(total, 4),
        dimension_scores={k: round(v, 4) for k, v in dimension_scores.items()},
        per_risk=per_risk,
    )
