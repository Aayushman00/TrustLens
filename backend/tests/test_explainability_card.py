"""explainability_card helper unit tests (Phase 13)."""

from __future__ import annotations

from pathlib import Path

from app.probes.explainability_card import (
    coverage_ratio,
    detect_contradictions,
    detect_required_sections,
    split_card_sections,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_complete_card_full_coverage() -> None:
    text = _read("model_card_complete.md")
    sections = split_card_sections(text)
    assert "Intended Use" in sections
    results = detect_required_sections(text, {})
    assert coverage_ratio(results) == 1.0
    for key in (
        "intended_use",
        "limitations",
        "training_data",
        "evaluation",
        "ethical_considerations",
    ):
        assert results[key]["present"] is True
        assert results[key]["matched_heading"]


def test_empty_card_zero_coverage() -> None:
    text = _read("model_card_empty.md")
    results = detect_required_sections(text, {})
    assert coverage_ratio(results) == 0.0
    assert detect_contradictions(text, {}) == ["empty_card"]


def test_contradiction_card_flags() -> None:
    text = _read("model_card_contradiction.md")
    results = detect_required_sections(text, {})
    assert results["limitations"]["present"] is False
    assert results["intended_use"]["present"] is True
    flags = detect_contradictions(
        text,
        {"license": "cc-by-nc-4.0"},
        section_results=results,
    )
    assert "open_claim_vs_restrictive_license" in flags
    assert "no_limitations_but_production_claim" in flags
    assert "empty_card" not in flags
    assert coverage_ratio(results) < 1.0


def test_empty_heading_body_does_not_count() -> None:
    text = "## Limitations\n\n\n## Intended Use\n\nThis model is intended for research demos only.\n"
    results = detect_required_sections(text, {})
    assert results["limitations"]["present"] is False
    assert results["intended_use"]["present"] is True


def test_card_data_fallback_for_training_data() -> None:
    text = "## Intended Use\n\nResearch demos and offline evaluation notebooks only.\n"
    results = detect_required_sections(
        text,
        {"datasets": [{"name": "glue", "config": "sst2"}]},
    )
    assert results["training_data"]["present"] is True
    assert results["training_data"]["matched_heading"] == "card_data.datasets"
