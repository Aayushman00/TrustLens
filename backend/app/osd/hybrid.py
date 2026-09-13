"""backend/app/osd/hybrid.py — HybridOSDAgent (Phase 20).

Baseline is always HeuristicOSDAgent's full five-dimension proposal. One
batched Gemini call then re-scores INTEGRITY/EXPLAINABILITY/SAFETY; on any
failure those three keep the heuristic's numbers, tagged as a fallback.
FAIRNESS/ROBUSTNESS are never touched by this engine.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.db.enums import FriesDimension
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import AgentContext, AgentResult, LEGACY_HEURISTIC_METHODOLOGY_STATUS
from app.osd.llm_client import GeminiOSDResponse, build_prompt, call_gemini, parse_gemini_response

logger = logging.getLogger("trustlens.osd")

_TARGET_DIMENSIONS = (
    FriesDimension.INTEGRITY,
    FriesDimension.EXPLAINABILITY,
    FriesDimension.SAFETY,
)

_LLM_SOURCE = "llm_v1"
_FALLBACK_SOURCE = "heuristic_fallback"


class HybridOSDAgent:
    """Heuristic baseline + Gemini-judged INTEGRITY/EXPLAINABILITY/SAFETY."""

    def propose(self, ctx: AgentContext) -> AgentResult:
        baseline = HeuristicOSDAgent().propose(ctx)
        judgment = self._get_llm_judgment(ctx)

        by_aspect = {aspect.aspect: aspect for aspect in baseline.aspects}
        for dimension in _TARGET_DIMENSIONS:
            aspect = by_aspect.get(dimension)
            if aspect is None:
                continue
            if judgment is None:
                if aspect.O is not None:
                    aspect.O_source = _FALLBACK_SOURCE
                if aspect.S is not None:
                    aspect.S_source = _FALLBACK_SOURCE
                if aspect.D is not None:
                    aspect.D_source = _FALLBACK_SOURCE
                continue
            dim_judgment = getattr(judgment, dimension.value)
            aspect.O, aspect.S, aspect.D = dim_judgment.O, dim_judgment.S, dim_judgment.D
            aspect.O_source = aspect.S_source = aspect.D_source = _LLM_SOURCE
            aspect.rationale = dim_judgment.rationale

        return AgentResult(
            aspects=baseline.aspects,
            overall_confidence=baseline.overall_confidence,
            methodology_status=LEGACY_HEURISTIC_METHODOLOGY_STATUS,
            model_ref=ctx.model_ref,
            assessment_engine="llm_v1",
        )

    def _get_llm_judgment(self, ctx: AgentContext) -> GeminiOSDResponse | None:
        settings = get_settings()
        api_key = settings.gemini_api_key
        if not api_key:
            logger.warning(
                "osd_agent_llm_v1_no_api_key evaluation_id=%s — falling back to heuristic",
                ctx.evaluation_id,
            )
            return None
        try:
            prompt = build_prompt(ctx)
            raw = call_gemini(prompt, api_key=api_key)
            return parse_gemini_response(raw)
        except Exception:  # noqa: BLE001 — any LLM/parse failure falls back, never propagates
            logger.warning(
                "osd_agent_llm_v1_failed evaluation_id=%s — falling back to heuristic",
                ctx.evaluation_id,
                exc_info=True,
            )
            return None
