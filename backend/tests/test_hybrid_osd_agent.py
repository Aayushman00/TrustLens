"""backend/tests/test_hybrid_osd_agent.py"""
from __future__ import annotations

import uuid
from unittest.mock import patch

from app.db.enums import FriesDimension
from app.osd.base import AgentContext, ProbeSnapshot
from app.osd.hybrid import HybridOSDAgent

_GOOD_RAW = (
    '{"INTEGRITY": {"O": 7, "S": 7, "D": 8, "rationale": "checks pass"}, '
    '"EXPLAINABILITY": {"O": 5, "S": 5, "D": 5, "rationale": "thin coverage but present"}, '
    '"SAFETY": {"O": 3, "S": 3, "D": 4, "rationale": "governance gap detected"}}'
)


def _full_context() -> AgentContext:
    return AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={"card_text": "# Card\n## Limitations\nNone."},
        probe_results=[
            ProbeSnapshot(
                dimension=FriesDimension.FAIRNESS,
                metric_values={
                    "demographic_parity_difference": 0.08,
                    "equalized_odds_difference": 0.05,
                    "min_group_n": 30,
                    "min_group_n_observed": 45,
                },
                confidence=0.85,
                evidence_refs=[{"evidence_id": "e1"}],
            ),
            ProbeSnapshot(
                dimension=FriesDimension.ROBUSTNESS,
                metric_values={"clean_accuracy": 0.9, "robust_accuracy": 0.8, "degradation_ratio": 0.889},
                confidence=0.9,
                evidence_refs=[{"evidence_id": "e2"}],
            ),
            ProbeSnapshot(
                dimension=FriesDimension.INTEGRITY,
                metric_values={"checks": {"a": {"pass": True}}, "pass_count": 1, "fail_count": 0},
                confidence=1.0,
                evidence_refs=[{"evidence_id": "e3"}],
            ),
            ProbeSnapshot(
                dimension=FriesDimension.EXPLAINABILITY,
                metric_values={"coverage_ratio": 0.8, "card_chars": 200},
                confidence=0.9,
                evidence_refs=[{"evidence_id": "e4"}],
            ),
            ProbeSnapshot(
                dimension=FriesDimension.SAFETY,
                metric_values={"coverage_ratio": 0.5, "card_chars": 200, "high_impact_claims": []},
                confidence=0.7,
                evidence_refs=[{"evidence_id": "e5"}],
            ),
        ],
    )


@patch("app.osd.hybrid.call_gemini", return_value=_GOOD_RAW)
@patch("app.osd.hybrid.get_settings")
def test_llm_success_overwrites_only_the_three_target_aspects(mock_settings, mock_call) -> None:
    mock_settings.return_value.gemini_api_key = "fake-key"
    result = HybridOSDAgent().propose(_full_context())

    assert result.assessment_engine == "llm_v1"
    by_aspect = {a.aspect: a for a in result.aspects}

    fairness = by_aspect[FriesDimension.FAIRNESS]
    assert fairness.O_source in (None, "heuristic")  # untouched by LLM path
    robustness = by_aspect[FriesDimension.ROBUSTNESS]
    assert robustness.O_source in (None, "heuristic")

    integrity = by_aspect[FriesDimension.INTEGRITY]
    assert (integrity.O, integrity.S, integrity.D) == (7, 7, 8)
    assert integrity.O_source == integrity.S_source == integrity.D_source == "llm_v1"
    assert integrity.rationale == "checks pass"

    safety = by_aspect[FriesDimension.SAFETY]
    assert (safety.O, safety.S, safety.D) == (3, 3, 4)
    assert safety.D_source == "llm_v1"
