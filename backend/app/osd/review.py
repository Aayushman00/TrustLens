"""Human review of agent O/S/D (Phase 18) — pure merge + finalized_osd builder.

No DB/S3. The Assisted finalize path uses these to turn the latest agent
suggestion + reviewer edits into the human-approved ``finalized_osd`` that the
pure FRIES scorer consumes when scoring is complete.
"""

from __future__ import annotations

from typing import Any

from app.db.enums import EvaluationMode, FriesDimension
from app.osd.base import METHODOLOGY_STATUS_DETERMINISTIC
from app.osd.serialize import (
    FRIES_ASPECT_COUNT,
    count_scoring_complete_aspects,
)
from app.schemas.modes import disclaimer_for, METHODOLOGY_STATUS_PROPOSED

ASSISTED_SOURCE = "human_review_assisted"

# Per-field O/S/D provenance tag for values a human explicitly entered/
# confirmed via the review endpoint — never inferred or fabricated. Kept as
# a stable string alongside the LLM-assisted workflow's own tags
# (HybridOSDAgent in hybrid.py populates the same O_source/S_source/D_source
# keys with "llm_v1" on a successful Gemini judgment, or "heuristic_fallback"
# when it falls back) without changing this schema.
HUMAN_SOURCE = "human"

_METHODOLOGY_NOTE_HEURISTIC = (
    "Legacy heuristic O/S/D was PROPOSED (requires validation); the values here "
    "were human approved/edited. Not an LLM assessment."
)
_METHODOLOGY_NOTE_DETERMINISTIC = (
    "Deterministic OSD v1 — the agent never proposes O, S, or D (no approved "
    "automatic mapping exists yet); all three are human-entered assessment, "
    "not measured model properties. FRIES withheld until all O/S/D are "
    "complete for every required aspect."
)


