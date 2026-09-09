"""P3-A corrective fix — disclosure/report text must follow actual scoring
state (scoring_withheld), not just assessment_engine/methodology_status.

Pure-function tests only: no DB, no pipeline run. These exercise exactly the
functions implicated in the audit finding — disclaimer_for, osd_provenance_bullet,
score_note_for, and build_executive_summary — directly, so a regression here
cannot hide behind fixture/DB setup noise.
"""

from __future__ import annotations

from app.db.enums import EvaluationMode
from app.reports.builder import build_executive_summary
from app.schemas.modes import (
    ASSISTED_REVIEWED_DISCLAIMER,
    ASSISTED_REVIEWED_LEGACY_DISCLAIMER,
    ASSISTED_REVIEWED_SCORED_DISCLAIMER,
    DETERMINISTIC_ABSTAIN_DISCLAIMER,
    SCORE_NOTE_DETERMINISTIC,
    SCORE_NOTE_DETERMINISTIC_SCORED,
    disclaimer_for,
    osd_provenance_bullet,
    score_note_for,
)

_DET_KW = {"assessment_engine": "deterministic", "methodology_status": "DETERMINISTIC_OSD_V1"}


# ---------------------------------------------------------------------------
# Case 1: deterministic + AI_ASSISTED + complete human O/S/D + FRIES scored
# ---------------------------------------------------------------------------


def test_disclaimer_scored_case_never_says_withheld_or_not_generated() -> None:
    text = disclaimer_for(
        EvaluationMode.AI_ASSISTED,
        human_reviewed=True,
        scoring_withheld=False,
        **_DET_KW,
    )
    assert text == ASSISTED_REVIEWED_SCORED_DISCLAIMER
    assert "withheld" not in text.lower()
    assert "were not generated" not in text.lower()
    assert "human-entered" in text.lower()


def test_score_note_scored_case_never_says_abstains() -> None:
    note = score_note_for(scoring_withheld=False, **_DET_KW)
    assert note == SCORE_NOTE_DETERMINISTIC_SCORED
    assert "abstains" not in note.lower()
    assert "were not generated" not in note.lower()


def test_osd_provenance_bullet_scored_case_describes_human_entry() -> None:
    bullet = osd_provenance_bullet(scoring_withheld=False, **_DET_KW)
    assert "were not generated" not in bullet.lower()
    assert "human-entered" in bullet.lower()


def test_executive_summary_scored_case_has_no_contradiction() -> None:
    """Reproduces the exact audit repro: human_reviewed=True + a real score
    must not coexist with 'FRIES is withheld' / 'were not generated' text."""
    summary = build_executive_summary(
        mode=EvaluationMode.AI_ASSISTED,
        human_reviewed=True,
        fries_score=7.2,
        dimension_scores={"FAIRNESS": 8.0},
        probe_flags=[],
        model_ref="org/model",
        scoring_withheld=False,
        **_DET_KW,
    )
    joined = " | ".join(summary.bullets).lower()
    assert "human reviewed: yes" in joined
    assert "withheld" not in joined
    assert "were not generated" not in joined
    assert "human-entered" in joined


# ---------------------------------------------------------------------------
# Case 2: deterministic + AI_ASSISTED + incomplete O/S/D + FRIES withheld
# ---------------------------------------------------------------------------


def test_disclaimer_withheld_case_unchanged_and_still_correct() -> None:
    text = disclaimer_for(
        EvaluationMode.AI_ASSISTED,
        human_reviewed=True,
        scoring_withheld=True,
        **_DET_KW,
    )
    assert text == ASSISTED_REVIEWED_DISCLAIMER
    assert "withheld" in text.lower()
    assert "human-entered" in text.lower()  # still accurately describes provenance


def test_disclaimer_withheld_case_default_param_matches_explicit_true() -> None:
    """Omitting scoring_withheld (unknown state) must not accidentally claim scored."""
    default_text = disclaimer_for(EvaluationMode.AI_ASSISTED, human_reviewed=True, **_DET_KW)
    assert default_text == ASSISTED_REVIEWED_DISCLAIMER


def test_score_note_withheld_case_unchanged() -> None:
    assert score_note_for(scoring_withheld=True, **_DET_KW) == SCORE_NOTE_DETERMINISTIC
    assert score_note_for(**_DET_KW) == SCORE_NOTE_DETERMINISTIC  # default omitted


