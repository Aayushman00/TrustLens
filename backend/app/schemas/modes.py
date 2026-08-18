"""Dual-mode product policy (Phase 17, ADR 0011) — disclosure schema + disclaimers.

Two product modes only; human review is optional **by mode**:

- ``AI_AUTONOMOUS`` — auto-finalizes from agent O/S/D; ``human_reviewed`` stays
  ``False`` on this path. Never presented as ground truth.
- ``AI_ASSISTED`` — stops at ``AWAITING_REVIEW``; ``human_reviewed`` becomes
  ``True`` only after the Phase 18 accept/edit review finalizes.

This module is the single source of the disclaimer texts. It is vendored into
the worker image so the pipeline persists the exact same wording into
``final_scores.finalized_osd``.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.db.enums import EvaluationMode

METHODOLOGY_STATUS_PROPOSED = "PROPOSED_REQUIRES_VALIDATION"

AUTONOMOUS_DISCLAIMER = (
    "O/S/D were generated automatically and were not human-reviewed. Not ground truth."
)
ASSISTED_AWAITING_DISCLAIMER = "Awaiting human review of agent O/S/D suggestions."
ASSISTED_REVIEWED_DISCLAIMER = (
    "Finalized O/S/D were human-reviewed (accept/edit of agent suggestions)."
)


def disclaimer_for(evaluation_mode: EvaluationMode, *, human_reviewed: bool) -> str:
    if evaluation_mode == EvaluationMode.AI_AUTONOMOUS:
        return AUTONOMOUS_DISCLAIMER
    if human_reviewed:
        return ASSISTED_REVIEWED_DISCLAIMER
    return ASSISTED_AWAITING_DISCLAIMER


class ModeDisclosure(BaseModel):
    """Mandatory mode/provenance disclosure on evaluation detail reads."""

    evaluation_mode: EvaluationMode
    human_reviewed: bool
    disclaimer: str
    methodology_status: str  # PROPOSED_REQUIRES_VALIDATION for agent-sourced O/S/D


def build_mode_disclosure(
    *,
    evaluation_mode: EvaluationMode,
    human_reviewed: bool,
    methodology_status: str = METHODOLOGY_STATUS_PROPOSED,
) -> ModeDisclosure:
    return ModeDisclosure(
        evaluation_mode=evaluation_mode,
        human_reviewed=human_reviewed,
        disclaimer=disclaimer_for(evaluation_mode, human_reviewed=human_reviewed),
        methodology_status=methodology_status,
    )
