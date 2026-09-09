"""Integrity probe — Hub identity, provenance, and disclosure (tl-integrity-v1.0).

Metadata-only: never downloads model weights. Emits Layer A evidence with named
Integrity risks — does **not** write final FRIES or O/S/D.
"""

from __future__ import annotations

import json
from typing import Any

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.integrity_eval import evaluate_integrity
from app.probes.integrity_stats import METHODOLOGY_BASIS, METHODOLOGY_VERSION, NOTE
from app.storage.evidence_store import EvidenceStoreError


class IntegrityProbe:
    """Audit Hub metadata for identity recording and disclosure evidence."""

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.INTEGRITY

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        extra = ctx.probe_config.extra if ctx.probe_config.extra else {}
        integrity_extra = extra.get("integrity") if isinstance(extra.get("integrity"), dict) else {}

        result = evaluate_integrity(
            model_ref=ctx.model_ref,
            model_revision=ctx.model_revision,
            model_metadata=ctx.model_metadata or {},
            integrity_extra=integrity_extra,
        )

        metrics: dict[str, Any] = {
            "methodology_version": METHODOLOGY_VERSION,
            "methodology_basis": METHODOLOGY_BASIS,
            "checks": result.checks,
            "identity": result.identity,
            "disclosure": result.disclosure,
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
            "probe": "integrity",
            "dimension": FriesDimension.INTEGRITY.value,
            "methodology_version": METHODOLOGY_VERSION,
            "methodology_basis": METHODOLOGY_BASIS,
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "model_revision": ctx.model_revision,
            "status": result.status.value,
            "status_reason": result.status_reason,
            "aspect_scoring": result.aspect_scoring,
            "scored_risk_id": result.scored_risk_id,
            "risks_triggered": result.risks_triggered,
            "checks": result.checks,
            "identity": result.identity,
            "disclosure": result.disclosure,
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
                probe_name="integrity",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise

        return ProbeOutput(
            dimension=FriesDimension.INTEGRITY,
            metric_values=metrics,
            confidence=result.confidence,
            evidence_refs=[ref],
            flags=result.flags,
            status=result.status,
            status_reason=result.status_reason,
        )
