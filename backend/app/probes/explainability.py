"""Explainability probe — model-card documentation transparency (tl-explainability-v1.0).

Metadata-only section coverage and consistency flags. Emits Layer A evidence with
named E-DOC-* detections — does **not** write final FRIES or O/S/D.
"""

from __future__ import annotations

import json
from typing import Any

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.explainability_eval import evaluate_explainability
from app.probes.explainability_stats import METHODOLOGY_BASIS, METHODOLOGY_VERSION, NOTE
from app.storage.evidence_store import EvidenceStoreError


class ExplainabilityProbe:
    """Audit model-card documentation completeness and light consistency flags."""

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.EXPLAINABILITY

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        result = evaluate_explainability(model_metadata=ctx.model_metadata or {})

        metrics: dict[str, Any] = {
            "methodology_version": METHODOLOGY_VERSION,
            "methodology_basis": METHODOLOGY_BASIS,
            "sections": result.sections,
            "bonus_sections": result.bonus_sections,
            "sections_present": result.sections_present,
            "sections_required": result.sections_required,
            "coverage_ratio": result.coverage_ratio,
            "card_chars": result.card_chars,
            "contradictions": result.contradictions,
            "checks": result.checks,
            "claims": result.claims,
            "claim_boundary": result.claim_boundary,
            "aspect_scoring": result.aspect_scoring,
            "scored_risk_id": result.scored_risk_id,
            "risks_triggered": result.risks_triggered,
            "reliability": result.reliability,
            "limitations": result.limitations,
            "proposed_mapping": False,
            "osd_proposals": [],
            "note": NOTE,
            "status": result.status.value,
            "probe_status": result.status.value,
        }
        if result.status_reason:
            metrics["status_reason"] = result.status_reason
            metrics["probe_status_reason"] = result.status_reason

        artifact = {
            "probe": "explainability",
            "dimension": FriesDimension.EXPLAINABILITY.value,
            "methodology_version": METHODOLOGY_VERSION,
            "methodology_basis": METHODOLOGY_BASIS,
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "status": result.status.value,
            "status_reason": result.status_reason,
            "aspect_scoring": result.aspect_scoring,
            "scored_risk_id": result.scored_risk_id,
            "risks_triggered": result.risks_triggered,
            "sections": result.sections,
            "bonus_sections": result.bonus_sections,
            "sections_present": result.sections_present,
            "sections_required": result.sections_required,
            "coverage_ratio": result.coverage_ratio,
            "card_chars": result.card_chars,
            "contradictions": result.contradictions,
            "checks": result.checks,
            "claims": result.claims,
            "claim_boundary": result.claim_boundary,
            "reliability": result.reliability,
            "limitations": result.limitations,
            "flags": result.flags,
            "proposed_mapping": False,
            "osd_proposals": [],
            "note": NOTE,
        }
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
                probe_name="explainability",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise

        return ProbeOutput(
            dimension=FriesDimension.EXPLAINABILITY,
            metric_values=metrics,
            confidence=result.confidence,
            evidence_refs=[ref],
            flags=result.flags,
            status=result.status,
            status_reason=result.status_reason,
        )
