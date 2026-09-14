"""backend/app/osd/hybrid.py — HybridOSDAgent (Phase 20).

Baseline is always HeuristicOSDAgent's full five-dimension proposal. One
batched LLM call then re-scores INTEGRITY/EXPLAINABILITY/SAFETY; on any
failure those three keep the heuristic's numbers, tagged as a fallback.
FAIRNESS/ROBUSTNESS are never touched by this engine.

The LLM call tries providers in order (Gemini -> Groq -> NVIDIA NIM) so a
single provider outage doesn't force every evaluation onto the heuristic —
first provider that returns a valid, parseable response wins; only a
failure from all three falls back to the heuristic.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.db.enums import FriesDimension
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import AgentContext, AgentResult, LEGACY_HEURISTIC_METHODOLOGY_STATUS
from app.osd.llm_client import (
    GeminiOSDResponse,
    build_prompt,
    call_gemini,
    call_groq,
    call_nvidia,
    parse_gemini_response,
)

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
            if aspect.O is None:
                # Heuristic baseline abstained (no probe evidence at all for
                # this dimension) — never apply the LLM's judgment here, even
                # though the batched prompt doesn't know that and may still
                # return a well-formed triple. Leave the aspect exactly as
                # the heuristic produced it (O=S=D=None, source tags as-is).
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
        providers = (
            ("gemini", settings.gemini_api_key, call_gemini),
            ("groq", getattr(settings, "groq_api_key", None), call_groq),
            ("nvidia", getattr(settings, "nvidia_api_key", None), call_nvidia),
        )
        prompt = build_prompt(ctx)
        for name, api_key, call_fn in providers:
            if not api_key:
                continue
            try:
                raw = call_fn(prompt, api_key=api_key)
                return parse_gemini_response(raw)
            except Exception:  # noqa: BLE001 — try the next provider, never propagate
                logger.warning(
                    "osd_agent_llm_v1_provider_failed evaluation_id=%s provider=%s — trying next",
                    ctx.evaluation_id,
                    name,
                    exc_info=True,
                )
                continue
        logger.warning(
            "osd_agent_llm_v1_all_providers_failed evaluation_id=%s — falling back to heuristic",
            ctx.evaluation_id,
        )
        return None
