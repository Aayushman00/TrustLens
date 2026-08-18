"""Confidence Engine (Phase 15) — pure factor model, no DB/S3.

Each FRIES dimension gets three factors in [0, 1]:

- ``data_quality`` — input/data adequacy (fairness group sizes, robustness
  ``n_samples``, integrity check pass fraction, card ``coverage_ratio``).
- ``probe_reliability`` — did the intended path run? 1.0 for a full run;
  ~0.4–0.6 on soft skips (``unsupported_modality`` / ``metrics_skipped`` /
  ``attack_skipped``); lower on empty cards.
- ``evidence_completeness`` — evidence_refs present; coverage for E/S;
  checks dict for Integrity.

Combine: **geometric mean** of the three factors → dimension confidence.
Overall: **geometric mean** of the five dimension confidences
(``method = "geometric_mean_v1"``).

Factors are floored at ``_FACTOR_FLOOR`` (0.1) so a single zero signal does
not collapse the geometric mean to exactly 0; everything is clamped to [0, 1].

Confidence is an **evidence-strength signal, not correctness**. Calibration
is an open research question (RQ5) — hence ``proposed_calibration: true``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from app.db.enums import FriesDimension

CONFIDENCE_METHOD = "geometric_mean_v1"
CONFIDENCE_NOTE = "Evidence strength only — not correctness or O/S/D"

_FACTOR_FLOOR = 0.1

_FAIRNESS_SKIP_FLAGS = {
    "metrics_skipped",
    "unsupported_modality",
    "dataset_load_failed",
    "predictor_failed",
    "missing_sensitive_attribute",
}
_ROBUSTNESS_SKIP_FLAGS = {
    "attack_skipped",
    "unsupported_modality",
    "dataset_load_failed",
    "model_load_failed",
}


class ConfidenceFactors(BaseModel):
    data_quality: float = Field(ge=0.0, le=1.0)
    probe_reliability: float = Field(ge=0.0, le=1.0)
    evidence_completeness: float = Field(ge=0.0, le=1.0)
    combined: float = Field(ge=0.0, le=1.0)


class DimensionConfidence(BaseModel):
    dimension: str
    confidence: float = Field(ge=0.0, le=1.0)
    factors: ConfidenceFactors
    flags: list[str] = Field(default_factory=list)


class ConfidenceSummary(BaseModel):
    overall: float = Field(ge=0.0, le=1.0)
    by_dimension: dict[str, float]
    method: str = CONFIDENCE_METHOD
    proposed_calibration: bool = True
    note: str = CONFIDENCE_NOTE


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _factor(value: float) -> float:
    """Clamp a factor to [_FACTOR_FLOOR, 1.0] to avoid degenerate zeros."""
    return _clamp(value, _FACTOR_FLOOR, 1.0)


def geometric_mean(values: Sequence[float]) -> float:
    """Geometric mean clamped to [0, 1]; empty input → 0.0."""
    items = [_clamp(float(v)) for v in values]
    if not items:
        return 0.0
    if any(v == 0.0 for v in items):
        return 0.0
    log_sum = sum(math.log(v) for v in items)
    return _clamp(math.exp(log_sum / len(items)))


def _ratio(metric_values: dict[str, Any], key: str) -> float | None:
    raw = metric_values.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return _clamp(float(raw))


def _fairness_factors(
    metric_values: dict[str, Any], flags: list[str], has_evidence: bool
) -> tuple[float, float, float]:
    dp = metric_values.get("demographic_parity_difference")
    computed = dp is not None
    skip = bool(_FAIRNESS_SKIP_FLAGS & set(flags)) or not computed

    if not computed:
        data_quality = 0.35
    elif "insufficient_slice_size" in flags:
        data_quality = 0.55
    else:
        observed = metric_values.get("min_group_n_observed")
        threshold = metric_values.get("min_group_n")
        if (
            isinstance(observed, (int, float))
            and isinstance(threshold, (int, float))
            and observed < threshold
        ):
            data_quality = 0.55
        else:
            data_quality = 1.0

    probe_reliability = 0.45 if skip else 1.0

    evidence = 1.0 if has_evidence else 0.2
    if has_evidence and metric_values.get("needs_human_review") is True:
        evidence = 0.95
    return data_quality, probe_reliability, evidence


def _robustness_factors(
    metric_values: dict[str, Any], flags: list[str], has_evidence: bool
) -> tuple[float, float, float]:
    clean = metric_values.get("clean_accuracy")
    computed = clean is not None
    skip = bool(_ROBUSTNESS_SKIP_FLAGS & set(flags)) or not computed

    n_samples = metric_values.get("n_samples")
    if not computed or not isinstance(n_samples, (int, float)):
        data_quality = 0.4
    elif n_samples >= 64:
        data_quality = 1.0
    elif n_samples >= 16:
        data_quality = 0.7
    else:
        data_quality = 0.4

    probe_reliability = 0.45 if skip else 1.0
    evidence = 1.0 if has_evidence else 0.2
    return data_quality, probe_reliability, evidence


def _integrity_factors(
    metric_values: dict[str, Any], flags: list[str], has_evidence: bool
) -> tuple[float, float, float]:
    checks = metric_values.get("checks")
    pass_count = metric_values.get("pass_count")
    fail_count = metric_values.get("fail_count")
    if isinstance(pass_count, int) and isinstance(fail_count, int):
        total = pass_count + fail_count
        data_quality = pass_count / total if total else 0.5
    elif isinstance(checks, dict) and checks:
        passes = sum(1 for c in checks.values() if isinstance(c, dict) and c.get("pass"))
        data_quality = passes / len(checks)
    else:
        data_quality = 0.5

    probe_reliability = 1.0  # metadata audit always runs its intended path
    if not has_evidence:
        evidence = 0.2
    elif isinstance(checks, dict) and checks:
        evidence = 1.0
    else:
        evidence = 0.8
    return data_quality, probe_reliability, evidence


def _card_coverage_factors(
    metric_values: dict[str, Any],
    flags: list[str],
    has_evidence: bool,
    *,
    high_impact_key: str | None,
) -> tuple[float, float, float]:
    """Shared Explainability/Safety card-coverage factor model."""
    coverage = _ratio(metric_values, "coverage_ratio")
    card_chars = metric_values.get("card_chars")
    empty = "empty_card" in flags or card_chars == 0

    data_quality = 0.0 if empty else (coverage if coverage is not None else 0.5)

    if empty:
        probe_reliability = 0.4
    elif high_impact_key is not None:
        high_impact = bool(metric_values.get(high_impact_key))
        if high_impact and (coverage is None or coverage < 1.0):
            probe_reliability = 0.5
        else:
            probe_reliability = 1.0
    elif coverage is not None and coverage < 0.4:
        probe_reliability = 0.6
    else:
        probe_reliability = 1.0

    if not has_evidence:
        evidence = 0.2
    else:
        evidence = 0.6 + 0.4 * (coverage if coverage is not None else 0.0)
    return data_quality, probe_reliability, evidence


def refine(
    dimension: FriesDimension,
    *,
    metric_values: dict[str, Any],
    flags: list[str] | None = None,
    evidence_refs: list[Any] | None = None,
) -> DimensionConfidence:
    """Compute factors + combined confidence for one probe result.

    Works from ``metric_values`` alone when ``flags`` are unavailable
    (e.g. re-deriving from persisted ``probe_results`` rows).
    """
    flag_list = list(flags or [])
    has_evidence = bool(evidence_refs)

    if dimension == FriesDimension.FAIRNESS:
        raw = _fairness_factors(metric_values, flag_list, has_evidence)
    elif dimension == FriesDimension.ROBUSTNESS:
        raw = _robustness_factors(metric_values, flag_list, has_evidence)
    elif dimension == FriesDimension.INTEGRITY:
        raw = _integrity_factors(metric_values, flag_list, has_evidence)
    elif dimension == FriesDimension.EXPLAINABILITY:
        raw = _card_coverage_factors(
            metric_values, flag_list, has_evidence, high_impact_key=None
        )
    else:
        raw = _card_coverage_factors(
            metric_values,
            flag_list,
            has_evidence,
            high_impact_key="high_impact_claims",
        )

    data_quality = round(_factor(raw[0]), 4)
    probe_reliability = round(_factor(raw[1]), 4)
    evidence_completeness = round(_factor(raw[2]), 4)
    combined = round(
        geometric_mean([data_quality, probe_reliability, evidence_completeness]), 4
    )
    return DimensionConfidence(
        dimension=dimension.value,
        confidence=combined,
        factors=ConfidenceFactors(
            data_quality=data_quality,
            probe_reliability=probe_reliability,
            evidence_completeness=evidence_completeness,
            combined=combined,
        ),
        flags=flag_list,
    )


def summarize(
    rows: Sequence[tuple[FriesDimension, float | None, dict[str, Any]]],
) -> ConfidenceSummary:
    """Aggregate persisted probe rows → overall + per-dimension confidences.

    Uses the stored ``confidence`` when present (engine wrote it at persist
    time); otherwise re-derives from ``metric_values`` (flags unavailable).
    """
    by_dimension: dict[str, float] = {}
    for dimension, confidence, metric_values in rows:
        if confidence is not None:
            by_dimension[dimension.value] = round(_clamp(float(confidence)), 4)
        else:
            by_dimension[dimension.value] = refine(
                dimension,
                metric_values=metric_values or {},
                evidence_refs=[True],  # rows always persisted with ≥1 ref
            ).confidence
    overall = round(geometric_mean(list(by_dimension.values())), 4)
    return ConfidenceSummary(overall=overall, by_dimension=by_dimension)
