"""Safety probe — mandatory disclosure checklist (Phase 14).

Metadata-only rule-based coverage. Emits evidence for Assisted-mode attention —
does **not** apply FRIES2 caps, O/S/D scores, or product FRIES mutation.
"""

from __future__ import annotations

import json
from typing import Any

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.safety_card import (
    SAFETY_BONUS,
    SAFETY_REQUIRED,
    checks_present_count,
    detect_high_impact_claims,
    detect_safety_checks,
    safety_coverage_ratio,
)
from app.storage.evidence_store import EvidenceStoreError

_NOTE = "Mandatory safety disclosure checklist — not O/S/D, not FRIES2 caps"


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value).strip() or None


def _card_data_dict(meta: dict[str, Any]) -> dict[str, Any]:
    raw = meta.get("card_data")
    return raw if isinstance(raw, dict) else {}


def _confidence(*, card_chars: int, coverage: float, high_impact: bool) -> float:
    if card_chars == 0:
        return 0.35
    value = 0.35 + 0.6 * coverage
    if high_impact and coverage < 1.0:
        value -= 0.15
    return round(max(0.0, min(1.0, value)), 3)


class SafetyProbe:
    """Audit model-card safety disclosures and high-impact deployment claims."""

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.SAFETY

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        meta = ctx.model_metadata or {}
        card_text = _as_str(meta.get("card_text")) or ""
        card_data = _card_data_dict(meta)
        card_chars = len(card_text)

        all_checks = detect_safety_checks(card_text, card_data)
        required = {k: all_checks[k] for k in SAFETY_REQUIRED}
        present_count = checks_present_count(all_checks)
        ratio = safety_coverage_ratio(all_checks)
        high_impact = detect_high_impact_claims(card_text)

        flags: list[str] = []
        if card_chars == 0:
            flags.append("empty_card")
        for key in SAFETY_REQUIRED:
            if not required[key]["present"]:
                flags.append(f"missing_{key}")
        if high_impact:
            flags.append("high_impact_deployment_claim")
        if ratio < 1.0 or high_impact:
            flags.append("needs_human_review")

        confidence = _confidence(
            card_chars=card_chars,
            coverage=ratio,
            high_impact=bool(high_impact),
        )

        metric_values: dict[str, Any] = {
            "checks": required,
            "bonus_checks": {k: all_checks[k] for k in SAFETY_BONUS if k in all_checks},
            "checks_present": present_count,
            "checks_required": len(SAFETY_REQUIRED),
            "coverage_ratio": ratio,
            "high_impact_claims": high_impact,
            "card_chars": card_chars,
            "proposed_mapping": False,
            "note": _NOTE,
        }

        artifact = {
            "probe": "safety",
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "checklist": {
                "checks": required,
                "checks_present": present_count,
                "checks_required": len(SAFETY_REQUIRED),
                "coverage_ratio": ratio,
            },
            "high_impact_claims": high_impact,
            "flags": flags,
            "proposed_mapping": False,
            "note": _NOTE,
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
            metric_values=metric_values,
            confidence=confidence,
            evidence_refs=[ref],
            flags=flags,
        )
