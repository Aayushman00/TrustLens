"""safety_card helper unit tests (Phase 14)."""

from __future__ import annotations

from pathlib import Path

from app.probes.safety_card import (
    detect_high_impact_claims,
    detect_safety_checks,
    safety_coverage_ratio,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_complete_safety_coverage() -> None:
    text = _read("model_card_safety_complete.md")
    checks = detect_safety_checks(text, {})
    assert safety_coverage_ratio(checks) == 1.0
    for key in ("misuse_risks", "privacy", "security_warnings", "data_disclosure"):
        assert checks[key]["present"] is True
        assert checks[key]["matched_heading"]


def test_missing_privacy_ratio() -> None:
    text = _read("model_card_safety_missing_privacy.md")
    checks = detect_safety_checks(text, {})
    assert checks["privacy"]["present"] is False
    assert checks["misuse_risks"]["present"] is True
    assert safety_coverage_ratio(checks) == 0.75


def test_high_impact_claims() -> None:
    text = _read("model_card_safety_high_impact.md")
    claims = detect_high_impact_claims(text)
    assert "production_ready" in claims
    assert "healthcare" in claims
    checks = detect_safety_checks(text, {})
    assert safety_coverage_ratio(checks) < 1.0
    assert checks["privacy"]["present"] is False
    assert checks["misuse_risks"]["present"] is False


def test_ethical_considerations_does_not_count_as_misuse() -> None:
    text = (
        "## Ethical Considerations\n\n"
        "Broader impacts include stereotype amplification for some cohorts.\n\n"
        "## Training Data\n\n"
        "Public review corpora with documented collection process and licenses.\n"
    )
    checks = detect_safety_checks(text, {})
    assert checks["misuse_risks"]["present"] is False
    assert checks["data_disclosure"]["present"] is True


def test_card_data_fallback_data_disclosure() -> None:
    text = "## Privacy\n\nPersonal data and PII must be redacted before inference runs.\n"
    checks = detect_safety_checks(
        text,
        {"datasets": [{"name": "glue", "config": "sst2"}]},
    )
    assert checks["data_disclosure"]["present"] is True
    assert checks["data_disclosure"]["matched_heading"] == "card_data.datasets"
