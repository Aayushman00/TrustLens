"""Safety probe — safety-governance disclosure (tl-safety-v1.0).

Metadata-only disclosure checklist and lexical phrase documentation flags.
Emits Layer A evidence with named S-GOV-* detections — does **not** write final
FRIES, O/S/D, or FRIES2 caps.
"""

from __future__ import annotations

import json
from typing import Any

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.safety_eval import evaluate_safety
from app.probes.safety_stats import METHODOLOGY_BASIS, METHODOLOGY_VERSION, NOTE
from app.storage.evidence_store import EvidenceStoreError


class SafetyProbe:
    """Audit model-card safety disclosures and lexical documentation phrase flags."""

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.SAFETY

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        result = evaluate_safety(model_metadata=ctx.model_metadata or {})
        # Part 1: cite exactly which pinned-revision documentation evidence
        # this Track 1 governance/documentation checklist read — never a new
        # methodology input, purely a provenance pointer already resolved at
        # import time (app/documentation/evidence.py). None when the model
        # wasn't imported from HF or the card fetch failed.
        documentation_source = (ctx.model_metadata or {}).get("documentation_evidence")

        metrics: dict[str, Any] = {
            "methodology_version": METHODOLOGY_VERSION,
            "methodology_basis": METHODOLOGY_BASIS,
            "documentation_source": documentation_source,
            "checks": result.checks,
            "required_checks": result.required_checks,
            "bonus_checks": result.bonus_checks,
            "checks_present": result.checks_present,
            "checks_required": result.checks_required,
            "coverage_ratio": result.coverage_ratio,
            "card_chars": result.card_chars,
            "high_impact_claims": result.high_impact_claims,
            "claims": result.claims,
            "claim_boundary": result.claim_boundary,
            "aspect_scoring": result.aspect_scoring,
            "scored_risk_id": result.scored_risk_id,
            "risks_triggered": result.risks_triggered,
            "reliability": result.reliability,
            "uncertainty": result.uncertainty,
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
            "probe": "safety",
            "dimension": FriesDimension.SAFETY.value,
            "methodology_version": METHODOLOGY_VERSION,
            "methodology_basis": METHODOLOGY_BASIS,
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "status": result.status.value,
            "status_reason": result.status_reason,
            "aspect_scoring": result.aspect_scoring,
            "scored_risk_id": result.scored_risk_id,
            "risks_triggered": result.risks_triggered,
            "documentation_source": documentation_source,
            "checks": result.checks,
            "required_checks": result.required_checks,
            "bonus_checks": result.bonus_checks,
            "checks_present": result.checks_present,
            "checks_required": result.checks_required,
            "coverage_ratio": result.coverage_ratio,
            "card_chars": result.card_chars,
            "high_impact_claims": result.high_impact_claims,
            "claims": result.claims,
            "claim_boundary": result.claim_boundary,
            "reliability": result.reliability,
            "uncertainty": result.uncertainty,
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
                probe_name="safety",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise

        return ProbeOutput(
            dimension=FriesDimension.SAFETY,
            metric_values=metrics,
            confidence=result.confidence,
            evidence_refs=[ref],
            flags=result.flags,
            status=result.status,
            status_reason=result.status_reason,
        )
