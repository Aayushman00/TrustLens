"""Safety disclosure checklist helpers (Phase 14).

Mandatory coverage evidence (not keyword stuffing / not FRIES2 caps / not O/S/D):
- misuse_risks, privacy, security_warnings, data_disclosure (denominator = 4)
- Optional tracked only: bias_and_fairness_risks, human_oversight

Matcher: ATX headings via ``card_markdown`` + safety-specific alias tables.
``ethical_considerations`` alone does **not** satisfy ``misuse_risks``.

High-impact phrase ids (``detect_high_impact_claims``):
- production_ready ← production ready / production-ready / ready for production
- healthcare ← healthcare / medical / clinical
- finance ← finance / financial / banking
- legal ← legal advice / legal decision
- autonomous_decision ← autonomous decision / fully autonomous
- biometric ← biometric / biometrics
"""

from __future__ import annotations

from typing import Any

from app.probes.card_markdown import (
    field_nontrivial,
    match_aliases,
    normalize_heading,
    nontrivial,
    split_card_sections,
)

SAFETY_REQUIRED: tuple[str, ...] = (
    "misuse_risks",
    "privacy",
    "security_warnings",
    "data_disclosure",
)

SAFETY_BONUS: tuple[str, ...] = (
    "bias_and_fairness_risks",
    "human_oversight",
)

_CHECK_ALIASES: dict[str, tuple[str, ...]] = {
    "misuse_risks": (
        "misuse and malicious use",
        "malicious use",
        "known risks of abuse",
        "out of scope harms",
        "dual-use",
        "dual use",
        "misuse",
    ),
    "privacy": (
        "data protection",
        "personal data",
        "privacy",
        "gdpr",
        "pii",
    ),
    "security_warnings": (
        "security considerations",
        "do not deploy",
        "adversarial",
        "vulnerability",
        "security",
    ),
    "data_disclosure": (
        "training dataset",
        "training data",
        "data sources",
        "data license",
        "collection process",
        "trained on",
        "datasets",
    ),
    "bias_and_fairness_risks": (
        "bias and fairness",
        "fairness risks",
        "demographic bias",
    ),
    "human_oversight": (
        "human in the loop",
        "human oversight",
        "human review",
    ),
}

_CARD_DATA_FALLBACKS: dict[str, tuple[str, ...]] = {
    "data_disclosure": ("datasets", "dataset", "train_data"),
}

# (claim_id, phrases) — phrase match is case-insensitive substring on full card.
_HIGH_IMPACT_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "production_ready",
        ("production ready", "production-ready", "ready for production"),
    ),
    ("healthcare", ("healthcare", "medical", "clinical")),
    ("finance", ("finance", "financial", "banking")),
    ("legal", ("legal advice", "legal decision")),
    (
        "autonomous_decision",
        ("autonomous decision", "fully autonomous"),
    ),
    ("biometric", ("biometric", "biometrics")),
)


def _card_data_dict(meta_or_card: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(meta_or_card, dict):
        return {}
    if "card_data" in meta_or_card and isinstance(meta_or_card.get("card_data"), dict):
        return meta_or_card["card_data"]
    return meta_or_card


def detect_safety_checks(
    card_text: str,
    card_data: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Detect required + bonus safety checks; return presence + matched heading."""
    split = split_card_sections(card_text or "")
    results: dict[str, dict[str, Any]] = {
        key: {"present": False, "matched_heading": None}
        for key in (*SAFETY_REQUIRED, *SAFETY_BONUS)
    }

    for heading, body in split.items():
        key = match_aliases(normalize_heading(heading), _CHECK_ALIASES)
        if key is None or key not in results:
            continue
        if results[key]["present"]:
            continue
        if nontrivial(body):
            results[key] = {"present": True, "matched_heading": heading}

    data = _card_data_dict(card_data)
    for key, field_names in _CARD_DATA_FALLBACKS.items():
        if key not in results or results[key]["present"]:
            continue
        for field in field_names:
            if field in data and field_nontrivial(data.get(field)):
                results[key] = {
                    "present": True,
                    "matched_heading": f"card_data.{field}",
                }
                break

    return results


def safety_coverage_ratio(checks: dict[str, dict[str, Any]]) -> float:
    """``checks_present / 4`` over required safety checks only."""
    present = sum(
        1
        for key in SAFETY_REQUIRED
        if bool((checks.get(key) or {}).get("present"))
    )
    return round(present / len(SAFETY_REQUIRED), 4)


def checks_present_count(checks: dict[str, dict[str, Any]]) -> int:
    return sum(
        1
        for key in SAFETY_REQUIRED
        if bool((checks.get(key) or {}).get("present"))
    )


def detect_high_impact_claims(card_text: str) -> list[str]:
    """Return matched high-impact claim ids (MVP heuristics, not NLP)."""
    lower = (card_text or "").lower()
    if not lower.strip():
        return []
    found: list[str] = []
    for claim_id, phrases in _HIGH_IMPACT_PHRASES:
        if any(phrase in lower for phrase in phrases):
            found.append(claim_id)
    return found
