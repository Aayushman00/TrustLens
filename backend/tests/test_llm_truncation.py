"""Round 3 L8 — LLM evidence/response truncation must never hide decision
fields or pass a cut-off judgment off as a complete assessment."""

from __future__ import annotations

import copy
import sys
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.db.enums import FriesDimension
from app.osd.base import AgentContext, ProbeSnapshot
from app.osd.hybrid import HybridOSDAgent
from app.osd.llm_client import (
    MAX_EVIDENCE_CHARS,
    LLMResponseTruncatedError,
    build_prompt,
    call_gemini,
    call_groq,
)

# Decision fields deliberately placed LAST, after a bulky ``checks`` block —
# the order the integrity/explainability/safety probes really emit them in.
_OVERSIZED = {
    "checks": {f"check_{i}": {"pass": True, "detail": "x" * 200} for i in range(40)},
    "probe_status": "EVALUATED",
    "aspect_scoring": "risk_detected",
    "scored_risk_id": "INTEGRITY_RISK_ID_MARKER",
    "risks_triggered": ["RISK_TRIGGERED_MARKER"],
    "disclosure_gaps": ["DISCLOSURE_GAP_MARKER"],
}


def _ctx(metric_values: dict) -> AgentContext:
    return AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={"card_text": "# Card\n## Limitations\nNone."},
        probe_results=[
            ProbeSnapshot(dimension=d, metric_values=metric_values, confidence=0.8, evidence_refs=[])
            for d in _LLM_DIMS
        ],
    )


_LLM_DIMS = (FriesDimension.INTEGRITY, FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY)


def _section(prompt: str, dimension: str) -> str:
    return prompt.split(f"### {dimension}\n", 1)[1].split("\n### ", 1)[0]


def test_decision_fields_survive_evidence_truncation_and_come_first() -> None:
    assert len(str(_OVERSIZED)) > MAX_EVIDENCE_CHARS  # really oversized
    prompt = build_prompt(_ctx(_OVERSIZED))
    for dimension in ("INTEGRITY", "EXPLAINABILITY", "SAFETY"):
        section = _section(prompt, dimension)
        assert section.startswith("decision: ")
        decision_line = section.split("\n", 1)[0]
        for marker in ("EVALUATED", "risk_detected", "INTEGRITY_RISK_ID_MARKER",
                       "RISK_TRIGGERED_MARKER", "DISCLOSURE_GAP_MARKER"):
            assert marker in decision_line
        assert "[evidence truncated:" in section  # truncation is visible, not silent
        assert "check_0" not in decision_line  # bulk stays in details


def test_build_prompt_does_not_mutate_deterministic_evidence() -> None:
    metric_values = copy.deepcopy(_OVERSIZED)
    build_prompt(_ctx(metric_values))
    assert metric_values == _OVERSIZED


_GOOD_RAW = (
    '{"INTEGRITY": {"O": 7, "S": 7, "D": 8, "rationale": "All metadata checks pass per the evidence '
    'block and the license is disclosed."}, "EXPLAINABILITY": {"O": 5, "S": 5, "D": 5, "rationale": '
    '"The card has a Limitations section but other required sections are thin."}, "SAFETY": {"O": 3, '
    '"S": 3, "D": 4, "rationale": "No explicit safety disclosure section is present in the card."}}'
)


def _settings(mock_settings) -> None:
    mock_settings.return_value.gemini_api_key = "k"
    mock_settings.return_value.groq_api_key = None
    mock_settings.return_value.nvidia_api_key = None


@patch("app.osd.hybrid.call_gemini", return_value=_GOOD_RAW)
@patch("app.osd.hybrid.get_settings")
def test_prompt_truncation_is_recorded_in_provenance(mock_settings, _call) -> None:
    _settings(mock_settings)
    truncated = HybridOSDAgent().propose(_ctx(_OVERSIZED))
    small = HybridOSDAgent().propose(_ctx({"probe_status": "EVALUATED", "coverage_ratio": 0.5}))
    integrity = {a.aspect: a for a in truncated.aspects}[FriesDimension.INTEGRITY]
    assert integrity.osd_metadata["llm_prompt_truncated"] is True
    # The heuristic baseline only rates EXPLAINABILITY for this small context.
    small_rated = {a.aspect: a for a in small.aspects}[FriesDimension.EXPLAINABILITY]
    assert small_rated.osd_metadata["llm_prompt_truncated"] is False


@patch("app.osd.hybrid.get_settings")
def test_cut_off_response_falls_back_explicitly_never_as_llm_judgment(mock_settings) -> None:
    """An oversized reply cut mid-rationale must not become an LLM-rated aspect."""
    _settings(mock_settings)
    cut = _GOOD_RAW[: _GOOD_RAW.index("license is disclosed")]
    with patch("app.osd.hybrid.call_gemini", return_value=cut):
        result = HybridOSDAgent().propose(_ctx(_OVERSIZED))
    rated = [a for a in result.aspects if a.aspect in _LLM_DIMS and a.O is not None]
    assert rated  # INTEGRITY is rated by the heuristic baseline here
    for aspect in rated:
        assert aspect.O_source == "heuristic_fallback"
        assert "llm_fallback_reason" in aspect.osd_metadata
        assert "license is" not in (aspect.rationale or "")


def _openai_response(finish_reason: str) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"finish_reason": finish_reason, "message": {"content": _GOOD_RAW}}]
    }
    return response


def test_openai_compatible_length_cutoff_is_an_error_not_a_reply() -> None:
    with patch("httpx.post", return_value=_openai_response("length")):
        with pytest.raises(LLMResponseTruncatedError):
            call_groq("prompt", api_key="k")
    with patch("httpx.post", return_value=_openai_response("stop")):
        assert call_groq("prompt", api_key="k") == _GOOD_RAW


def _fake_genai(monkeypatch: pytest.MonkeyPatch, finish_reason: str) -> None:
    candidate = MagicMock()
    candidate.finish_reason = types.SimpleNamespace(name=finish_reason)
    response = MagicMock(text=_GOOD_RAW, candidates=[candidate])
    genai = types.ModuleType("google.genai")
    genai.Client = lambda api_key: MagicMock(**{"models.generate_content.return_value": response})  # type: ignore[attr-defined]
    google = types.ModuleType("google")
    google.genai = genai  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)


def test_gemini_max_tokens_cutoff_is_an_error_not_a_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_genai(monkeypatch, "MAX_TOKENS")
    with pytest.raises(LLMResponseTruncatedError):
        call_gemini("prompt", api_key="k")
    _fake_genai(monkeypatch, "STOP")
    assert call_gemini("prompt", api_key="k") == _GOOD_RAW
