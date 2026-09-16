"""backend/tests/test_hybrid_osd_agent.py"""
from __future__ import annotations

import uuid
from unittest.mock import patch

from app.db.enums import FriesDimension
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import AgentContext, ProbeSnapshot
from app.osd.hybrid import HybridOSDAgent


def _mock_settings(mock_settings, *, gemini=None, groq=None, nvidia=None) -> None:
    """Explicitly set all three provider keys on a mocked Settings — a
    MagicMock auto-creates a truthy attribute for any name never explicitly
    set, so leaving groq_api_key/nvidia_api_key untouched would make the
    fallback chain think they're configured and try a real HTTP call."""
    mock_settings.return_value.gemini_api_key = gemini
    mock_settings.return_value.groq_api_key = groq
    mock_settings.return_value.nvidia_api_key = nvidia

_GOOD_RAW = (
    '{"INTEGRITY": {"O": 7, "S": 7, "D": 8, '
    '"rationale": "All metadata checks pass per the evidence block, and the card discloses '
    'licensing information clearly."}, '
    '"EXPLAINABILITY": {"O": 5, "S": 5, "D": 5, '
    '"rationale": "The card has a Limitations section but coverage_ratio of 0.8 shows other '
    'required sections are thin or missing."}, '
    '"SAFETY": {"O": 3, "S": 3, "D": 4, '
    '"rationale": "A governance gap was detected: no explicit safety disclosure section is '
    'present in the model card."}}'
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
    _mock_settings(mock_settings, gemini="fake-key")
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
    assert "licensing information" in integrity.rationale

    safety = by_aspect[FriesDimension.SAFETY]
    assert (safety.O, safety.S, safety.D) == (3, 3, 4)
    assert safety.D_source == "llm_v1"


@patch("app.osd.hybrid.call_gemini", side_effect=RuntimeError("timeout"))
@patch("app.osd.hybrid.get_settings")
def test_llm_api_error_falls_back_to_heuristic_values(mock_settings, mock_call) -> None:
    _mock_settings(mock_settings, gemini="fake-key")
    agent = HybridOSDAgent()

    baseline = HeuristicOSDAgent().propose(_full_context())
    result = agent.propose(_full_context())

    by_aspect = {a.aspect: a for a in result.aspects}
    baseline_by_aspect = {a.aspect: a for a in baseline.aspects}
    for dimension in (FriesDimension.INTEGRITY, FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY):
        aspect = by_aspect[dimension]
        base_aspect = baseline_by_aspect[dimension]
        assert (aspect.O, aspect.S, aspect.D) == (base_aspect.O, base_aspect.S, base_aspect.D)
        assert aspect.O_source == aspect.S_source == aspect.D_source == "heuristic_fallback"


@patch("app.osd.hybrid.call_gemini", return_value="not valid json")
@patch("app.osd.hybrid.get_settings")
def test_llm_malformed_json_falls_back_to_heuristic_values(mock_settings, mock_call) -> None:
    _mock_settings(mock_settings, gemini="fake-key")
    baseline = HeuristicOSDAgent().propose(_full_context())
    result = HybridOSDAgent().propose(_full_context())

    by_aspect = {a.aspect: a for a in result.aspects}
    baseline_by_aspect = {a.aspect: a for a in baseline.aspects}
    for dimension in (FriesDimension.INTEGRITY, FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY):
        aspect = by_aspect[dimension]
        base_aspect = baseline_by_aspect[dimension]
        assert (aspect.O, aspect.S, aspect.D) == (base_aspect.O, base_aspect.S, base_aspect.D)
        assert aspect.O_source == aspect.S_source == aspect.D_source == "heuristic_fallback"


@patch("app.osd.hybrid.get_settings")
def test_missing_api_key_falls_back_without_calling_gemini(mock_settings) -> None:
    _mock_settings(mock_settings, gemini=None)
    baseline = HeuristicOSDAgent().propose(_full_context())
    with patch("app.osd.hybrid.call_gemini") as mock_call:
        result = HybridOSDAgent().propose(_full_context())
        mock_call.assert_not_called()

    by_aspect = {a.aspect: a for a in result.aspects}
    baseline_by_aspect = {a.aspect: a for a in baseline.aspects}
    for dimension in (FriesDimension.INTEGRITY, FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY):
        aspect = by_aspect[dimension]
        base_aspect = baseline_by_aspect[dimension]
        assert (aspect.O, aspect.S, aspect.D) == (base_aspect.O, base_aspect.S, base_aspect.D)
        assert aspect.O_source == aspect.S_source == aspect.D_source == "heuristic_fallback"


def _context_missing_explainability_evidence() -> AgentContext:
    """Same as _full_context() but with NO ProbeSnapshot for EXPLAINABILITY.

    The heuristic baseline abstains for EXPLAINABILITY here (agent.py's
    propose() hits ``snap is None`` and sets O=S=D=None), even though the
    batched Gemini prompt below will still return a well-formed triple for
    it (the LLM doesn't know the dimension lacks evidence).
    """
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
            # No ProbeSnapshot for EXPLAINABILITY — heuristic will abstain.
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
def test_llm_success_does_not_fabricate_triple_for_dimension_with_no_evidence(
    mock_settings, mock_call
) -> None:
    """Fix for final-review Fix 1: the LLM success branch must not overwrite
    an aspect the heuristic baseline abstained on, even if Gemini returns a
    well-formed triple for that dimension in the batched response.
    """
    _mock_settings(mock_settings, gemini="fake-key")
    ctx = _context_missing_explainability_evidence()

    # Sanity-check the premise: the heuristic really does abstain here.
    baseline = HeuristicOSDAgent().propose(ctx)
    baseline_by_aspect = {a.aspect: a for a in baseline.aspects}
    explainability_baseline = baseline_by_aspect[FriesDimension.EXPLAINABILITY]
    assert (explainability_baseline.O, explainability_baseline.S, explainability_baseline.D) == (
        None,
        None,
        None,
    )
    assert explainability_baseline.O_source is None
    assert explainability_baseline.S_source is None
    assert explainability_baseline.D_source is None

    result = HybridOSDAgent().propose(ctx)
    by_aspect = {a.aspect: a for a in result.aspects}

    explainability = by_aspect[FriesDimension.EXPLAINABILITY]
    assert (explainability.O, explainability.S, explainability.D) == (None, None, None)
    assert explainability.O_source is None
    assert explainability.S_source is None
    assert explainability.D_source is None
    assert explainability.O_source != "llm_v1"
    assert explainability.S_source != "llm_v1"
    assert explainability.D_source != "llm_v1"

    # INTEGRITY and SAFETY have real evidence and must still pick up the LLM
    # values — the fix must be scoped to the abstaining dimension only.
    integrity = by_aspect[FriesDimension.INTEGRITY]
    assert (integrity.O, integrity.S, integrity.D) == (7, 7, 8)
    assert integrity.O_source == integrity.S_source == integrity.D_source == "llm_v1"

    safety = by_aspect[FriesDimension.SAFETY]
    assert (safety.O, safety.S, safety.D) == (3, 3, 4)
    assert safety.O_source == safety.S_source == safety.D_source == "llm_v1"


@patch("app.osd.hybrid.call_gemini", return_value=_GOOD_RAW)
@patch("app.osd.hybrid.get_settings")
def test_fairness_and_robustness_never_carry_llm_or_fallback_tags(mock_settings, mock_call) -> None:
    _mock_settings(mock_settings, gemini="fake-key")
    result = HybridOSDAgent().propose(_full_context())
    for dimension in (FriesDimension.FAIRNESS, FriesDimension.ROBUSTNESS):
        aspect = next(a for a in result.aspects if a.aspect == dimension)
        assert aspect.O_source not in ("llm_v1", "heuristic_fallback")
        assert aspect.S_source not in ("llm_v1", "heuristic_fallback")
        assert aspect.D_source not in ("llm_v1", "heuristic_fallback")


@patch("app.osd.hybrid.call_groq", return_value=_GOOD_RAW)
@patch("app.osd.hybrid.call_gemini", side_effect=RuntimeError("gemini down"))
@patch("app.osd.hybrid.get_settings")
def test_gemini_failure_falls_through_to_groq(mock_settings, mock_gemini, mock_groq) -> None:
    _mock_settings(mock_settings, gemini="fake-gemini-key", groq="fake-groq-key")
    result = HybridOSDAgent().propose(_full_context())

    mock_gemini.assert_called_once()
    mock_groq.assert_called_once()
    integrity = next(a for a in result.aspects if a.aspect == FriesDimension.INTEGRITY)
    assert (integrity.O, integrity.S, integrity.D) == (7, 7, 8)
    assert integrity.O_source == integrity.S_source == integrity.D_source == "llm_v1"


@patch("app.osd.hybrid.call_nvidia", return_value=_GOOD_RAW)
@patch("app.osd.hybrid.call_groq", side_effect=RuntimeError("groq down"))
@patch("app.osd.hybrid.call_gemini", side_effect=RuntimeError("gemini down"))
@patch("app.osd.hybrid.get_settings")
def test_gemini_and_groq_failure_falls_through_to_nvidia(
    mock_settings, mock_gemini, mock_groq, mock_nvidia
) -> None:
    _mock_settings(mock_settings, gemini="fake-gemini-key", groq="fake-groq-key", nvidia="fake-nvidia-key")
    result = HybridOSDAgent().propose(_full_context())

    mock_gemini.assert_called_once()
    mock_groq.assert_called_once()
    mock_nvidia.assert_called_once()
    integrity = next(a for a in result.aspects if a.aspect == FriesDimension.INTEGRITY)
    assert (integrity.O, integrity.S, integrity.D) == (7, 7, 8)
    assert integrity.O_source == integrity.S_source == integrity.D_source == "llm_v1"


@patch("app.osd.hybrid.call_nvidia", side_effect=RuntimeError("nvidia down"))
@patch("app.osd.hybrid.call_groq", side_effect=RuntimeError("groq down"))
@patch("app.osd.hybrid.call_gemini", side_effect=RuntimeError("gemini down"))
@patch("app.osd.hybrid.get_settings")
def test_all_three_providers_failing_falls_back_to_heuristic(
    mock_settings, mock_gemini, mock_groq, mock_nvidia
) -> None:
    _mock_settings(mock_settings, gemini="fake-gemini-key", groq="fake-groq-key", nvidia="fake-nvidia-key")
    baseline = HeuristicOSDAgent().propose(_full_context())
    result = HybridOSDAgent().propose(_full_context())

    mock_gemini.assert_called_once()
    mock_groq.assert_called_once()
    mock_nvidia.assert_called_once()
    by_aspect = {a.aspect: a for a in result.aspects}
    baseline_by_aspect = {a.aspect: a for a in baseline.aspects}
    for dimension in (FriesDimension.INTEGRITY, FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY):
        aspect = by_aspect[dimension]
        base_aspect = baseline_by_aspect[dimension]
        assert (aspect.O, aspect.S, aspect.D) == (base_aspect.O, base_aspect.S, base_aspect.D)
        assert aspect.O_source == aspect.S_source == aspect.D_source == "heuristic_fallback"


@patch("app.osd.hybrid.call_nvidia")
@patch("app.osd.hybrid.call_groq")
@patch("app.osd.hybrid.call_gemini", return_value=_GOOD_RAW)
@patch("app.osd.hybrid.get_settings")
def test_gemini_success_never_tries_groq_or_nvidia(
    mock_settings, mock_gemini, mock_groq, mock_nvidia
) -> None:
    _mock_settings(mock_settings, gemini="fake-gemini-key", groq="fake-groq-key", nvidia="fake-nvidia-key")
    HybridOSDAgent().propose(_full_context())

    mock_gemini.assert_called_once()
    mock_groq.assert_not_called()
    mock_nvidia.assert_not_called()
