"""Explainability evaluation unit tests (tl-explainability-v1.0)."""

from __future__ import annotations

from pathlib import Path

from app.db.enums import ProbeEvaluationStatus
from app.probes.explainability_eval import evaluate_explainability
from app.probes.explainability_stats import (
    ASPECT_NO_MATERIAL_RISK,
    ASPECT_NOT_SCORED,
    ASPECT_RISK_DETECTED,
    G_CARD_EMPTY,
    METHODOLOGY_VERSION,
    RISK_DOC_CONTRADICTION,
    RISK_DOC_INCOMPLETE,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_empty_card_insufficient_not_scored() -> None:
    result = evaluate_explainability(model_metadata={"card_text": ""})
    assert result.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE
    assert result.aspect_scoring == ASPECT_NOT_SCORED
    assert result.scored_risk_id is None
    assert result.risks_triggered == []
    assert G_CARD_EMPTY in result.reliability["failed_gates"]
    assert RISK_DOC_INCOMPLETE not in result.risks_triggered


def test_complete_card_no_material_risk() -> None:
    text = _read("model_card_complete.md")
    result = evaluate_explainability(
        model_metadata={"card_text": text, "license": "apache-2.0"}
    )
    assert result.status == ProbeEvaluationStatus.EVALUATED
    assert result.aspect_scoring == ASPECT_NO_MATERIAL_RISK
    assert result.scored_risk_id is None
    assert result.risks_triggered == []
    assert result.coverage_ratio == 1.0


def test_prose_without_headings_evaluated_incomplete() -> None:
    text = (
        "This model was trained on a public corpus and evaluated offline. "
        "It is intended for research demos only."
    )
    result = evaluate_explainability(model_metadata={"card_text": text})
    assert result.status == ProbeEvaluationStatus.EVALUATED
    assert result.aspect_scoring == ASPECT_RISK_DETECTED
    assert RISK_DOC_INCOMPLETE in result.risks_triggered
    assert result.coverage_ratio == 0.0


def test_contradiction_triggers_doc_contradiction_risk() -> None:
    text = _read("model_card_contradiction.md")
    result = evaluate_explainability(
        model_metadata={"card_text": text, "license": "cc-by-nc-4.0"}
    )
    assert result.status == ProbeEvaluationStatus.EVALUATED
    assert RISK_DOC_CONTRADICTION in result.risks_triggered
    assert RISK_DOC_INCOMPLETE in result.risks_triggered
    assert result.aspect_scoring == ASPECT_RISK_DETECTED
    assert result.scored_risk_id is None


def test_aspect_scoring_never_scored_risk_token() -> None:
    for meta in (
        {"card_text": ""},
        {"card_text": _read("model_card_complete.md")},
        {"card_text": _read("model_card_contradiction.md"), "license": "cc-by-nc-4.0"},
    ):
        result = evaluate_explainability(model_metadata=meta)
        assert result.aspect_scoring != "scored_risk"


def test_claim_boundary_forbids_overclaim_language() -> None:
    result = evaluate_explainability(model_metadata={"card_text": _read("model_card_complete.md")})
    not_established = result.claim_boundary["not_established"].lower()
    assert "faithfulness" in not_established
    assert "explainable" in not_established
    for limitation in result.limitations:
        assert "quality score" not in limitation.lower() or "not" in limitation.lower()
