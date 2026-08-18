"""AgentResult → persistence shapes for ``osd_agent_outputs`` / ``final_scores``."""

from __future__ import annotations

from typing import Any

from app.db.enums import EvaluationMode
from app.osd.base import AgentResult
from app.schemas.modes import AUTONOMOUS_DISCLAIMER

_SUGGESTION_NOTE = (
    "AI-proposed O/S/D suggestion — not ground truth; requires human validation."
)


def to_ai_suggestion(result: AgentResult) -> dict[str, Any]:
    """JSON for ``osd_agent_outputs.ai_suggestion`` (loudly PROPOSED)."""
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
                "confidence": aspect.confidence,
                "rationale": aspect.rationale,
            }
            for aspect in result.aspects
        ],
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
    """
    return {
        "methodology_status": result.methodology_status,
        "source": "osd_agent_autonomous",
        "evaluation_mode": EvaluationMode.AI_AUTONOMOUS.value,
        "human_reviewed": False,
        "disclaimer": AUTONOMOUS_DISCLAIMER,
        "aspects": [
            {
                "aspect": aspect.aspect.value,
                "O": aspect.O,
                "S": aspect.S,
                "D": aspect.D,
            }
            for aspect in result.aspects
        ],
    }
