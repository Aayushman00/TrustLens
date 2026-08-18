"""Model-card section coverage helpers (Phase 13).

Matcher rules (rule-based; not keyword stuffing / not NLP quality):
1. Split ATX headings ``#`` / ``##`` / ``###`` at line start; keep heading → body.
2. Map heading text (lowercased, punctuation stripped) to section keys via aliases.
3. If a required section is still missing, fall back to common Hub ``card_data`` fields.
4. ``present=true`` only when matched heading/field exists AND body/value is non-trivial
   (strip length >= ``MIN_BODY_CHARS``). Empty ``## Limitations`` does not count.

Coverage = present_count / 5 over REQUIRED_SECTIONS only (bonus sections tracked separately).
"""

from __future__ import annotations

from typing import Any

from app.probes.card_markdown import (
    MIN_BODY_CHARS,
    field_nontrivial,
    match_aliases,
    normalize_heading,
    nontrivial,
    split_card_sections,
)

REQUIRED_SECTIONS: tuple[str, ...] = (
    "intended_use",
    "limitations",
    "training_data",
    "evaluation",
    "ethical_considerations",
)

BONUS_SECTIONS: tuple[str, ...] = (
    "architecture",
    "citation",
    "examples",
)

# Alias phrases → section key (matched against normalized heading text).
_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "intended_use": (
        "intended use",
        "use cases",
        "direct use",
        "intended uses",
    ),
    "limitations": (
        "limitations",
        "limitation",
        "out of scope",
        "out-of-scope",
        "known limitations",
        "bias",
        "risks",
        "bias risks and limitations",
    ),
    "training_data": (
        "training data",
        "training dataset",
        "training datasets",
        "datasets",
        "dataset",
    ),
    "evaluation": (
        "evaluation",
        "evaluation results",
        "results",
        "metrics",
        "benchmark",
        "benchmarks",
    ),
    "ethical_considerations": (
        "ethical considerations",
        "bias and risks",
        "broader impacts",
        "ethics",
        "ethical considerations and caveats",
    ),
    "architecture": (
        "architecture",
        "model architecture",
        "model description",
    ),
    "citation": (
        "citation",
        "bibtex",
        "how to cite",
        "citing",
    ),
    "examples": (
        "examples",
        "example usage",
        "usage examples",
        "how to use",
    ),
}

# card_data keys that can satisfy a missing section (structured Hub fields).
_CARD_DATA_FALLBACKS: dict[str, tuple[str, ...]] = {
    "training_data": ("datasets", "dataset", "train_data"),
    "evaluation": ("model-index", "model_index", "eval_results", "metrics"),
    "examples": ("widget", "widget_data", "inference"),
    "architecture": ("model_name", "base_model", "pipeline_tag"),
}

_OPEN_CLAIM_PHRASES: tuple[str, ...] = (
    "fully open",
    "completely open",
    "unlimited commercial use",
    "unrestricted commercial",
    "free for any commercial",
    "open for any use",
)

_PRODUCTION_CLAIM_PHRASES: tuple[str, ...] = (
    "production ready",
    "production-ready",
    "ready for production",
    "state of the art for all",
    "state-of-the-art for all",
    "suitable for all uses",
    "works for every use case",
)

_RESTRICTIVE_LICENSE_MARKERS: tuple[str, ...] = (
    "cc-by-nc",
    "cc by-nc",
    "non-commercial",
    "noncommercial",
    "gpl",
    "agpl",
    "proprietary",
    "llama",
    "other",
    "unknown",
)


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value).strip() or None


def _card_data_dict(meta_or_card: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(meta_or_card, dict):
        return {}
    if "card_data" in meta_or_card and isinstance(meta_or_card.get("card_data"), dict):
        return meta_or_card["card_data"]
    return meta_or_card


def _structured_license(meta: dict[str, Any]) -> str | None:
    card_data = _card_data_dict(meta)
    for candidate in (meta.get("license"), card_data.get("license")):
        text = _as_str(candidate)
        if text:
            return text
    return None


def detect_required_sections(
    card_text: str,
    card_data: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Detect required + bonus sections; return presence + matched heading."""
    split = split_card_sections(card_text or "")
    results: dict[str, dict[str, Any]] = {
        key: {"present": False, "matched_heading": None}
        for key in (*REQUIRED_SECTIONS, *BONUS_SECTIONS)
    }

    for heading, body in split.items():
        key = match_aliases(normalize_heading(heading), _SECTION_ALIASES)
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


def coverage_ratio(section_results: dict[str, dict[str, Any]]) -> float:
    """``present_count / 5`` over required sections only."""
    present = sum(
        1
        for key in REQUIRED_SECTIONS
        if bool((section_results.get(key) or {}).get("present"))
    )
    return round(present / len(REQUIRED_SECTIONS), 4)


def detect_contradictions(
    card_text: str,
    meta: dict[str, Any],
    *,
    section_results: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Simple consistency flags — not NLP entailment."""
    flags: list[str] = []
    text = (card_text or "").strip()
    if not text:
        flags.append("empty_card")
        return flags

    lower = text.lower()
    sections = section_results or detect_required_sections(
        text, _card_data_dict(meta)
    )
    limitations_present = bool((sections.get("limitations") or {}).get("present"))

    open_claim = any(phrase in lower for phrase in _OPEN_CLAIM_PHRASES)
    license_value = _structured_license(meta)
    license_lower = (license_value or "").lower()
    if not license_value:
        restrictive_or_missing = True
    else:
        restrictive_or_missing = any(
            marker in license_lower for marker in _RESTRICTIVE_LICENSE_MARKERS
        )
    if open_claim and restrictive_or_missing:
        flags.append("open_claim_vs_restrictive_license")

    production_claim = any(phrase in lower for phrase in _PRODUCTION_CLAIM_PHRASES)
    if production_claim and not limitations_present:
        flags.append("no_limitations_but_production_claim")

    return flags


def sections_present_count(section_results: dict[str, dict[str, Any]]) -> int:
    return sum(
        1
        for key in REQUIRED_SECTIONS
        if bool((section_results.get(key) or {}).get("present"))
    )


__all__ = [
    "BONUS_SECTIONS",
    "MIN_BODY_CHARS",
    "REQUIRED_SECTIONS",
    "coverage_ratio",
    "detect_contradictions",
    "detect_required_sections",
    "sections_present_count",
    "split_card_sections",
]
