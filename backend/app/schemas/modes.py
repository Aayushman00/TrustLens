"""Dual-mode product policy (Phase 17, ADR 0011) — disclosure schema + disclaimers.

Two *workflow* modes (human review gate). Orthogonal to assessment_engine:

- ``AI_AUTONOMOUS`` — pipeline may finalize without human review.
- ``AI_ASSISTED`` — stops at ``AWAITING_REVIEW`` until a human review.

Assessment engines:

- ``deterministic`` (default) — abstains O/S/D; FRIES withheld.
- ``legacy_heuristic`` — heuristic proposed O/S/D; not an LLM; not Mode B.

This module is the single source of the disclaimer texts. It is vendored into
the worker image so the pipeline persists the exact same wording into
``final_scores.finalized_osd``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app.db.enums import EvaluationMode

_METHODOLOGY_STATUS_DETERMINISTIC = "DETERMINISTIC_OSD_V1"

METHODOLOGY_STATUS_PROPOSED = "PROPOSED_REQUIRES_VALIDATION"

FriesStatus = Literal["scored", "withheld", "not_scored_yet"]

DETERMINISTIC_ABSTAIN_DISCLAIMER = (
    "O/S/D were not generated. The deterministic mapper abstained because no "
    "validated O/S/D mapping is available. FRIES is withheld. This evaluation "
    "was not human-reviewed."
)
LEGACY_AUTONOMOUS_DISCLAIMER = (
    "Heuristic O/S/D values were produced by the legacy heuristic engine and "
    "were not human-reviewed. They are proposed, not ground truth, and are "
    "not an LLM assessment."
)
# Historical name: default (deterministic) autonomous wording.
AUTONOMOUS_DISCLAIMER = DETERMINISTIC_ABSTAIN_DISCLAIMER

ASSISTED_AWAITING_DISCLAIMER = (
    "Awaiting human review before finalize. This is a human-review workflow, "
    "not LLM interpretation of evidence."
)
ASSISTED_REVIEWED_DISCLAIMER = (
    "Human review recorded. On the deterministic path O remains unavailable "
    "(no validated mapping), D remains unavailable, and S is human-controlled "
    "only when supplied. FRIES is withheld until complete O/S/D exist."
)
ASSISTED_REVIEWED_LEGACY_DISCLAIMER = (
    "Finalized O/S/D were human-reviewed (accept/edit of legacy heuristic "
    "suggestions). Heuristic values are not ground truth and are not an LLM "
    "assessment."
)

SCORE_NOTE_DETERMINISTIC = (
    "Original FRIES is computed only from complete finalized O/S/D — not FRIES2. "
    "Deterministic mapping abstains: O/S/D were not generated."
)
SCORE_NOTE_LEGACY = (
    "Original FRIES computed from finalized O/S/D — not FRIES2. O/S/D on this "
    "path are legacy heuristic proposals, not an LLM assessment and not ground truth."
)


def is_deterministic_engine(
    assessment_engine: str | None,
    methodology_status: str | None = None,
) -> bool:
    if assessment_engine == "deterministic":
        return True
    if assessment_engine in ("legacy_heuristic", "heuristic"):
        return False
    return methodology_status == _METHODOLOGY_STATUS_DETERMINISTIC


def fries_status_for(
    *,
    scoring_withheld: bool | None,
    has_final_score: bool,
    osd_present: bool,
) -> FriesStatus:
    if has_final_score:
        return "scored"
    if scoring_withheld is True:
        return "withheld"
    if osd_present:
        return "withheld"
    return "not_scored_yet"


def disclaimer_for(
    evaluation_mode: EvaluationMode,
    *,
    human_reviewed: bool,
    assessment_engine: str | None = "deterministic",
    methodology_status: str | None = None,
    scoring_withheld: bool | None = None,
) -> str:
    deterministic = is_deterministic_engine(assessment_engine, methodology_status)
    if evaluation_mode == EvaluationMode.AI_AUTONOMOUS:
        if deterministic:
            return DETERMINISTIC_ABSTAIN_DISCLAIMER
        return LEGACY_AUTONOMOUS_DISCLAIMER
    if human_reviewed:
        if deterministic:
            return ASSISTED_REVIEWED_DISCLAIMER
        return ASSISTED_REVIEWED_LEGACY_DISCLAIMER
    return ASSISTED_AWAITING_DISCLAIMER


def score_note_for(
    *,
    assessment_engine: str | None = None,
    methodology_status: str | None = None,
) -> str:
    if is_deterministic_engine(assessment_engine, methodology_status):
        return SCORE_NOTE_DETERMINISTIC
    return SCORE_NOTE_LEGACY


def osd_provenance_bullet(
    *,
    assessment_engine: str | None = None,
    methodology_status: str | None = None,
) -> str:
    if is_deterministic_engine(assessment_engine, methodology_status):
        return (
            "O/S/D were not generated (deterministic abstention; no validated "
            "mapping). Not an LLM assessment."
        )
    return (
        "O/S/D are legacy heuristic proposals — not ground truth and not an "
        "LLM assessment."
    )


class ModeDisclosure(BaseModel):
    """Mandatory mode/provenance disclosure on evaluation detail reads."""

    evaluation_mode: EvaluationMode
    human_reviewed: bool
    disclaimer: str
    methodology_status: str
    assessment_engine: str | None = None
    scoring_withheld: bool | None = None
    fries_status: FriesStatus | None = None


def build_mode_disclosure(
    *,
    evaluation_mode: EvaluationMode,
    human_reviewed: bool,
    methodology_status: str = METHODOLOGY_STATUS_PROPOSED,
    assessment_engine: str | None = None,
    scoring_withheld: bool | None = None,
    fries_status: FriesStatus | None = None,
) -> ModeDisclosure:
    engine = assessment_engine or (
        "deterministic"
        if methodology_status == _METHODOLOGY_STATUS_DETERMINISTIC
        else None
    )
    return ModeDisclosure(
        evaluation_mode=evaluation_mode,
        human_reviewed=human_reviewed,
        disclaimer=disclaimer_for(
            evaluation_mode,
            human_reviewed=human_reviewed,
            assessment_engine=engine,
            methodology_status=methodology_status,
            scoring_withheld=scoring_withheld,
        ),
        methodology_status=methodology_status,
        assessment_engine=engine,
        scoring_withheld=scoring_withheld,
        fries_status=fries_status,
    )


def engine_from_osd_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    engine = payload.get("assessment_engine")
    if isinstance(engine, str) and engine:
        return engine
    return None
