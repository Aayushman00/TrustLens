"""Confidence Engine (Phase 15) — pure factor model, no DB/S3.

Each FRIES dimension gets three factors in [0, 1]:

- ``data_quality`` — input/data adequacy (fairness group sizes, robustness
  ``n_evaluated`` / ``n_samples``, integrity identity snapshot richness).
  Explainability and Safety v1 do **not** use ``coverage_ratio`` for this factor.
- ``probe_reliability`` — did the intended path run? 1.0 for a full run;
  ~0.4–0.6 on skips / insufficient evidence / mapping blocked.
- ``evidence_completeness`` — evidence_refs present; checks dict for I/E/S;
  robustness uses drop CI / mapping state (not card coverage).

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

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION

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
    by_dimension: dict[str, float | None]
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
    gap = metric_values.get("subgroup_worst_group_acc_gap")
    computed = (
        dp is not None and dp != "NOT_APPLICABLE"
    ) or gap is not None
    skip = bool(_FAIRNESS_SKIP_FLAGS & set(flags)) or not computed
    probe_status = metric_values.get("probe_status")
    reliability = metric_values.get("reliability")
    failed_gates = (
        reliability.get("failed_gates") or []
        if isinstance(reliability, dict)
        else []
    )
    reliability_blocked = (
        metric_values.get("aspect_scoring") == "mapping_blocked"
        or "wide_ci" in flags
        or "G-FAIR-CI-WIDE" in failed_gates
    )
    if probe_status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value:
        probe_reliability = 0.45
    elif skip:
        probe_reliability = 0.45
    elif reliability_blocked:
        probe_reliability = 0.45
    else:
        probe_reliability = 1.0

    if not computed:
        data_quality = 0.35
    elif "insufficient_slice_size" in flags or "insufficient_total_n" in flags:
        data_quality = 0.55
    elif "insufficient_group_n" in flags or "thin_groups_excluded" in flags:
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

    probe_status = metric_values.get("probe_status")
    reliability = metric_values.get("reliability")
    failed_gates = (
        reliability.get("failed_gates") or []
        if isinstance(reliability, dict)
        else []
    )
    aspect_scoring = metric_values.get("aspect_scoring")
    reliability_blocked = (
        aspect_scoring == "mapping_blocked"
        or "wide_ci" in flags
        or "uninformative_robustness" in flags
        or "domain_mismatch" in flags
        or "G-ROB-CI-WIDE" in failed_gates
        or "G-ROB-CLEAN-FLOOR" in failed_gates
    )

    if probe_status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value:
        probe_reliability = 0.45
    elif skip:
        probe_reliability = 0.45
    elif reliability_blocked:
        probe_reliability = 0.45
    else:
        probe_reliability = 1.0

    n_evaluated = metric_values.get("n_evaluated") or metric_values.get("n_samples")
    if not computed or not isinstance(n_evaluated, (int, float)):
        data_quality = 0.4
    elif n_evaluated >= 200:
        data_quality = 1.0
    elif n_evaluated >= 100:
        data_quality = 0.85
    elif n_evaluated >= 16:
        data_quality = 0.7
    else:
        data_quality = 0.4

    uncertainty = metric_values.get("uncertainty")
    drop_ci = (
        uncertainty.get("accuracy_drop")
        if isinstance(uncertainty, dict)
        else None
    )
    has_drop_ci = (
        isinstance(drop_ci, dict)
        and drop_ci.get("ci_lower") is not None
        and drop_ci.get("ci_upper") is not None
    )

    if not has_evidence:
        evidence = 0.2
    elif not computed:
        evidence = 0.2
    elif reliability_blocked or not has_drop_ci:
        evidence = 0.6
    elif aspect_scoring == "no_material_risk" and has_drop_ci:
        evidence = 1.0
    elif aspect_scoring == "scored_risk" and has_drop_ci:
        evidence = 1.0
    else:
        evidence = 0.8 if has_drop_ci else 0.6

    return data_quality, probe_reliability, evidence


def _integrity_factors(
    metric_values: dict[str, Any], flags: list[str], has_evidence: bool
) -> tuple[float, float, float]:
    probe_status = metric_values.get("probe_status")

    if probe_status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value:
        probe_reliability = 0.45
        data_quality = 0.35
    elif probe_status == ProbeEvaluationStatus.FAILED.value:
        probe_reliability = 0.45
        data_quality = 0.35
    else:
        probe_reliability = 1.0
        identity = metric_values.get("identity")
        if isinstance(identity, dict):
            has_files = bool(identity.get("hub_files"))
            revision_sha_like = identity.get("sha_like") is True
            disclosure = metric_values.get("disclosure")
            has_card = (
                isinstance(disclosure, dict) and disclosure.get("card_present") is True
            )
            if has_files or revision_sha_like:
                data_quality = 1.0
            elif has_card or identity.get("revision"):
                data_quality = 0.55
            else:
                data_quality = 0.55
        else:
            data_quality = 0.55

    if not has_evidence:
        evidence = 0.2
    elif not isinstance(metric_values.get("checks"), dict) or not metric_values.get(
        "checks"
    ):
        evidence = 0.2
    else:
        identity = metric_values.get("identity")
        hash_comparison = None
        if isinstance(identity, dict):
            hash_comparison = identity.get("hash_comparison")
        reliability = metric_values.get("reliability")
        failed_gates = (
            reliability.get("failed_gates") or []
            if isinstance(reliability, dict)
            else []
        )
        hash_unverified = hash_comparison == "not_performed" or any(
            gate in failed_gates
            for gate in (
                "I-INT-HASH-UNVERIFIED",
                "G-INT-HASH-REF-MISSING",
                "G-INT-HASH-LOCAL-MISSING",
            )
        )
        if hash_unverified and probe_status == ProbeEvaluationStatus.EVALUATED.value:
            evidence = 0.85
        else:
            evidence = 1.0

    return data_quality, probe_reliability, evidence


def _explainability_factors(
    metric_values: dict[str, Any], flags: list[str], has_evidence: bool
) -> tuple[float, float, float]:
    """Explainability v1 — provisional uncalibrated evidence-strength weights.

    Not calibrated probabilities and not a function of coverage_ratio.
    """
    probe_status = metric_values.get("probe_status")

    if probe_status in (
        ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
        ProbeEvaluationStatus.FAILED.value,
    ):
        probe_reliability = 0.45
        data_quality = 0.35
    else:
        probe_reliability = 1.0
        data_quality = 1.0

    if not has_evidence:
        evidence = 0.2
    elif not isinstance(metric_values.get("checks"), dict) or not metric_values.get(
        "checks"
    ):
        evidence = 0.2
    else:
        evidence = 1.0

    return data_quality, probe_reliability, evidence


def _safety_factors(
    metric_values: dict[str, Any], flags: list[str], has_evidence: bool
) -> tuple[float, float, float]:
    """Safety v1 — provisional uncalibrated evidence-strength weights.

    Not calibrated probabilities and not a function of coverage_ratio or
    high_impact_claims (documentation metadata flags).
    """
    probe_status = metric_values.get("probe_status")

    if probe_status in (
        ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
        ProbeEvaluationStatus.FAILED.value,
    ):
        probe_reliability = 0.45
        data_quality = 0.35
    else:
        probe_reliability = 1.0
        data_quality = 1.0

    if not has_evidence:
        evidence = 0.2
    elif not isinstance(metric_values.get("checks"), dict) or not metric_values.get(
        "checks"
    ):
        evidence = 0.2
    else:
        evidence = 1.0

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
        raw = _explainability_factors(metric_values, flag_list, has_evidence)
    elif dimension == FriesDimension.SAFETY:
        raw = _safety_factors(metric_values, flag_list, has_evidence)
    else:
        raise ValueError(f"unsupported dimension for confidence refine: {dimension}")

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
    *,
    methodology_version: str = LEGACY_METHODOLOGY_VERSION,
) -> ConfidenceSummary:
    """Aggregate persisted probe rows → overall + per-dimension confidences.

    Uses the stored ``confidence`` when present (engine wrote it at persist
    time); otherwise re-derives from ``metric_values`` (flags unavailable).

    When ``methodology_version != LEGACY_METHODOLOGY_VERSION``, rows whose
    ``metric_values["probe_status"] == ProbeEvaluationStatus.NOT_APPLICABLE.value``
    (i.e. the persisted string ``"NOT_APPLICABLE"``) are excluded from
    the geometric mean (still present in ``by_dimension`` for display, valued
    ``None``). When ``methodology_version == LEGACY_METHODOLOGY_VERSION``,
    behavior is byte-for-byte unchanged from before this parameter existed —
    NOT_APPLICABLE rows are still folded into ``overall`` at their stored
    confidence, forever.
    """
    by_dimension: dict[str, float | None] = {}
    included_values: list[float] = []
    for dimension, confidence, metric_values in rows:
        metric_values = metric_values or {}
        is_not_applicable = (
            metric_values.get("probe_status") == ProbeEvaluationStatus.NOT_APPLICABLE.value
        )
        if confidence is not None:
            value = round(_clamp(float(confidence)), 4)
        else:
            value = refine(
                dimension,
                metric_values=metric_values,
                evidence_refs=[True],  # rows always persisted with ≥1 ref
            ).confidence

        exclude = is_not_applicable and methodology_version != LEGACY_METHODOLOGY_VERSION
        by_dimension[dimension.value] = None if exclude else value
        if not exclude:
            included_values.append(value)

    overall = round(geometric_mean(included_values), 4) if included_values else 0.0
    return ConfidenceSummary(overall=overall, by_dimension=by_dimension)
