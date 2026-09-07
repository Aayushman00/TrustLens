"""Explainability evaluation logic (tl-explainability-v1.0) — pure functions, stdlib only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.enums import ProbeEvaluationStatus
from app.probes.explainability_card import (
    BONUS_SECTIONS,
    REQUIRED_SECTIONS,
    coverage_ratio,
    detect_contradictions,
    detect_required_sections,
    sections_present_count,
)
from app.probes.explainability_stats import (
    ASPECT_NO_MATERIAL_RISK,
    ASPECT_NOT_SCORED,
    ASPECT_RISK_DETECTED,
    CLAIM_NOT_ESTABLISHED,
    CLAIM_SUPPORTED,
    G_CARD_EMPTY,
    LIMITATIONS,
    RISK_DOC_CONTRADICTION,
    RISK_DOC_INCOMPLETE,
)

_CONTRADICTION_RISK_FLAGS = frozenset(
    {
        "open_claim_vs_restrictive_license",
        "no_limitations_but_production_claim",
    }
)


@dataclass
class ExplainabilityEvalResult:
    status: ProbeEvaluationStatus
    status_reason: str | None
    aspect_scoring: str
    scored_risk_id: None
    risks_triggered: list[str]
    flags: list[str]
    checks: dict[str, dict[str, Any]]
    sections: dict[str, dict[str, Any]]
    bonus_sections: dict[str, dict[str, Any]]
    sections_present: int
    sections_required: int
    coverage_ratio: float
    card_chars: int
    contradictions: list[str]
    claims: dict[str, dict[str, str]]
    claim_boundary: dict[str, str]
    reliability: dict[str, Any]
    limitations: list[str]
    confidence: float = 0.5


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


def evaluate_explainability(*, model_metadata: dict[str, Any]) -> ExplainabilityEvalResult:
    """Evaluate documentation/transparency from Hub model-card metadata."""
    meta = model_metadata or {}
    card_text = _as_str(meta.get("card_text")) or ""
    card_data = _card_data_dict(meta)
    card_chars = len(card_text)

    if card_chars == 0:
        return ExplainabilityEvalResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason="no model card text — cannot evaluate documentation",
            aspect_scoring=ASPECT_NOT_SCORED,
            scored_risk_id=None,
            risks_triggered=[],
            flags=["empty_card"],
            checks={},
            sections={},
            bonus_sections={},
            sections_present=0,
            sections_required=len(REQUIRED_SECTIONS),
            coverage_ratio=0.0,
            card_chars=0,
            contradictions=["empty_card"],
            claims={
                "documentation_completeness": {
                    "status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
                    "reason": G_CARD_EMPTY,
                },
            },
            claim_boundary={
                "supported": CLAIM_SUPPORTED,
                "not_established": CLAIM_NOT_ESTABLISHED,
            },
            reliability={"gates_passed": False, "failed_gates": [G_CARD_EMPTY]},
            limitations=list(LIMITATIONS),
        )

    all_sections = detect_required_sections(card_text, card_data)
    required = {key: all_sections[key] for key in REQUIRED_SECTIONS}
    bonus = {
        key: all_sections[key]
        for key in BONUS_SECTIONS
        if key in all_sections
    }
    present_count = sections_present_count(all_sections)
    ratio = coverage_ratio(all_sections)
    contradictions = detect_contradictions(
        card_text, meta, section_results=all_sections
    )

    flags: list[str] = []
    risks: list[str] = []
    checks: dict[str, dict[str, Any]] = {}

    for key in REQUIRED_SECTIONS:
        section = required[key]
        present = bool(section.get("present"))
        if not present:
            flags.append(f"missing_{key}")
        checks[key] = {
            "pass": present,
            "detail": section.get("matched_heading") or "missing or trivial body",
        }

    checks["documentation_completeness"] = {
        "pass": present_count == len(REQUIRED_SECTIONS),
        "detail": f"{present_count}/{len(REQUIRED_SECTIONS)} required sections present",
        "sections_present": present_count,
        "sections_required": len(REQUIRED_SECTIONS),
        "coverage_ratio": ratio,
    }

    if present_count < len(REQUIRED_SECTIONS):
        risks.append(RISK_DOC_INCOMPLETE)

    for item in contradictions:
        if item not in flags:
            flags.append(item)

    if any(flag in _CONTRADICTION_RISK_FLAGS for flag in contradictions):
        risks.append(RISK_DOC_CONTRADICTION)
        checks["documentation_contradiction"] = {
            "pass": False,
            "detail": ", ".join(
                flag
                for flag in contradictions
                if flag in _CONTRADICTION_RISK_FLAGS
            ),
        }
    else:
        checks["documentation_contradiction"] = {
            "pass": True,
            "detail": "no keyword-level contradiction flags",
        }

    if ratio < 0.6:
        flags.append("needs_human_review")

    if risks:
        aspect_scoring = ASPECT_RISK_DETECTED
    else:
        aspect_scoring = ASPECT_NO_MATERIAL_RISK

    doc_status = ProbeEvaluationStatus.EVALUATED.value
    doc_reason = (
        f"documentation checklist evaluated; {present_count}/{len(REQUIRED_SECTIONS)} "
        "required sections present"
    )
    if RISK_DOC_INCOMPLETE in risks:
        doc_reason = (
            "one or more required documentation sections absent or trivial "
            f"({present_count}/{len(REQUIRED_SECTIONS)} present)"
        )

    return ExplainabilityEvalResult(
        status=ProbeEvaluationStatus.EVALUATED,
        status_reason=None,
        aspect_scoring=aspect_scoring,
        scored_risk_id=None,
        risks_triggered=risks,
        flags=flags,
        checks=checks,
        sections=required,
        bonus_sections=bonus,
        sections_present=present_count,
        sections_required=len(REQUIRED_SECTIONS),
        coverage_ratio=ratio,
        card_chars=card_chars,
        contradictions=contradictions,
        claims={
            "documentation_completeness": {
                "status": doc_status,
                "reason": doc_reason,
            },
            "documentation_contradiction": {
                "status": doc_status,
                "reason": (
                    "keyword-level contradiction flags recorded"
                    if RISK_DOC_CONTRADICTION in risks
                    else "no contradiction risk triggered"
                ),
            },
        },
        claim_boundary={
            "supported": CLAIM_SUPPORTED,
            "not_established": CLAIM_NOT_ESTABLISHED,
        },
        reliability={"gates_passed": True, "failed_gates": []},
        limitations=list(LIMITATIONS),
    )
