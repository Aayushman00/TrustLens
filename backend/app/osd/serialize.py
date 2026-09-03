"""AgentResult → persistence shapes for ``osd_agent_outputs`` / ``final_scores``."""

from __future__ import annotations

from typing import Any

from app.db.enums import EvaluationMode, FriesDimension, ProbeEvaluationStatus
from app.osd.base import AgentResult, AspectOSD
from app.schemas.modes import AUTONOMOUS_DISCLAIMER

_SUGGESTION_NOTE = (
    "AI-proposed O/S/D suggestion — not ground truth; requires human validation."
)

FRIES_ASPECT_COUNT = len(FriesDimension)


def osd_triple_complete(aspect: AspectOSD) -> bool:
    """True iff O, S, and D are all integers (not abstention, not bool)."""
    return (
        isinstance(aspect.O, int)
        and not isinstance(aspect.O, bool)
        and isinstance(aspect.S, int)
        and not isinstance(aspect.S, bool)
        and isinstance(aspect.D, int)
        and not isinstance(aspect.D, bool)
    )


def _aspect_status(aspect: AspectOSD) -> str:
    if aspect.status is not None:
        return aspect.status.value
    if osd_triple_complete(aspect):
        return ProbeEvaluationStatus.EVALUATED.value
    return ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value


def to_ai_suggestion(result: AgentResult) -> dict[str, Any]:
    """JSON for ``osd_agent_outputs.ai_suggestion`` (loudly PROPOSED)."""
    complete_count = sum(1 for aspect in result.aspects if osd_triple_complete(aspect))
    scoring_complete = complete_count == FRIES_ASPECT_COUNT
    return {
        "schema_version": "osd-agent-v1",
        "methodology_status": result.methodology_status,
        "model_ref": result.model_ref,
        "overall_confidence": result.overall_confidence,
        "aspects": [
            {
                "aspect": aspect.aspect.value,
                "O": aspect.O,
                "S": aspect.S,
                "D": aspect.D,
                "status": _aspect_status(aspect),
                "confidence": aspect.confidence,
                "rationale": aspect.rationale,
            }
            for aspect in result.aspects
        ],
        "complete_aspect_count": complete_count,
        "scoring_complete": scoring_complete,
        "scoring_withheld": not scoring_complete,
        "note": _SUGGESTION_NOTE,
    }


def to_evidence_used(result: AgentResult) -> list[dict[str, Any]]:
    """Flattened probe evidence refs, tagged with the aspect they support."""
    used: list[dict[str, Any]] = []
    for aspect in result.aspects:
        used.extend({**ref, "aspect": aspect.aspect.value} for ref in aspect.evidence_refs)
    return used


def to_rationale(result: AgentResult) -> str:
    """Combined rationale text for ``osd_agent_outputs.rationale``."""
    lines = [
        "PROPOSED / REQUIRES VALIDATION — heuristic O/S/D suggestions, not ground truth."
    ]
    lines.extend(aspect.rationale for aspect in result.aspects)
    return "\n".join(lines)


def to_finalized_osd(result: AgentResult) -> dict[str, Any]:
    """``final_scores.finalized_osd`` for the Autonomous path.

    Autonomous mode treats the agent suggestion as finalized for the product
    path; the PROPOSED methodology label and the Phase 17 mode disclosure
    (``human_reviewed=false`` + disclaimer) travel with it.

    Aspects with any null O/S/D are omitted — never passed to the scorer.
    """
    complete = [aspect for aspect in result.aspects if osd_triple_complete(aspect)]
    scoring_complete = len(complete) == FRIES_ASPECT_COUNT
    return {
        "methodology_status": result.methodology_status,
        "source": "osd_agent_autonomous",
        "evaluation_mode": EvaluationMode.AI_AUTONOMOUS.value,
        "human_reviewed": False,
        "disclaimer": AUTONOMOUS_DISCLAIMER,
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