def test_executive_summary_withheld_case_states_withheld() -> None:
    summary = build_executive_summary(
        mode=EvaluationMode.AI_ASSISTED,
        human_reviewed=True,
        fries_score=0.0,
        dimension_scores={},
        probe_flags=[],
        model_ref="org/model",
        scoring_withheld=True,
        **_DET_KW,
    )
    joined = " | ".join(summary.bullets).lower()
    assert "were not generated" in joined or "withheld" in joined
    assert "human-entered for every required aspect" not in joined


# ---------------------------------------------------------------------------
# Case 3: deterministic + AI_AUTONOMOUS + no human O/S/D — must remain intact
# ---------------------------------------------------------------------------


def test_autonomous_deterministic_disclaimer_unaffected_by_fix() -> None:
    """AI_AUTONOMOUS never takes human review, so scoring_withheld here should
    have no bearing — the autonomous abstain disclaimer must be untouched,
    and must never imply human assessment occurred."""
    text = disclaimer_for(
        EvaluationMode.AI_AUTONOMOUS,
        human_reviewed=False,
        scoring_withheld=True,
        **_DET_KW,
    )
    assert text == DETERMINISTIC_ABSTAIN_DISCLAIMER
    assert "not human-reviewed" in text.lower()

    # Even a stray/impossible scoring_withheld=False must not flip this branch
    # into claiming human review happened — AI_AUTONOMOUS is checked first.
    text_defensive = disclaimer_for(
        EvaluationMode.AI_AUTONOMOUS,
        human_reviewed=False,
        scoring_withheld=False,
        **_DET_KW,
    )
    assert text_defensive == DETERMINISTIC_ABSTAIN_DISCLAIMER


# ---------------------------------------------------------------------------
# Case 4: legacy heuristic — behavior must remain unchanged
# ---------------------------------------------------------------------------


def test_legacy_heuristic_disclaimer_unaffected_by_scoring_withheld() -> None:
    kw = {"assessment_engine": "legacy_heuristic", "methodology_status": "LEGACY_HEURISTIC_OSD_V1"}
    for withheld in (True, False, None):
        text = disclaimer_for(
            EvaluationMode.AI_ASSISTED,
            human_reviewed=True,
            scoring_withheld=withheld,
            **kw,
        )
        assert text == ASSISTED_REVIEWED_LEGACY_DISCLAIMER


def test_legacy_heuristic_score_note_and_bullet_unaffected() -> None:
    kw = {"assessment_engine": "legacy_heuristic", "methodology_status": "LEGACY_HEURISTIC_OSD_V1"}
    for withheld in (True, False, None):
        assert "legacy heuristic proposals" in osd_provenance_bullet(scoring_withheld=withheld, **kw)


# ---------------------------------------------------------------------------
# Source-language / no-fabrication invariants
# ---------------------------------------------------------------------------


def test_no_disclaimer_ever_attributes_osd_to_a_probe_or_ai() -> None:
    """None of the disclosure text — in any state — may claim O/S/D came from
    a probe, the model, or an automatic/AI/inferred/estimated process."""
    banned = ("probe generated", "ai-generated", "model-inferred", "auto-generated", "estimated by")
    texts = [
        disclaimer_for(EvaluationMode.AI_ASSISTED, human_reviewed=True, scoring_withheld=False, **_DET_KW),
        disclaimer_for(EvaluationMode.AI_ASSISTED, human_reviewed=True, scoring_withheld=True, **_DET_KW),
        disclaimer_for(EvaluationMode.AI_AUTONOMOUS, human_reviewed=False, **_DET_KW),
        score_note_for(scoring_withheld=False, **_DET_KW),
        score_note_for(scoring_withheld=True, **_DET_KW),
        osd_provenance_bullet(scoring_withheld=False, **_DET_KW),
        osd_provenance_bullet(scoring_withheld=True, **_DET_KW),
    ]
    for text in texts:
        lowered = text.lower()
        for phrase in banned:
            assert phrase not in lowered, f"{phrase!r} found in: {text!r}"


def test_this_fix_creates_no_new_scoring_path() -> None:
    """The corrective fix must be presentation-only: these functions take a
    scoring_withheld flag as INPUT and never compute or call the FRIES
    scorer themselves. Asserting on return type (str) is a cheap proxy for
    'no score object was constructed here'."""
    assert isinstance(
        disclaimer_for(EvaluationMode.AI_ASSISTED, human_reviewed=True, scoring_withheld=False, **_DET_KW),
        str,
    )
    assert isinstance(score_note_for(scoring_withheld=False, **_DET_KW), str)
    assert isinstance(osd_provenance_bullet(scoring_withheld=False, **_DET_KW), str)
