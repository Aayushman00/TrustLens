"""backend/tests/test_llm_client.py"""
from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from app.db.enums import FriesDimension
from app.osd.base import AgentContext, ProbeSnapshot
from app.osd.llm_client import GeminiOSDResponse, build_prompt, parse_gemini_response


def _ctx() -> AgentContext:
    return AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={"card_text": "# Model\n\n## Limitations\nNone known."},
        probe_results=[
            ProbeSnapshot(
                dimension=FriesDimension.FAIRNESS,
                metric_values={"demographic_parity_difference": 0.05},
                confidence=0.8,
                evidence_refs=[],
            ),
            ProbeSnapshot(
                dimension=FriesDimension.INTEGRITY,
                metric_values={"checks": {"license_present": {"pass": True}}},
                confidence=0.9,
                evidence_refs=[],
            ),
            ProbeSnapshot(
                dimension=FriesDimension.EXPLAINABILITY,
                metric_values={"coverage_ratio": 0.8, "card_chars": 200},
                confidence=0.9,
                evidence_refs=[],
            ),
            ProbeSnapshot(
                dimension=FriesDimension.SAFETY,
                metric_values={"coverage_ratio": 0.6, "risks_triggered": ["gov_disclosure_gap"]},
                confidence=0.7,
                evidence_refs=[],
            ),
        ],
    )


def test_build_prompt_includes_only_the_three_target_dimensions_and_card_text() -> None:
    prompt = build_prompt(_ctx())
    assert "Limitations" in prompt  # card_text made it in
    assert "license_present" in prompt  # INTEGRITY evidence made it in
    assert "coverage_ratio" in prompt  # EXPLAINABILITY/SAFETY evidence made it in
    assert "gov_disclosure_gap" in prompt
    assert "demographic_parity_difference" not in prompt  # FAIRNESS excluded


def test_build_prompt_instructs_multi_sentence_evidence_citing_rationale() -> None:
    prompt = build_prompt(_ctx())
    assert "3-5 sentences" in prompt
    assert "quote or closely paraphrase" in prompt


def test_parse_gemini_response_accepts_well_formed_json() -> None:
    raw = json.dumps(
        {
            "INTEGRITY": {
                "O": 7,
                "S": 7,
                "D": 8,
                "rationale": "Metadata checks pass: the license field and pass_count in the "
                "evidence block confirm all required integrity checks succeeded.",
            },
            "EXPLAINABILITY": {
                "O": 6,
                "S": 6,
                "D": 6,
                "rationale": "The card has a Limitations section but coverage_ratio of 0.8 "
                "shows other required sections are thin or missing.",
            },
            "SAFETY": {
                "O": 4,
                "S": 4,
                "D": 5,
                "rationale": "The gov_disclosure_gap risk flag was triggered, and coverage_ratio "
                "of 0.6 indicates governance disclosure is incomplete.",
            },
        }
    )
    result = parse_gemini_response(raw)
    assert isinstance(result, GeminiOSDResponse)
    assert result.INTEGRITY.O == 7
    assert "gov_disclosure_gap" in result.SAFETY.rationale


def test_parse_gemini_response_rejects_too_short_rationale() -> None:
    raw = json.dumps(
        {
            "INTEGRITY": {"O": 7, "S": 7, "D": 8, "rationale": "checks pass"},
            "EXPLAINABILITY": {
                "O": 6,
                "S": 6,
                "D": 6,
                "rationale": "The card has a Limitations section but other required sections are thin.",
            },
            "SAFETY": {
                "O": 4,
                "S": 4,
                "D": 5,
                "rationale": "The gov_disclosure_gap risk flag was triggered during evaluation.",
            },
        }
    )
    with pytest.raises(ValidationError):
        parse_gemini_response(raw)


def test_parse_gemini_response_rejects_malformed_json() -> None:
    with pytest.raises(Exception):
        parse_gemini_response("not json at all")


def test_parse_gemini_response_rejects_out_of_range_band() -> None:
    raw = json.dumps(
        {
            "INTEGRITY": {"O": 11, "S": 7, "D": 8, "rationale": "x"},
            "EXPLAINABILITY": {"O": 6, "S": 6, "D": 6, "rationale": "x"},
            "SAFETY": {"O": 4, "S": 4, "D": 5, "rationale": "x"},
        }
    )
    with pytest.raises(ValidationError):
        parse_gemini_response(raw)


def test_parse_gemini_response_rejects_missing_dimension() -> None:
    raw = json.dumps(
        {
            "INTEGRITY": {"O": 7, "S": 7, "D": 8, "rationale": "x"},
            "EXPLAINABILITY": {"O": 6, "S": 6, "D": 6, "rationale": "x"},
        }
    )
    with pytest.raises(ValidationError):
        parse_gemini_response(raw)
