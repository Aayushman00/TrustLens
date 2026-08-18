"""Explainability probe — model-card section coverage (Phase 13).

Metadata-only rule-based checklist. Emits objective documentation coverage as
evidence — does **not** score interpretability quality, O/S/D, or product FRIES.
"""

from __future__ import annotations

import json
from typing import Any

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.explainability_card import (
    REQUIRED_SECTIONS,
    coverage_ratio,
    detect_contradictions,
    detect_required_sections,
    sections_present_count,
)
from app.storage.evidence_store import EvidenceStoreError

_NOTE = (
    "Rule-based documentation coverage only — not O/S/D or interpretability quality"
)


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


def _confidence(
    *,
    card_chars: int,
    coverage: float,
    heading_matches: int,
) -> float:
    if card_chars == 0:
        return 0.35
    if heading_matches == 0:
        return 0.5
    if coverage >= 1.0 and card_chars >= 1500:
        return 0.9
    if coverage >= 0.6:
        return 0.8
    return 0.5


class ExplainabilityProbe:
    """Audit model-card section coverage and light consistency contradictions."""

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.EXPLAINABILITY

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        meta = ctx.model_metadata or {}
        card_text = _as_str(meta.get("card_text")) or ""
        card_data = _card_data_dict(meta)
        card_chars = len(card_text)

        all_sections = detect_required_sections(card_text, card_data)
        required = {k: all_sections[k] for k in REQUIRED_SECTIONS}
        present_count = sections_present_count(all_sections)
        ratio = coverage_ratio(all_sections)
        contradictions = detect_contradictions(
            card_text, meta, section_results=all_sections
        )

        flags: list[str] = []
        for key in REQUIRED_SECTIONS:
            if not required[key]["present"]:
                flags.append(f"missing_{key}")
        for item in contradictions:
            if item not in flags:
                flags.append(item)
        if ratio < 0.6:
            flags.append("needs_human_review")

        heading_matches = sum(
            1
            for key in REQUIRED_SECTIONS
            if required[key]["present"]
            and not str(required[key].get("matched_heading") or "").startswith(
                "card_data."
            )
        )
        confidence = _confidence(
            card_chars=card_chars,
            coverage=ratio,
            heading_matches=heading_matches,
        )

        metric_values: dict[str, Any] = {
            "sections": required,
            "bonus_sections": {
                k: all_sections[k]
                for k in ("architecture", "citation", "examples")
                if k in all_sections
            },
            "sections_present": present_count,
            "sections_required": len(REQUIRED_SECTIONS),
            "coverage_ratio": ratio,
            "contradictions": contradictions,
            "card_chars": card_chars,
            "proposed_mapping": False,
            "note": _NOTE,
        }

        artifact = {
            "probe": "explainability",
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "checklist": {
                "sections": required,
                "sections_present": present_count,
                "sections_required": len(REQUIRED_SECTIONS),
                "coverage_ratio": ratio,
            },
            "contradictions": contradictions,
            "flags": flags,
            "proposed_mapping": False,
            "note": _NOTE,
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
            metric_values=metric_values,
            confidence=confidence,
            evidence_refs=[ref],
            flags=flags,
        )
