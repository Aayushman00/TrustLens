"""Human review of agent O/S/D (Phase 18) — pure merge + finalized_osd builder.

No DB/S3. The Assisted finalize path uses these to turn the latest agent
suggestion + reviewer edits into the human-approved ``finalized_osd`` that the
pure FRIES scorer consumes. Final Assisted O/S/D = human-approved values only.
"""

from __future__ import annotations

from typing import Any

from app.db.enums import EvaluationMode, FriesDimension
from app.schemas.modes import ASSISTED_REVIEWED_DISCLAIMER, METHODOLOGY_STATUS_PROPOSED

ASSISTED_SOURCE = "human_review_assisted"

_METHODOLOGY_NOTE = (
    "Agent O/S/D was PROPOSED (heuristic, requires validation); the values here "
    "were human approved/edited."
)


def _triple(entry: dict[str, Any], aspect: str) -> dict[str, Any]:
    try:
        return {
            "aspect": aspect,
            "O": int(entry["O"]),
            "S": int(entry["S"]),
            "D": int(entry["D"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"aspect {aspect}: malformed O/S/D entry: {entry!r}") from exc


def merge_review_aspects(
    agent_suggestion: dict[str, Any],
    edits: list[dict[str, Any]] | None,
    *,
    accept_all: bool,
) -> tuple[list[dict[str, Any]], bool]:
    """Merge reviewer edits over the agent suggestion.

    Returns ``(approved_aspects, human_changed)`` covering all five FRIES
    dimensions: edited aspects take the reviewer values, the rest keep the
    agent values. ``human_changed`` is True iff any approved triple differs
    from the agent snapshot.
    """
    expected = [dimension.value for dimension in FriesDimension]
    agent_aspects: dict[str, dict[str, Any]] = {}
    for entry in agent_suggestion.get("aspects") or []:
        name = str(entry.get("aspect", ""))
        if name:
            agent_aspects[name] = entry
    missing = [name for name in expected if name not in agent_aspects]
    if missing:
        raise ValueError(f"agent suggestion is missing aspects: {missing}")

    if accept_all and edits:
        raise ValueError("accept_all=true does not take aspect edits")
    if not accept_all and not edits:
        raise ValueError("accept_all=false requires at least one aspect edit")

    edits_by_aspect: dict[str, dict[str, Any]] = {}
    for edit in edits or []:
        name = str(edit.get("aspect", ""))
        if name not in expected:
            raise ValueError(f"unknown aspect in edits: {name!r}")
        if name in edits_by_aspect:
            raise ValueError(f"duplicate aspect in edits: {name}")
        edits_by_aspect[name] = edit

    approved: list[dict[str, Any]] = []
    human_changed = False
    for name in expected:
        agent_triple = _triple(agent_aspects[name], name)
        edit = edits_by_aspect.get(name)
        if edit is None:
            approved.append(agent_triple)
            continue
        reviewed = _triple(edit, name)
        if (reviewed["O"], reviewed["S"], reviewed["D"]) != (
            agent_triple["O"],
            agent_triple["S"],
            agent_triple["D"],
        ):
            human_changed = True
        approved.append(reviewed)
    return approved, human_changed


def build_overrides(
    *,
    accept_all: bool,
    approved_aspects: list[dict[str, Any]],
    agent_suggestion: dict[str, Any],
    review_rationale: str | None,
) -> dict[str, Any]:
    """Structured ``human_reviews.overrides`` JSON."""
    return {
        "schema_version": "human-review-v1",
        "accept_all": accept_all,
        "approved_osd": {"aspects": approved_aspects},
        "agent_osd_snapshot": {
            "methodology_status": agent_suggestion.get("methodology_status"),
            "overall_confidence": agent_suggestion.get("overall_confidence"),
            "aspects": [
                _triple(entry, str(entry.get("aspect", "")))
                for entry in agent_suggestion.get("aspects") or []
            ],
        },
        "review_rationale": review_rationale,
    }


def to_finalized_osd_assisted(
    approved_aspects: list[dict[str, Any]],
    *,
    human_review_id: int,
    reviewer_id: int,
    human_changed: bool,
) -> dict[str, Any]:
    """``final_scores.finalized_osd`` for the Assisted path (human-approved).

    Mirrors the Autonomous builder in ``app.osd.serialize.to_finalized_osd``
    but flips the disclosure: ``human_reviewed=True`` + the reviewed
    disclaimer. The heuristic metric→O/S/D mapping stays labeled PROPOSED.
    """
    return {
        "methodology_status": METHODOLOGY_STATUS_PROPOSED,
        "methodology_note": _METHODOLOGY_NOTE,
        "source": ASSISTED_SOURCE,
        "evaluation_mode": EvaluationMode.AI_ASSISTED.value,
        "human_reviewed": True,
        "human_changed": human_changed,
        "human_review_id": human_review_id,
        "reviewer_id": reviewer_id,
        "disclaimer": ASSISTED_REVIEWED_DISCLAIMER,
        "aspects": [_triple(entry, str(entry.get("aspect", ""))) for entry in approved_aspects],
    }
