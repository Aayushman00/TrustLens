"""Integrity probe — Hub identity, provenance, and disclosure (tl-integrity-v1.2).

Metadata checks plus sha256 verification of the model artifact set: for Hub
models every weight file (single or sharded) against the Hub's LFS hashes, for
local folders the weights + loader files against an authoritative manifest
when one exists (integrity_artifact.py; docs/adr/0013-artifact-set-integrity.md
supersedes ADR 0012's "never reads weight bytes" for this check). Emits Layer A
evidence with named Integrity risks — does **not** write final FRIES or O/S/D.
"""

from __future__ import annotations

import json
from typing import Any

from app.adapters.hf_hub import HfHubModelAdapter
from app.db.enums import FriesDimension
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.integrity_artifact import hub_weight_hashes, local_integrity_extras, verify_local_artifacts
from app.probes.integrity_eval import evaluate_integrity, is_local_ref
from app.probes.integrity_stats import G_ARTIFACT_INCOMPLETE, METHODOLOGY_BASIS, METHODOLOGY_VERSION, NOTE
from app.storage.evidence_store import EvidenceStoreError


def _hf_token() -> str | None:
    try:
        from app.core.config import get_settings

        return get_settings().hf_token
    except Exception:  # noqa: BLE001 — public repos need no token
        return None


class IntegrityProbe:
    """Audit Hub metadata for identity recording and disclosure evidence."""

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.INTEGRITY

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        extra = ctx.probe_config.extra if ctx.probe_config.extra else {}
        integrity_extra = extra.get("integrity") if isinstance(extra.get("integrity"), dict) else {}

        live_files: list[str] | None = None
        live_files_error: str | None = None
        imported_files = (ctx.model_metadata or {}).get("files")
        if isinstance(imported_files, list) and imported_files:
            # Listing re-check (metadata only; weight bytes are verified separately
            # below) — re-resolves the Hub file *listing* at the same pinned revision to
            # detect post-import drift/tampering in the listing itself. Never
            # allowed to fail the whole probe: any error degrades to
            # "not_performed" in evaluate_integrity, same as an unsupplied hash.
            try:
                live_files = HfHubModelAdapter().list_current_files(ctx.model_ref, ctx.model_revision)
            except Exception as exc:  # noqa: BLE001 — degrade, never fail the probe
                live_files_error = str(exc)

        artifact_verification: dict[str, Any] = {"performed": False}
        supplied = integrity_extra.get("trusted_reference") or integrity_extra.get("local_artifact_hash")
        if not supplied:
            # Hub model: verify every cached weight file (single or sharded)
            # against the Hub's LFS sha256 at the pinned revision. Local folder:
            # hash the artifact set the loader reads and compare it with an
            # authoritative manifest when one exists. Any failure degrades to
            # not_performed (INSUFFICIENT), never a pass.
            try:
                if is_local_ref(ctx.model_ref):
                    operator_manifest = integrity_extra.get("artifact_manifest")
                    artifact_verification = verify_local_artifacts(
                        ctx.model_ref,
                        manifest=operator_manifest if isinstance(operator_manifest, dict) else None,
                    )
                    integrity_extra = {**integrity_extra, **local_integrity_extras(artifact_verification)}
                else:
                    hashes = hub_weight_hashes(ctx.model_ref, ctx.model_revision, _hf_token())
                    artifact_verification = hashes.pop(
                        "artifact_verification", {"performed": True, "file": hashes["file"]}
                    )
                    integrity_extra = {**integrity_extra, **hashes}
            except Exception as exc:  # noqa: BLE001 — degrade, never fail the probe
                artifact_verification = {"performed": False, "status": "UNVERIFIABLE", "error": str(exc)[:300]}

        result = evaluate_integrity(
            model_ref=ctx.model_ref,
            model_revision=ctx.model_revision,
            model_metadata=ctx.model_metadata or {},
            integrity_extra=integrity_extra,
            live_files=live_files,
            live_files_error=live_files_error,
        )
        if artifact_verification.get("status") == "INCOMPLETE":
            # An expected artifact is absent: the set cannot be verified. Not a
            # risk (no bytes were shown to differ) — an unverified gate.
            result.reliability = {
                "gates_passed": False,
                "failed_gates": [*result.reliability.get("failed_gates", []), G_ARTIFACT_INCOMPLETE],
            }

        metrics: dict[str, Any] = {
            "methodology_version": METHODOLOGY_VERSION,
            "methodology_basis": METHODOLOGY_BASIS,
            "artifact_verification": artifact_verification,
            "checks": result.checks,
            "identity": result.identity,
            "disclosure": result.disclosure,
            "claims": result.claims,
            "claim_boundary": result.claim_boundary,
            "aspect_scoring": result.aspect_scoring,
            "scored_risk_id": result.scored_risk_id,
            "risks_triggered": result.risks_triggered,
            "disclosure_gaps": result.disclosure_gaps,
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
            "disclosure_gaps": result.disclosure_gaps,
            "checks": result.checks,
            "identity": result.identity,
            "disclosure": result.disclosure,
            "claims": result.claims,
            "claim_boundary": result.claim_boundary,
            "reliability": result.reliability,
            "uncertainty": result.uncertainty,
            "limitations": result.limitations,
            "flags": result.flags,
            "artifact_verification": artifact_verification,
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
