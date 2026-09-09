"""Safety evaluation logic (tl-safety-v1.0) — pure functions, stdlib only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.enums import ProbeEvaluationStatus
from app.probes.safety_card import (
    SAFETY_BONUS,
    SAFETY_REQUIRED,
    checks_present_count,
    detect_high_impact_claims,
    detect_safety_checks,
    safety_coverage_ratio,
)
from app.probes.safety_stats import (
    ASPECT_NO_MATERIAL_RISK,
    ASPECT_NOT_SCORED,
    ASPECT_RISK_DETECTED,
    CLAIM_NOT_ESTABLISHED,
    CLAIM_SUPPORTED,
    G_CARD_EMPTY,
    LIMITATIONS,
    RISK_GOV_DISCLOSURE_GAP,
)


@dataclass
class SafetyEvalResult:
    status: ProbeEvaluationStatus
    status_reason: str | None
    aspect_scoring: str
    scored_risk_id: None
    risks_triggered: list[str]
    flags: list[str]
    checks: dict[str, dict[str, Any]]
    required_checks: dict[str, dict[str, Any]]
    bonus_checks: dict[str, dict[str, Any]]
    checks_present: int
    checks_required: int
    coverage_ratio: float
    card_chars: int
    high_impact_claims: list[str]
    claims: dict[str, dict[str, str]]
    claim_boundary: dict[str, str]
    reliability: dict[str, Any]
    uncertainty: dict[str, Any]
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


def evaluate_safety(*, model_metadata: dict[str, Any]) -> SafetyEvalResult:
    """Evaluate safety-governance disclosure from Hub model-card metadata."""
    meta = model_metadata or {}
    card_text = _as_str(meta.get("card_text")) or ""
    card_data = _card_data_dict(meta)
    card_chars = len(card_text)

    if card_chars == 0:
        return SafetyEvalResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason="no model card text — cannot evaluate safety disclosures",
            aspect_scoring=ASPECT_NOT_SCORED,
            scored_risk_id=None,
            risks_triggered=[],
            flags=["empty_card"],
            checks={},
            required_checks={},
            bonus_checks={},
            checks_present=0,
            checks_required=len(SAFETY_REQUIRED),
            coverage_ratio=0.0,
            card_chars=0,
            high_impact_claims=[],
            claims={
                "disclosure_completeness": {
                    "status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
                    "reason": G_CARD_EMPTY,
                },
            },
            claim_boundary={
                "supported": CLAIM_SUPPORTED,
                "not_established": CLAIM_NOT_ESTABLISHED,
            },
            reliability={"gates_passed": False, "failed_gates": [G_CARD_EMPTY]},
            uncertainty={},
            limitations=list(LIMITATIONS),
        )

    all_checks = detect_safety_checks(card_text, card_data)
    required = {key: all_checks[key] for key in SAFETY_REQUIRED}
    bonus = {
        key: all_checks[key]
        for key in SAFETY_BONUS
        if key in all_checks
    }
    present_count = checks_present_count(all_checks)
    ratio = safety_coverage_ratio(all_checks)
    phrase_matches = detect_high_impact_claims(card_text)

    flags: list[str] = []
    risks: list[str] = []
    checks: dict[str, dict[str, Any]] = {}

    for key in SAFETY_REQUIRED:
        check = required[key]
        present = bool(check.get("present"))
        if not present:
            flags.append(f"missing_{key}")
        checks[key] = {
            "pass": present,
            "detail": check.get("matched_heading") or "missing or trivial body",
        }

    checks["disclosure_completeness"] = {
        "pass": present_count == len(SAFETY_REQUIRED),
        "detail": f"{present_count}/{len(SAFETY_REQUIRED)} required sections present",
        "checks_present": present_count,
        "checks_required": len(SAFETY_REQUIRED),
        "coverage_ratio": ratio,
    }

    if present_count < len(SAFETY_REQUIRED):
        risks.append(RISK_GOV_DISCLOSURE_GAP)

    if phrase_matches:
        flags.append("high_impact_deployment_claim")
        if ratio < 1.0:
            flags.append("high_impact_without_full_disclosure")

    if ratio < 1.0 or phrase_matches:
        flags.append("needs_human_review")

    if risks:
        aspect_scoring = ASPECT_RISK_DETECTED
    else:
        aspect_scoring = ASPECT_NO_MATERIAL_RISK

    doc_status = ProbeEvaluationStatus.EVALUATED.value
    doc_reason = (
        f"safety disclosure checklist evaluated; {present_count}/{len(SAFETY_REQUIRED)} "
        "required sections present"
    )
    if RISK_GOV_DISCLOSURE_GAP in risks:
        doc_reason = (
            "one or more required safety-disclosure sections absent or trivial "
            f"({present_count}/{len(SAFETY_REQUIRED)} present)"
        )

    phrase_status = doc_status
    phrase_reason = (
        f"lexical documentation evidence: {len(phrase_matches)} listed phrase(s) matched"
        if phrase_matches
        else "no listed high-impact phrases matched"
    )

    return SafetyEvalResult(
        status=ProbeEvaluationStatus.EVALUATED,
        status_reason=None,
        aspect_scoring=aspect_scoring,
        scored_risk_id=None,
        risks_triggered=risks,
        flags=flags,
        checks=checks,
        required_checks=required,
        bonus_checks=bonus,
        checks_present=present_count,
        checks_required=len(SAFETY_REQUIRED),
        coverage_ratio=ratio,
        card_chars=card_chars,
        high_impact_claims=phrase_matches,
        claims={
            "disclosure_completeness": {
                "status": doc_status,
                "reason": doc_reason,
            },
            "phrase_matches": {
                "status": phrase_status,
                "reason": phrase_reason,
            },
        },
        claim_boundary={
            "supported": CLAIM_SUPPORTED,
            "not_established": CLAIM_NOT_ESTABLISHED,
        },
        reliability={"gates_passed": True, "failed_gates": []},
        uncertainty={},
        limitations=list(LIMITATIONS),
    )
