"""AgentResult → persistence shapes for ``osd_agent_outputs`` / ``final_scores``."""

from __future__ import annotations

from typing import Any

from app.db.enums import EvaluationMode, FriesDimension, ProbeEvaluationStatus
from app.osd.base import (
    LEGACY_HEURISTIC_METHODOLOGY_STATUS,
    METHODOLOGY_STATUS_DETERMINISTIC,
    AgentResult,
    AspectOSD,
)
from app.schemas.modes import disclaimer_for

_SUGGESTION_NOTE_HEURISTIC = (
    "Legacy heuristic O/S/D suggestion — proposed, not ground truth, not an LLM "
    "assessment; requires human validation."
)
_SUGGESTION_NOTE_DETERMINISTIC = (
    "Deterministic O/S/D representation from probe evidence; O unavailable "
    "(no approved mapping); S human-controlled; D unavailable."
)

FRIES_ASPECT_COUNT = len(FriesDimension)


def osd_triple_complete(aspect: AspectOSD) -> bool:
    """True iff O, S, and D are all integers (not abstention, not bool)."""
    return aspect_entry_scoring_complete(
        {"O": aspect.O, "S": aspect.S, "D": aspect.D}
    )


def aspect_entry_scoring_complete(entry: dict[str, Any]) -> bool:
    """True when an aspect dict has int O, S, and D suitable for FRIES."""
    for key in ("O", "S", "D"):
        value = entry.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            return False
    return True


def count_scoring_complete_aspects(aspects: list[dict[str, Any]]) -> int:
    return sum(1 for entry in aspects if aspect_entry_scoring_complete(entry))


def _aspect_status(aspect: AspectOSD) -> str:
    if aspect.status is not None:
        return aspect.status.value
    if osd_triple_complete(aspect):
        return ProbeEvaluationStatus.EVALUATED.value
    return ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value


def _suggestion_note(result: AgentResult) -> str:
    if result.assessment_engine == "deterministic":
        return _SUGGESTION_NOTE_DETERMINISTIC
    return _SUGGESTION_NOTE_HEURISTIC


def _aspect_payload(aspect: AspectOSD) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "aspect": aspect.aspect.value,
        "O": aspect.O,
        "S": aspect.S,
        "D": aspect.D,
        "status": _aspect_status(aspect),
        "confidence": aspect.confidence,
        "rationale": aspect.rationale,
    }
    if aspect.O_source is not None:
        payload["O_source"] = aspect.O_source
    if aspect.S_source is not None:
        payload["S_source"] = aspect.S_source
    if aspect.D_source is not None:
        payload["D_source"] = aspect.D_source
    if aspect.osd_metadata:
        payload["osd_metadata"] = aspect.osd_metadata
    return payload


def to_ai_suggestion(result: AgentResult, *, required_aspect_count: int = FRIES_ASPECT_COUNT) -> dict[str, Any]:
    """JSON for ``osd_agent_outputs.ai_suggestion``."""
    complete_count = sum(1 for aspect in result.aspects if osd_triple_complete(aspect))
    scoring_complete = complete_count == required_aspect_count
    return {
        "schema_version": "osd-agent-v1",
        "methodology_status": result.methodology_status,
        "assessment_engine": result.assessment_engine,
        "model_ref": result.model_ref,
        "overall_confidence": result.overall_confidence,
        "aspects": [_aspect_payload(aspect) for aspect in result.aspects],
        "complete_aspect_count": complete_count,
        "scoring_complete": scoring_complete,
        "scoring_withheld": not scoring_complete,
        "note": _suggestion_note(result),
    }


def to_evidence_used(result: AgentResult) -> list[dict[str, Any]]:
    """Flattened probe evidence refs, tagged with the aspect they support."""
    used: list[dict[str, Any]] = []
    for aspect in result.aspects:
        used.extend({**ref, "aspect": aspect.aspect.value} for ref in aspect.evidence_refs)
    return used


def to_rationale(result: AgentResult) -> str:
    """Combined rationale text for ``osd_agent_outputs.rationale``."""
    if result.methodology_status == METHODOLOGY_STATUS_DETERMINISTIC:
        header = (
            "DETERMINISTIC OSD v1 — probe evidence representation only; "
            "O unavailable (no approved mapping); S human-controlled; D unavailable."
        )
    elif result.methodology_status == LEGACY_HEURISTIC_METHODOLOGY_STATUS:
        header = (
            "LEGACY HEURISTIC — PROPOSED / REQUIRES VALIDATION — "
            "heuristic O/S/D suggestions, not ground truth."
        )
    else:
        header = (
            "PROPOSED / REQUIRES VALIDATION — heuristic O/S/D suggestions, not ground truth."
        )
    lines = [header]
    lines.extend(aspect.rationale for aspect in result.aspects)
    return "\n".join(lines)


def to_finalized_osd(result: AgentResult) -> dict[str, Any]:
    """``final_scores.finalized_osd`` for the Autonomous path.

    Aspects with any null O/S/D are omitted — never passed to the scorer.
    """
    complete = [aspect for aspect in result.aspects if osd_triple_complete(aspect)]
    scoring_complete = len(complete) == FRIES_ASPECT_COUNT
    return {
        "methodology_status": result.methodology_status,
        "assessment_engine": result.assessment_engine,
        "source": "osd_agent_autonomous",
        "evaluation_mode": EvaluationMode.AI_AUTONOMOUS.value,
        "human_reviewed": False,
        "disclaimer": disclaimer_for(
            EvaluationMode.AI_AUTONOMOUS,
            human_reviewed=False,
            assessment_engine=result.assessment_engine,
            methodology_status=result.methodology_status,
            scoring_withheld=not scoring_complete,
        ),
        "scoring_complete": scoring_complete,
        "scoring_withheld": not scoring_complete,
        "complete_aspect_count": len(complete),
        "aspects": [
            {
                "aspect": aspect.aspect.value,
                "O": aspect.O,
                "S": aspect.S,
                "D": aspect.D,
            }
            for aspect in complete
        ],
    }
