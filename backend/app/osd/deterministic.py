"""DeterministicOSDMapper — consumer/representation layer over Layer A probes.

Reads persisted probe snapshots only. Does **not** recompute metrics, CIs,
gates, confidence, or risk triggers. Under v1.0 rules every aspect has
``O=None`` (no approved mapping), ``S=None`` (human-controlled only),
``D=None`` (unavailable).
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.osd.base import (
    METHODOLOGY_STATUS_DETERMINISTIC,
    AgentContext,
    AgentResult,
    AspectOSD,
    ProbeSnapshot,
)

logger = logging.getLogger("trustlens.osd")

_ASSESSMENT_ENGINE = "deterministic"
_O_SOURCE_UNAVAILABLE = "unavailable"
_D_SOURCE_UNAVAILABLE = "unavailable"
_NO_APPROVED_MAPPING = "no_approved_mapping"

_DEFAULT_CONFIDENCE = 0.5

_PROBE_METADATA_KEYS = (
    "aspect_scoring",
    "scored_risk_id",
    "risks_triggered",
    "failed_gates",
    "flags",
    "status",
    "status_reason",
    "gap",
    "gap_ci_lower",
    "gap_ci_upper",
    "demographic_parity_difference",
    "equalized_odds_difference",
    "min_group_n",
    "min_group_n_observed",
    "clean_accuracy",
    "robust_accuracy",
    "degradation_ratio",
    "relative_degradation",
    "accuracy_drop",
    "drop_ci_lower",
    "drop_ci_upper",
    "uncertainty",
    "reliability",
    "limitations",
    "n_evaluated",
    "n_requested",
    "perturbation_coverage",
    "pass_count",
    "fail_count",
    "coverage_ratio",
    "card_chars",
    "sections",
    "bonus_sections",
    "sections_present",
    "sections_required",
    "contradictions",
    "high_impact_claims",
    "probe_status",
    "methodology_version",
    "methodology_basis",
    "claim_boundary",
    "identity",
    "disclosure",
    "claims",
    "checks",
    "bonus_checks",
    "checks_present",
    "checks_required",
    "required_checks",
)


def resolve_assessment_engine(probe_config: dict[str, Any] | None) -> str:
    """Return ``deterministic`` (default) or ``legacy_heuristic``.

    Only the top-level ``assessment_engine`` field is honored. ``extra`` cannot
    select the engine (including the historical ``heuristic`` alias).
    """
    cfg = probe_config or {}
    engine = cfg.get("assessment_engine")
    if engine == "legacy_heuristic":
        return "legacy_heuristic"
    return "deterministic"


def _status_from_metrics(m: dict[str, Any]) -> ProbeEvaluationStatus | None:
    raw = m.get("probe_status")
    if not isinstance(raw, str):
        return None
    try:
        return ProbeEvaluationStatus(raw)
    except ValueError:
        return None


def _extract_probe_metadata(metric_values: dict[str, Any]) -> dict[str, Any]:
    """Copy probe-owned fields into OSD representation metadata (read-only)."""
    meta: dict[str, Any] = {}
    for key in _PROBE_METADATA_KEYS:
        if key in metric_values:
            meta[key] = metric_values[key]
    return meta


def _build_rationale(dimension: FriesDimension, metadata: dict[str, Any]) -> str:
    parts = [
        f"{dimension.value}: O unavailable (no approved+validated mapping); "
        "S human-controlled; D unavailable."
    ]
    scored = metadata.get("scored_risk_id")
    if scored:
        parts.append(f"Probe reported named risk {scored}.")
    aspect_scoring = metadata.get("aspect_scoring")
    if aspect_scoring:
        parts.append(f"aspect_scoring={aspect_scoring}.")
    status = metadata.get("status") or metadata.get("probe_status")
    if status:
        parts.append(f"probe status={status}.")
    return " ".join(parts)


class DeterministicOSDMapper:
    """v1.0 default mapper — abstains O/S/D; copies probe evidence metadata only."""

    def propose(self, ctx: AgentContext) -> AgentResult:
        by_dimension: dict[FriesDimension, ProbeSnapshot] = {
            snap.dimension: snap for snap in ctx.probe_results
        }
        aspects: list[AspectOSD] = []
        for dimension in FriesDimension:
            snap = by_dimension.get(dimension)
            if snap is None:
                aspects.append(
                    AspectOSD(
                        aspect=dimension,
                        O=None,
                        S=None,
                        D=None,
                        O_source=_O_SOURCE_UNAVAILABLE,
                        S_source=None,
                        D_source=_D_SOURCE_UNAVAILABLE,
                        confidence=0.2,
                        rationale=(
                            f"{dimension.value}: no probe result; O/S/D unavailable."
                        ),
                        status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
                        osd_metadata={"mapping_reason": _NO_APPROVED_MAPPING},
                    )
                )
                continue
            metric_values = snap.metric_values or {}
            metadata = _extract_probe_metadata(metric_values)
            metadata["mapping_reason"] = _NO_APPROVED_MAPPING
            probe_status = _status_from_metrics(metric_values)
            aspects.append(
                AspectOSD(
                    aspect=dimension,
                    O=None,
                    S=None,
                    D=None,
                    O_source=_O_SOURCE_UNAVAILABLE,
                    S_source=None,
                    D_source=_D_SOURCE_UNAVAILABLE,
                    confidence=round(
                        float(
                            snap.confidence
                            if snap.confidence is not None
                            else _DEFAULT_CONFIDENCE
                        ),
                        4,
                    ),
                    rationale=_build_rationale(dimension, metadata),
                    evidence_refs=list(snap.evidence_refs or []),
                    status=probe_status or ProbeEvaluationStatus.EVALUATED,
                    osd_metadata=metadata,
                )
            )
        overall = round(sum(a.confidence for a in aspects) / len(aspects), 4)
        logger.info(
            "osd_deterministic_mapper evaluation_id=%s model_ref=%s overall_confidence=%s",
            ctx.evaluation_id,
            ctx.model_ref,
            overall,
        )
        return AgentResult(
            aspects=aspects,
            overall_confidence=overall,
            methodology_status=METHODOLOGY_STATUS_DETERMINISTIC,
            model_ref=ctx.model_ref,
            assessment_engine=_ASSESSMENT_ENGINE,
        )