def _is_deterministic(agent_suggestion: dict[str, Any]) -> bool:
    return (
        agent_suggestion.get("assessment_engine") == "deterministic"
        or agent_suggestion.get("methodology_status") == METHODOLOGY_STATUS_DETERMINISTIC
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


def _triple_if_complete(entry: dict[str, Any], aspect: str) -> dict[str, Any] | None:
    """Return a triple when O/S/D are all ints; None when the agent abstained."""
    o, s, d = entry.get("O"), entry.get("S"), entry.get("D")
    if o is None or s is None or d is None:
        return None
    return _triple(entry, aspect)


def _partial_entry(edit: dict[str, Any], aspect: str) -> dict[str, Any]:
    """Build an aspect entry preserving nulls for omitted O/S/D."""
    entry: dict[str, Any] = {"aspect": aspect}
    for key in ("O", "S", "D"):
        if key in edit and edit[key] is not None:
            entry[key] = int(edit[key])
        else:
            entry[key] = None
    return entry


def merge_review_aspects(
    agent_suggestion: dict[str, Any],
    edits: list[dict[str, Any]] | None,
    *,
    accept_all: bool,
) -> tuple[list[dict[str, Any]], bool]:
    """Merge reviewer edits over the agent suggestion.

    Returns ``(approved_aspects, human_changed)``. On the deterministic path,
    O, S, and D are all independently human-enterable per aspect (the agent
    itself never proposes any of them — it always abstains); each field the
    reviewer omits stays ``None`` on that aspect, never defaulted.
    ``accept_all`` records evidence acceptance without fabricating O/S/D.
    """
    if _is_deterministic(agent_suggestion):
        return _merge_deterministic(agent_suggestion, edits, accept_all=accept_all)
    return _merge_legacy_heuristic(agent_suggestion, edits, accept_all=accept_all)


def _merge_legacy_heuristic(
    agent_suggestion: dict[str, Any],
    edits: list[dict[str, Any]] | None,
    *,
    accept_all: bool,
) -> tuple[list[dict[str, Any]], bool]:
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
        agent_entry = agent_aspects[name]
        agent_triple = _triple_if_complete(agent_entry, name)
        if agent_triple is None:
            continue
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
    if not approved:
        raise ValueError("no aspects with complete O/S/D to approve")
    return approved, human_changed


def _merge_deterministic(
    agent_suggestion: dict[str, Any],
    edits: list[dict[str, Any]] | None,
    *,
    accept_all: bool,
) -> tuple[list[dict[str, Any]], bool]:
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

    if accept_all:
        return [], False

    approved: list[dict[str, Any]] = []
    human_changed = False
    for name in expected:
        edit = edits_by_aspect.get(name)
        if edit is None:
            continue
        # Each of O, S, D is independently optional (AspectOSDEdit only
        # requires at least one field to be present on the edit itself).
        # Whatever the reviewer omits stays None here — never defaulted.
        entry = _partial_entry(edit, name)
        agent_entry = agent_aspects[name]
        for field in ("O", "S", "D"):
            if agent_entry.get(field) != entry[field]:
                human_changed = True
        approved.append(entry)
    return approved, human_changed


def build_overrides(
    *,
    accept_all: bool,
    approved_aspects: list[dict[str, Any]],
    agent_suggestion: dict[str, Any],
    review_rationale: str | None,
) -> dict[str, Any]:
    """Structured ``human_reviews.overrides`` JSON."""
    snapshot_aspects: list[dict[str, Any]] = []
    for entry in agent_suggestion.get("aspects") or []:
        aspect = str(entry.get("aspect", ""))
        triple = _triple_if_complete(entry, aspect)
        if triple is not None:
            snapshot_aspects.append(triple)
        elif _is_deterministic(agent_suggestion):
            snapshot_aspects.append(
                {
                    "aspect": aspect,
                    "O": entry.get("O"),
                    "S": entry.get("S"),
                    "D": entry.get("D"),
                }
            )
    return {
        "schema_version": "human-review-v1",
        "accept_all": accept_all,
        "approved_osd": {"aspects": approved_aspects},
        "agent_osd_snapshot": {
            "methodology_status": agent_suggestion.get("methodology_status"),
            "assessment_engine": agent_suggestion.get("assessment_engine"),
            "overall_confidence": agent_suggestion.get("overall_confidence"),
            "aspects": snapshot_aspects,
        },
        "review_rationale": review_rationale,
    }


def to_finalized_osd_assisted(
    approved_aspects: list[dict[str, Any]],
    *,
    human_review_id: int,
    human_changed: bool,
    agent_suggestion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``final_scores.finalized_osd`` for the Assisted path (human-approved)."""
    deterministic = _is_deterministic(agent_suggestion or {})
    methodology_status = (
        (agent_suggestion or {}).get("methodology_status")
        or (
            METHODOLOGY_STATUS_DETERMINISTIC
            if deterministic
            else METHODOLOGY_STATUS_PROPOSED
        )
    )
    methodology_note = (
        _METHODOLOGY_NOTE_DETERMINISTIC
        if deterministic
        else _METHODOLOGY_NOTE_HEURISTIC
    )
    aspects_out: list[dict[str, Any]] = []
    for entry in approved_aspects:
        aspect = str(entry.get("aspect", ""))
        out_entry: dict[str, Any] = {
            "aspect": aspect,
            "O": entry.get("O"),
            "S": entry.get("S"),
            "D": entry.get("D"),
        }
        if deterministic:
            # On the deterministic path the agent itself never proposes O,
            # S, or D (it always abstains) — _merge_deterministic guarantees
            # every non-null value reaching here came from an explicit
            # reviewer edit (accept_all short-circuits to an empty approved
            # list), so tagging each present field "human" here is never a
            # fabricated provenance claim. A field the reviewer left blank
            # stays None with no source tag — never defaulted.
            out_entry["O_source"] = HUMAN_SOURCE if out_entry["O"] is not None else None
            out_entry["S_source"] = HUMAN_SOURCE if out_entry["S"] is not None else None
            out_entry["D_source"] = HUMAN_SOURCE if out_entry["D"] is not None else None
        aspects_out.append(out_entry)
    complete_count = count_scoring_complete_aspects(aspects_out)
    scoring_complete = complete_count == FRIES_ASPECT_COUNT
    payload: dict[str, Any] = {
        "methodology_status": methodology_status,
        "methodology_note": methodology_note,
        "source": ASSISTED_SOURCE,
        "evaluation_mode": EvaluationMode.AI_ASSISTED.value,
        "human_reviewed": True,
        "human_changed": human_changed,
        "human_review_id": human_review_id,
        "disclaimer": disclaimer_for(
            EvaluationMode.AI_ASSISTED,
            human_reviewed=True,
            assessment_engine=str(
                (agent_suggestion or {}).get("assessment_engine") or ""
            )
            or None,
            methodology_status=str(methodology_status),
            scoring_withheld=not scoring_complete,
        ),
        "scoring_complete": scoring_complete,
        "scoring_withheld": not scoring_complete,
        "complete_aspect_count": complete_count,
        "aspects": aspects_out,
    }
    if agent_suggestion is not None:
        payload["assessment_engine"] = agent_suggestion.get("assessment_engine")
    return payload
