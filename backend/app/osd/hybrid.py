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

import hashlib
import logging
import time

from app.core.config import get_settings
from app.db.enums import FriesDimension
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import AgentContext, AgentResult, LEGACY_HEURISTIC_METHODOLOGY_STATUS
from app.osd.llm_client import (
    GEMINI_MODEL,
    GROQ_MODEL,
    NVIDIA_MODEL,
    OPENAI_COMPAT_TEMPERATURE,
    PROMPT_VERSION,
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


def _has_behavioural_safety(ctx: AgentContext) -> bool:
    snap = next((s for s in ctx.probe_results if s.dimension == FriesDimension.SAFETY), None)
    return snap is not None and isinstance((snap.metric_values or {}).get("severe_fnr"), (int, float))


_MAX_ATTEMPTS = 3
_BACKOFF_S = 10.0
_MAX_RETRY_AFTER_S = 30.0


def _retry_delay(exc: Exception, attempt: int) -> float | None:
    """Seconds to wait before retrying the same provider, or None = give up.

    Retries 5xx, transport errors and per-minute 429s. A 429 for a daily quota
    ("per day"/TPD) or with Retry-After above _MAX_RETRY_AFTER_S cannot clear
    within this evaluation, so it is not retried."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            body = exc.response.text.lower()
            if "per day" in body or "(tpd)" in body:
                return None
            raw = exc.response.headers.get("retry-after")
            try:
                wait = float(raw) if raw is not None else _BACKOFF_S * 2 ** (attempt - 1)
            except ValueError:
                wait = _BACKOFF_S * 2 ** (attempt - 1)
            return wait if wait <= _MAX_RETRY_AFTER_S else None
        return _BACKOFF_S * 2 ** (attempt - 1) if code >= 500 else None
    if isinstance(exc, (httpx.TransportError, ConnectionError, TimeoutError)):
        return _BACKOFF_S * 2 ** (attempt - 1)
    return None


def _describe(exc: Exception) -> str:
    import httpx

    text = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, httpx.HTTPStatusError):
        text += f" body={exc.response.text[:200]}"
    return text


class HybridOSDAgent:
    """Heuristic baseline + Gemini-judged INTEGRITY/EXPLAINABILITY/SAFETY."""

    def propose(self, ctx: AgentContext) -> AgentResult:
        baseline = HeuristicOSDAgent().propose(ctx)
        judgment, provenance = self._get_llm_judgment(ctx)

        by_aspect = {aspect.aspect: aspect for aspect in baseline.aspects}
        for dimension in _TARGET_DIMENSIONS:
            aspect = by_aspect.get(dimension)
            if aspect is None:
                continue
            if judgment is None:
                aspect.osd_metadata = {**aspect.osd_metadata, **provenance}
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
            if dimension == FriesDimension.SAFETY and _has_behavioural_safety(ctx):
                # Measured severe-harm misses outrank an LLM reading of the card;
                # keep the LLM's view as traceable metadata only.
                aspect.osd_metadata = {
                    **aspect.osd_metadata,
                    **provenance,
                    "llm_card_judgment": {"O": dim_judgment.O, "S": dim_judgment.S, "D": dim_judgment.D},
                }
                continue
            aspect.O, aspect.S, aspect.D = dim_judgment.O, dim_judgment.S, dim_judgment.D
            aspect.O_source = aspect.S_source = aspect.D_source = _LLM_SOURCE
            aspect.rationale = dim_judgment.rationale
            aspect.osd_metadata = {**aspect.osd_metadata, **provenance}
            # EXPLAINABILITY/SAFETY only (see llm_client._PROMPT_TEMPLATE) —
            # an audit-visible companion to the rationale, never a mechanical
            # override of O/S/D and never required for a "successful" judgment.
            if dim_judgment.content_quality is not None:
                aspect.osd_metadata = {
                    **aspect.osd_metadata,
                    "content_quality": dim_judgment.content_quality,
                }

        return AgentResult(
            aspects=baseline.aspects,
            overall_confidence=baseline.overall_confidence,
            methodology_status=LEGACY_HEURISTIC_METHODOLOGY_STATUS,
            model_ref=ctx.model_ref,
            assessment_engine="llm_v1",
        )

    def _get_llm_judgment(
        self, ctx: AgentContext
    ) -> tuple[GeminiOSDResponse | None, dict[str, object]]:
        """Return the first valid judgment plus provenance for the aspects it rates
        (provider, model, temperature, prompt hash); on failure ``(None, {llm_fallback_reason, ...})``."""
        settings = get_settings()
        providers = (
            ("gemini", settings.gemini_api_key, call_gemini, GEMINI_MODEL, None),
            ("groq", getattr(settings, "groq_api_key", None), call_groq, GROQ_MODEL, OPENAI_COMPAT_TEMPERATURE),
            ("nvidia", getattr(settings, "nvidia_api_key", None), call_nvidia, NVIDIA_MODEL, OPENAI_COMPAT_TEMPERATURE),
        )
        prompt = build_prompt(ctx)
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        errors: list[str] = []
        for name, api_key, call_fn, model, temperature in providers:
            if not api_key:
                continue
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    raw = call_fn(prompt, api_key=api_key)
                    return parse_gemini_response(raw), {
                        "llm_provider": name,
                        "llm_model": model,
                        # None = provider default (Gemini call sets no temperature).
                        "llm_temperature": temperature,
                        "llm_prompt_sha256": prompt_sha256,
                        "llm_attempts": attempt,
                        "llm_prompt_version": PROMPT_VERSION,
                    }
                except Exception as exc:  # noqa: BLE001 — retry/next provider, never propagate
                    errors.append(f"{name}#{attempt}: {_describe(exc)}"[:400])
                    logger.warning(
                        "osd_agent_llm_v1_provider_failed evaluation_id=%s provider=%s attempt=%s",
                        ctx.evaluation_id, name, attempt, exc_info=True,
                    )
                    delay = _retry_delay(exc, attempt)
                    if delay is None or attempt == _MAX_ATTEMPTS:
                        break
                    time.sleep(delay)
        logger.warning(
            "osd_agent_llm_v1_all_providers_failed evaluation_id=%s — falling back to heuristic",
            ctx.evaluation_id,
        )
        return None, {"llm_fallback_reason": " | ".join(errors) or "no LLM provider configured",
                      "llm_prompt_sha256": prompt_sha256}
