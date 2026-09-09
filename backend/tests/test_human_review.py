"""Phase 18 — AI-Assisted human review workflow.

Pure merge/build helpers first (no DB), then the API workflow: review →
finalize → FRIES from human-approved O/S/D with ``human_reviewed=true``.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, FriesDimension
from app.db.models import User
from app.db.repositories.final_score import FinalScoreRepository
from app.osd.review import (
    build_overrides,
    merge_review_aspects,
    to_finalized_osd_assisted,
)
from app.schemas.internal import EvaluateModelPayload
from app.schemas.modes import (
    ASSISTED_AWAITING_DISCLAIMER,
    ASSISTED_REVIEWED_DISCLAIMER,
    ASSISTED_REVIEWED_LEGACY_DISCLAIMER,
    ASSISTED_REVIEWED_SCORED_DISCLAIMER,
)
from app.schemas.reviews import HumanReviewRequest
from app.scoring.fries import score_from_finalized_osd
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.conftest import LEGACY_HEURISTIC_PROBE_CONFIG, auth_headers_for, fries_complete_model_payload
from tests.fakes import FakeEvidenceStore


@pytest.fixture(autouse=True)
def _complete_fries_probes(
    evaluated_robustness: None,
    evaluated_fairness: None,
) -> None:
    return

# ---------------------------------------------------------------------------
# Pure helpers — no DB
# ---------------------------------------------------------------------------

AGENT_SUGGESTION = {
    "schema_version": "osd-agent-v1",
    "methodology_status": "LEGACY_HEURISTIC_OSD_V1",
    "assessment_engine": "legacy_heuristic",
    "overall_confidence": 0.62,
    "aspects": [
        {"aspect": "FAIRNESS", "O": 4, "S": 5, "D": 6, "confidence": 0.5, "rationale": "r"},
        {"aspect": "ROBUSTNESS", "O": 5, "S": 5, "D": 5},
        {"aspect": "INTEGRITY", "O": 6, "S": 6, "D": 6},
        {"aspect": "EXPLAINABILITY", "O": 7, "S": 7, "D": 7},
        {"aspect": "SAFETY", "O": 8, "S": 8, "D": 8},
    ],
}


def test_merge_accept_all_keeps_agent_values() -> None:
    approved, human_changed = merge_review_aspects(AGENT_SUGGESTION, None, accept_all=True)
    assert human_changed is False
    assert approved == [
        {"aspect": "FAIRNESS", "O": 4, "S": 5, "D": 6},
        {"aspect": "ROBUSTNESS", "O": 5, "S": 5, "D": 5},
        {"aspect": "INTEGRITY", "O": 6, "S": 6, "D": 6},
        {"aspect": "EXPLAINABILITY", "O": 7, "S": 7, "D": 7},
        {"aspect": "SAFETY", "O": 8, "S": 8, "D": 8},
    ]


def test_merge_partial_edit_defaults_missing_aspects_to_agent() -> None:
    edits = [{"aspect": "FAIRNESS", "O": 0, "S": 5, "D": 6}]
    approved, human_changed = merge_review_aspects(AGENT_SUGGESTION, edits, accept_all=False)
    assert human_changed is True
    by_aspect = {entry["aspect"]: entry for entry in approved}
    assert by_aspect["FAIRNESS"] == {"aspect": "FAIRNESS", "O": 0, "S": 5, "D": 6}
    assert by_aspect["SAFETY"] == {"aspect": "SAFETY", "O": 8, "S": 8, "D": 8}
    assert len(approved) == 5


def test_merge_edit_equal_to_agent_is_not_a_change() -> None:
    edits = [{"aspect": "ROBUSTNESS", "O": 5, "S": 5, "D": 5}]
    _, human_changed = merge_review_aspects(AGENT_SUGGESTION, edits, accept_all=False)
    assert human_changed is False


def test_merge_rejects_unknown_duplicate_and_missing() -> None:
    with pytest.raises(ValueError, match="unknown aspect"):
        merge_review_aspects(
            AGENT_SUGGESTION, [{"aspect": "SPEED", "O": 1, "S": 1, "D": 1}], accept_all=False
        )
    with pytest.raises(ValueError, match="duplicate aspect"):
        merge_review_aspects(
            AGENT_SUGGESTION,
            [
                {"aspect": "SAFETY", "O": 1, "S": 1, "D": 1},
                {"aspect": "SAFETY", "O": 2, "S": 2, "D": 2},
            ],
            accept_all=False,
        )
    broken = {"aspects": AGENT_SUGGESTION["aspects"][:4]}
    with pytest.raises(ValueError, match="missing aspects"):
        merge_review_aspects(broken, None, accept_all=True)


def test_merge_accept_all_flag_contract() -> None:
    with pytest.raises(ValueError, match="does not take aspect edits"):
        merge_review_aspects(
            AGENT_SUGGESTION, [{"aspect": "SAFETY", "O": 9, "S": 9, "D": 9}], accept_all=True
        )
    with pytest.raises(ValueError, match="requires at least one aspect edit"):
        merge_review_aspects(AGENT_SUGGESTION, [], accept_all=False)


def test_build_overrides_shape() -> None:
    approved, _ = merge_review_aspects(AGENT_SUGGESTION, None, accept_all=True)
    overrides = build_overrides(
        accept_all=True,
        approved_aspects=approved,
        agent_suggestion=AGENT_SUGGESTION,
        review_rationale="looks right",
    )
    assert overrides["schema_version"] == "human-review-v1"
    assert overrides["accept_all"] is True
    assert overrides["approved_osd"]["aspects"] == approved
    assert overrides["agent_osd_snapshot"]["overall_confidence"] == 0.62
    assert len(overrides["agent_osd_snapshot"]["aspects"]) == 5
    assert overrides["review_rationale"] == "looks right"


def test_to_finalized_osd_assisted_disclosure() -> None:
    approved, human_changed = merge_review_aspects(
        AGENT_SUGGESTION, [{"aspect": "FAIRNESS", "O": 0, "S": 5, "D": 6}], accept_all=False
    )
    finalized = to_finalized_osd_assisted(
        approved,
        human_review_id=7,
        reviewer_id=3,
        human_changed=human_changed,
        agent_suggestion=AGENT_SUGGESTION,
    )
    assert finalized["human_reviewed"] is True
    assert finalized["human_changed"] is True
    assert finalized["human_review_id"] == 7
    assert finalized["reviewer_id"] == 3
    assert finalized["source"] == "human_review_assisted"
    assert finalized["evaluation_mode"] == "AI_ASSISTED"
    assert finalized["disclaimer"] == ASSISTED_REVIEWED_LEGACY_DISCLAIMER
    assert finalized["methodology_status"] == "LEGACY_HEURISTIC_OSD_V1"
    assert "human approved/edited" in finalized["methodology_note"]
    assert len(finalized["aspects"]) == 5


def test_deterministic_human_s_is_tagged_source_human_never_fabricated() -> None:
    """The temporary manual O/S/D workflow: a human-supplied S is tagged
    ``S_source="human"``; O/D stay unavailable (None), never fabricated.
    Structured so a future engine can populate the same keys with
    "llm_assisted" instead."""
    deterministic_suggestion = {
        "assessment_engine": "deterministic",
        "methodology_status": "DETERMINISTIC_OSD_V1",
        "aspects": [
            {"aspect": dim.value, "O": None, "S": None, "D": None}
            for dim in FriesDimension
        ],
    }
    approved, human_changed = merge_review_aspects(
        deterministic_suggestion,
        [{"aspect": "FAIRNESS", "S": 7}],
        accept_all=False,
    )
    assert human_changed is True
    finalized = to_finalized_osd_assisted(
        approved,
        human_review_id=1,
        reviewer_id=2,
        human_changed=human_changed,
        agent_suggestion=deterministic_suggestion,
    )
    assert len(finalized["aspects"]) == 1
    aspect = finalized["aspects"][0]
    assert aspect["aspect"] == "FAIRNESS"
    assert aspect["S"] == 7
    assert aspect["S_source"] == "human"
    assert aspect["O"] is None
    assert aspect["O_source"] is None  # never fabricated
    assert aspect["D"] is None
    assert aspect["D_source"] is None  # never fabricated


def _deterministic_suggestion() -> dict:
    return {
        "assessment_engine": "deterministic",
        "methodology_status": "DETERMINISTIC_OSD_V1",
        "aspects": [
            {"aspect": dim.value, "O": None, "S": None, "D": None}
            for dim in FriesDimension
        ],
    }


@pytest.mark.parametrize(
    "edit,expected",
    [
        ({"O": 4}, {"O": 4, "S": None, "D": None}),
        ({"S": 6}, {"O": None, "S": 6, "D": None}),
        ({"D": 2}, {"O": None, "S": None, "D": 2}),
        ({"O": 4, "S": 6}, {"O": 4, "S": 6, "D": None}),
        ({"O": 4, "D": 2}, {"O": 4, "S": None, "D": 2}),
        ({"S": 6, "D": 2}, {"O": None, "S": 6, "D": 2}),
        ({"O": 4, "S": 6, "D": 2}, {"O": 4, "S": 6, "D": 2}),
    ],
)
def test_human_o_s_d_each_independently_editable(edit: dict, expected: dict) -> None:
    """Every subset of {O, S, D} is accepted; omitted fields stay None — never defaulted."""
    suggestion = _deterministic_suggestion()
    approved, human_changed = merge_review_aspects(
        suggestion, [{"aspect": "FAIRNESS", **edit}], accept_all=False
    )
    assert human_changed is True
    assert len(approved) == 1
    entry = approved[0]
    assert entry["O"] == expected["O"]
    assert entry["S"] == expected["S"]
    assert entry["D"] == expected["D"]

    finalized = to_finalized_osd_assisted(
        approved, human_review_id=1, reviewer_id=2, human_changed=human_changed,
        agent_suggestion=suggestion,
    )
    aspect = finalized["aspects"][0]
    for field in ("O", "S", "D"):
        source_key = f"{field}_source"
        if expected[field] is None:
            assert aspect[source_key] is None, f"{field} is missing — must not be tagged human"
        else:
            assert aspect[source_key] == "human", f"{field} was human-supplied — must be tagged human"


def test_human_changed_tracks_o_and_d_not_only_s() -> None:
    suggestion = _deterministic_suggestion()

    _, changed_o = merge_review_aspects(suggestion, [{"aspect": "FAIRNESS", "O": 3}], accept_all=False)
    assert changed_o is True

    _, changed_d = merge_review_aspects(suggestion, [{"aspect": "FAIRNESS", "D": 3}], accept_all=False)
    assert changed_d is True

    _, changed_s = merge_review_aspects(suggestion, [{"aspect": "FAIRNESS", "S": 3}], accept_all=False)
    assert changed_s is True


def test_clearing_a_previously_entered_value_via_a_fresh_review() -> None:
    """Each review call merges against the fixed agent baseline (never the prior
    human review) — omitting a field in a later review clears it back to None,
    it does not carry the old value forward."""
    suggestion = _deterministic_suggestion()

    first_approved, _ = merge_review_aspects(
        suggestion, [{"aspect": "FAIRNESS", "O": 4, "S": 6, "D": 8}], accept_all=False
    )
    assert first_approved[0] == {"aspect": "FAIRNESS", "O": 4, "S": 6, "D": 8}

    second_approved, second_changed = merge_review_aspects(
        suggestion, [{"aspect": "FAIRNESS", "S": 6, "D": 8}], accept_all=False
    )
    assert second_changed is True
    assert second_approved[0] == {"aspect": "FAIRNESS", "O": None, "S": 6, "D": 8}


def test_no_default_values_ever_assigned_for_omitted_fields() -> None:
    suggestion = _deterministic_suggestion()
    approved, _ = merge_review_aspects(
        suggestion, [{"aspect": "ROBUSTNESS", "S": 5}], accept_all=False
    )
    entry = approved[0]
    assert entry["O"] is None
    assert entry["D"] is None
    # Never coerced to 0, 5, or any other placeholder.
    assert entry["O"] != 0
    assert entry["D"] != 0


def test_incomplete_single_aspect_blocks_fries_but_complete_all_five_permits_it() -> None:
    suggestion = _deterministic_suggestion()

    # Only one of five aspects complete -> FRIES stays withheld.
    partial, _ = merge_review_aspects(
        suggestion, [{"aspect": "FAIRNESS", "O": 4, "S": 6, "D": 8}], accept_all=False
    )
    partial_finalized = to_finalized_osd_assisted(
        partial, human_review_id=1, reviewer_id=2, human_changed=True, agent_suggestion=suggestion
    )
    assert partial_finalized["scoring_complete"] is False
    assert partial_finalized["scoring_withheld"] is True
    assert partial_finalized["complete_aspect_count"] == 1

    # All five aspects complete -> FRIES eligible, computed via the untouched scorer.
    full_edits = [
        {"aspect": dim.value, "O": 4, "S": 6, "D": 8} for dim in FriesDimension
    ]
    full_approved, _ = merge_review_aspects(suggestion, full_edits, accept_all=False)
    full_finalized = to_finalized_osd_assisted(
        full_approved, human_review_id=1, reviewer_id=2, human_changed=True, agent_suggestion=suggestion
    )
    assert full_finalized["scoring_complete"] is True
    assert full_finalized["scoring_withheld"] is False
    assert full_finalized["complete_aspect_count"] == 5
    fries = score_from_finalized_osd(full_finalized)
    assert fries.fries_score > 0
    for dim in FriesDimension:
        assert full_finalized["aspects"][
            [a["aspect"] for a in full_finalized["aspects"]].index(dim.value)
        ]["O_source"] == "human"


def test_deterministic_accept_all_never_tags_a_fabricated_human_source() -> None:
    """accept_all on the deterministic path yields zero aspects — no O/S/D
    value exists to (mis)tag as human-sourced."""
    deterministic_suggestion = {
        "assessment_engine": "deterministic",
        "methodology_status": "DETERMINISTIC_OSD_V1",
        "aspects": [
            {"aspect": dim.value, "O": None, "S": None, "D": None}
            for dim in FriesDimension
        ],
    }
    approved, human_changed = merge_review_aspects(
        deterministic_suggestion, None, accept_all=True
    )
    assert approved == []
    finalized = to_finalized_osd_assisted(
        approved,
        human_review_id=1,
        reviewer_id=2,
        human_changed=human_changed,
        agent_suggestion=deterministic_suggestion,
    )
    assert finalized["aspects"] == []


def test_request_schema_validation() -> None:
    with pytest.raises(ValidationError):
        HumanReviewRequest(
            accept_all=True,
            aspects=[{"aspect": "SAFETY", "O": 9, "S": 9, "D": 9}],
        )
    with pytest.raises(ValidationError):
        HumanReviewRequest(accept_all=False, aspects=None)
    with pytest.raises(ValidationError):
        HumanReviewRequest(
            aspects=[
                {"aspect": "SAFETY", "O": 9, "S": 9, "D": 9},
                {"aspect": "SAFETY", "O": 1, "S": 1, "D": 1},
            ]
        )
    with pytest.raises(ValidationError):  # out of range
        HumanReviewRequest(aspects=[{"aspect": "SAFETY", "O": 11, "S": 9, "D": 9}])
    ok = HumanReviewRequest(aspects=[{"aspect": "SAFETY", "O": 0, "S": 10, "D": 9}])
    assert ok.aspects is not None and ok.aspects[0].O == 0  # veto + optimal allowed


# ---------------------------------------------------------------------------
# API workflow — review → finalize (needs Postgres)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _skip_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid Redis during API create; tests invoke the pipeline directly."""
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: None,
    )


def _create_evaluation(
    api_client: TestClient, headers: dict[str, str], *, mode: str
) -> str:
    model = api_client.post(
        "/v1/models",
        json=fries_complete_model_payload(f"org/review-{uuid.uuid4().hex[:8]}"),
        headers=headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": mode},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _create_and_run(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    *,
    mode: str,
    probe_config: dict | None = LEGACY_HEURISTIC_PROBE_CONFIG,
) -> str:
    model = api_client.post(
        "/v1/models",
        json=fries_complete_model_payload(f"org/review-{uuid.uuid4().hex[:8]}"),
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    create_payload: dict = {
        "model_id": model.json()["id"],
        "evaluation_mode": mode,
    }
    if probe_config is not None:
        create_payload["probe_config"] = probe_config
    created = api_client.post(
        "/v1/evaluations",
        json=create_payload,
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=model.json()["hf_repo_id"],
        evaluation_mode=EvaluationMode(mode),
        probe_config=probe_config or {},
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()
    return eval_id


def _reviewer_headers(
    api_client: TestClient, seeded_users: dict[str, tuple[User, str]]
) -> tuple[User, dict[str, str]]:
    reviewer, password = seeded_users["reviewer"]
    return reviewer, auth_headers_for(api_client, reviewer.email, password)


def _osd_triples(aspects: list[dict]) -> list[dict]:
    return [
        {"aspect": a["aspect"], "O": a["O"], "S": a["S"], "D": a["D"]} for a in aspects
    ]


def test_accept_all_review_then_finalize(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(api_client, admin_headers, db_session, mode="AI_ASSISTED")
    reviewer, reviewer_headers = _reviewer_headers(api_client, seeded_users)

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert detail["status"] == "AWAITING_REVIEW"
    assert detail["human_review"] is None
    agent_aspects = _osd_triples(detail["osd_agent"]["ai_suggestion"]["aspects"])

    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True, "review_rationale": "agent values look right"},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    body = review.json()
    assert body["evaluation_id"] == eval_id
    assert body["reviewer_id"] == reviewer.id
    assert body["accept_all"] is True
    assert body["human_changed"] is False
    assert body["approved_osd"]["aspects"] == agent_aspects
    assert body["review_rationale"] == "agent values look right"

    # A human_reviews row now exists — human_reviewed reflects that
    # authoritative record immediately, even pre-finalize (not derived from
    # final_scores, which doesn't exist yet either way at this point).
    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert detail["status"] == "AWAITING_REVIEW"
    assert detail["final_score"] is None
    assert detail["mode_disclosure"]["human_reviewed"] is True
    assert detail["mode_disclosure"]["disclaimer"] == ASSISTED_REVIEWED_LEGACY_DISCLAIMER
    assert detail["human_review"]["id"] == body["id"]

    expected = score_from_finalized_osd({"aspects": agent_aspects})
    for _ in range(2):  # finalize, then idempotent repeat
        finalized = api_client.post(
            f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
        )
        assert finalized.status_code == 200, finalized.text
        fin = finalized.json()
        assert fin["status"] == "FINALIZED"
        assert fin["final_score"]["fries_score"] == expected.fries_score
        assert fin["final_score"]["human_reviewed"] is True
        assert fin["final_score"]["disclaimer"] == ASSISTED_REVIEWED_LEGACY_DISCLAIMER
        assert fin["final_score"]["evaluation_mode"] == "AI_ASSISTED"
        assert fin["mode_disclosure"]["human_reviewed"] is True
        assert fin["mode_disclosure"]["disclaimer"] == ASSISTED_REVIEWED_LEGACY_DISCLAIMER
        assert fin["human_review"]["id"] == body["id"]

    row = FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id))
    assert row is not None
    assert row.finalized_osd["source"] == "human_review_assisted"
    assert row.finalized_osd["human_reviewed"] is True
    assert row.finalized_osd["human_changed"] is False
    assert row.finalized_osd["human_review_id"] == body["id"]
    assert row.finalized_osd["reviewer_id"] == reviewer.id
    assert row.finalized_osd["disclaimer"] == ASSISTED_REVIEWED_LEGACY_DISCLAIMER
    assert _osd_triples(row.finalized_osd["aspects"]) == agent_aspects


def test_edit_veto_changes_score_and_marks_human_changed(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(api_client, admin_headers, db_session, mode="AI_ASSISTED")
    _, reviewer_headers = _reviewer_headers(api_client, seeded_users)

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    agent_aspects = _osd_triples(detail["osd_agent"]["ai_suggestion"]["aspects"])
    fairness = next(a for a in agent_aspects if a["aspect"] == "FAIRNESS")

    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={
            "aspects": [
                {"aspect": "FAIRNESS", "O": 0, "S": fairness["S"], "D": fairness["D"]}
            ],
            "review_rationale": "fairness evidence shows a blocking issue — veto",
        },
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    assert review.json()["human_changed"] is True

    finalized = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert finalized.status_code == 200, finalized.text
    fin = finalized.json()

    approved = [
        {**a, "O": 0} if a["aspect"] == "FAIRNESS" else a for a in agent_aspects
    ]
    expected = score_from_finalized_osd({"aspects": approved})
    accept_all_score = score_from_finalized_osd({"aspects": agent_aspects})
    assert fin["final_score"]["fries_score"] == expected.fries_score
    assert fin["final_score"]["fries_score"] != accept_all_score.fries_score
    assert fin["final_score"]["dimension_scores"]["FAIRNESS"] == 0.0  # veto

    row = FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id))
    assert row is not None
    assert row.finalized_osd["human_changed"] is True


def test_second_review_supersedes_first(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(api_client, admin_headers, db_session, mode="AI_ASSISTED")
    _, reviewer_headers = _reviewer_headers(api_client, seeded_users)

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    agent_aspects = _osd_triples(detail["osd_agent"]["ai_suggestion"]["aspects"])

    first = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"aspects": [{"aspect": "SAFETY", "O": 1, "S": 1, "D": 1}]},
        headers=reviewer_headers,
    )
    assert first.status_code == 201, first.text
    second = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True},
        headers=reviewer_headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] > first.json()["id"]

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert detail["human_review"]["id"] == second.json()["id"]
    assert detail["human_review"]["accept_all"] is True

    finalized = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert finalized.status_code == 200, finalized.text
    expected = score_from_finalized_osd({"aspects": agent_aspects})
    assert finalized.json()["final_score"]["fries_score"] == expected.fries_score

    row = FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id))
    assert row is not None
    assert row.finalized_osd["human_review_id"] == second.json()["id"]


def test_review_conflicts(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    _, reviewer_headers = _reviewer_headers(api_client, seeded_users)
    accept_all = {"accept_all": True}

    # Autonomous evaluations never take a human review.
    autonomous_id = _create_and_run(
        api_client, admin_headers, db_session, mode="AI_AUTONOMOUS"
    )
    response = api_client.post(
        f"/v1/evaluations/{autonomous_id}/human-review",
        json=accept_all,
        headers=reviewer_headers,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ASSISTED_ONLY"

    # Assisted before AWAITING_REVIEW (pipeline not run → PENDING).
    pending_id = _create_evaluation(api_client, auth_headers, mode="AI_ASSISTED")
    response = api_client.post(
        f"/v1/evaluations/{pending_id}/human-review",
        json=accept_all,
        headers=reviewer_headers,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_READY"

    # Missing evaluation → 404.
    response = api_client.post(
        f"/v1/evaluations/{uuid.uuid4()}/human-review",
        json=accept_all,
        headers=reviewer_headers,
    )
    assert response.status_code == 404

    # After finalize the approved O/S/D is locked → ALREADY_FINALIZED.
    finalized_id = _create_and_run(
        api_client, admin_headers, db_session, mode="AI_ASSISTED"
    )
    assert (
        api_client.post(
            f"/v1/evaluations/{finalized_id}/human-review",
            json=accept_all,
            headers=reviewer_headers,
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            f"/v1/evaluations/{finalized_id}/finalize", headers=reviewer_headers
        ).status_code
        == 200
    )
    response = api_client.post(
        f"/v1/evaluations/{finalized_id}/human-review",
        json=accept_all,
        headers=reviewer_headers,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ALREADY_FINALIZED"

    # accept_all with aspects is contradictory → 422 (model validator). Last
    # assertion on purpose: RequestValidationError rolls back the test-scoped
    # transaction in the conftest get_db override, wiping seeded state.
    response = api_client.post(
        f"/v1/evaluations/{pending_id}/human-review",
        json={
            "accept_all": True,
            "aspects": [{"aspect": "SAFETY", "O": 9, "S": 9, "D": 9}],
        },
        headers=reviewer_headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_deterministic_accept_all_finalizes_without_fries(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(
        api_client,
        auth_headers,
        db_session,
        mode="AI_ASSISTED",
        probe_config={"schema_version": "v1", "assessment_engine": "deterministic"},
    )
    _, reviewer_headers = _reviewer_headers(api_client, seeded_users)

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert detail["osd_agent"]["ai_suggestion"]["assessment_engine"] == "deterministic"
    assert all(a["O"] is None for a in detail["osd_agent"]["ai_suggestion"]["aspects"])

    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    assert review.json()["approved_osd"]["aspects"] == []

    finalized = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert finalized.status_code == 200, finalized.text
    fin = finalized.json()
    assert fin["status"] == "FINALIZED"
    assert fin["final_score"] is None


def test_deterministic_full_human_osd_all_aspects_permits_fries(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    """A human filling in complete O/S/D for every required aspect makes the
    evaluation FRIES-eligible via the existing, untouched scorer — proving
    the deterministic-engine restriction to S-only has been lifted end to end."""
    eval_id = _create_and_run(
        api_client,
        auth_headers,
        db_session,
        mode="AI_ASSISTED",
        probe_config={"schema_version": "v1", "assessment_engine": "deterministic"},
    )
    _, reviewer_headers = _reviewer_headers(api_client, seeded_users)

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    dims = [a["aspect"] for a in detail["osd_agent"]["ai_suggestion"]["aspects"]]
    assert set(dims) == {d.value for d in FriesDimension}

    full_edits = [{"aspect": dim, "O": 4, "S": 6, "D": 8} for dim in dims]
    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"aspects": full_edits},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    assert review.json()["human_changed"] is True
    for entry in review.json()["approved_osd"]["aspects"]:
        assert entry["O"] == 4
        assert entry["S"] == 6
        assert entry["D"] == 8

    finalized = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert finalized.status_code == 200, finalized.text
    fin = finalized.json()
    assert fin["status"] == "FINALIZED"
    assert fin["final_score"] is not None
    expected = score_from_finalized_osd(
        {"aspects": [{"aspect": dim, "O": 4, "S": 6, "D": 8} for dim in dims]}
    )
    assert fin["final_score"]["fries_score"] == expected.fries_score
    assert fin["final_score"]["human_reviewed"] is True

    row = FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id))
    assert row is not None
    for entry in row.finalized_osd["aspects"]:
        assert entry["O_source"] == "human"
        assert entry["S_source"] == "human"
        assert entry["D_source"] == "human"

    # P3-A regression: a real FRIES score exists here (fin["final_score"] is
    # not None, asserted above) — the disclosure must never simultaneously
    # claim FRIES is withheld or that O/S/D "were not generated".
    disclosure = fin["mode_disclosure"]
    assert disclosure["fries_status"] == "scored"
    assert "withheld" not in disclosure["disclaimer"].lower()
    assert "were not generated" not in disclosure["disclaimer"].lower()
    assert "human" in disclosure["disclaimer"].lower()

    # A fresh GET (not just the finalize response) must be consistent too —
    # this is what actually renders on ModeDisclosureBanner.
    refetched = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    re_disclosure = refetched["mode_disclosure"]
    assert re_disclosure["fries_status"] == "scored"
    assert "withheld" not in re_disclosure["disclaimer"].lower()
    assert "were not generated" not in re_disclosure["disclaimer"].lower()


def test_deterministic_human_s_still_withholds_fries(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(
        api_client,
        auth_headers,
        db_session,
        mode="AI_ASSISTED",
        probe_config={"schema_version": "v1", "assessment_engine": "deterministic"},
    )
    _, reviewer_headers = _reviewer_headers(api_client, seeded_users)

    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"aspects": [{"aspect": "FAIRNESS", "S": 7}]},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    assert review.json()["human_changed"] is True
    assert review.json()["approved_osd"]["aspects"] == [
        {"aspect": "FAIRNESS", "O": None, "S": 7, "D": None}
    ]

    finalized = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["final_score"] is None

    # Case 2 (incomplete O/S/D): fries_status must correctly say withheld,
    # and the disclaimer must never claim a scored/human-completed state
    # that never happened. human_reviewed is derived from the actual
    # human_reviews record (not final_scores, which has no row when
    # withheld) — a review genuinely happened here, so human_reviewed=True
    # and the reviewed-but-incomplete disclaimer is shown, never the
    # pre-review "awaiting" text (fixed post-item-8 live validation).
    disclosure = finalized.json()["mode_disclosure"]
    assert disclosure["fries_status"] == "withheld"
    assert disclosure["human_reviewed"] is True
    assert "has been scored" not in disclosure["disclaimer"].lower()
    assert "human-entered for every required aspect" not in disclosure["disclaimer"].lower()
    assert "awaiting human review" not in disclosure["disclaimer"].lower()
    assert "missing a complete human o/s/d triple" in disclosure["disclaimer"].lower()


# --- mode_disclosure.human_reviewed regression (audit item 8 defect fix) ---
#
# human_reviewed must come from the actual human_reviews record, never from
# final_scores (which has no row at all when FRIES is withheld).


def test_no_review_shows_awaiting_disclaimer(
    api_client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(api_client, admin_headers, db_session, mode="AI_ASSISTED")

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=admin_headers)
    disclosure = detail.json()["mode_disclosure"]
    assert disclosure["human_reviewed"] is False
    assert disclosure["disclaimer"] == ASSISTED_AWAITING_DISCLAIMER


def test_review_submitted_incomplete_osd_shows_reviewed_disclaimer(
    api_client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(
        api_client,
        admin_headers,
        db_session,
        mode="AI_ASSISTED",
        probe_config={"schema_version": "v1", "assessment_engine": "deterministic"},
    )
    _, reviewer_headers = _reviewer_headers(api_client, seeded_users)

    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"aspects": [{"aspect": "FAIRNESS", "O": 8, "S": 7}]},  # D left blank
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text

    finalized = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert finalized.status_code == 200, finalized.text
    body = finalized.json()

    # FRIES remains withheld — the fix only corrects the disclaimer's
    # human_reviewed flag/wording, never FRIES logic.
    assert body["final_score"] is None
    disclosure = body["mode_disclosure"]
    assert disclosure["fries_status"] == "withheld"
    assert disclosure["human_reviewed"] is True
    assert disclosure["disclaimer"] == ASSISTED_REVIEWED_DISCLAIMER


def test_review_submitted_complete_osd_shows_scored_disclaimer(
    api_client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(
        api_client,
        admin_headers,
        db_session,
        mode="AI_ASSISTED",
        probe_config={"schema_version": "v1", "assessment_engine": "deterministic"},
    )
    _, reviewer_headers = _reviewer_headers(api_client, seeded_users)

    aspects = [
        {"aspect": d.value, "O": 5, "S": 5, "D": 5}
        for d in FriesDimension
    ]
    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"aspects": aspects},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text

    finalized = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert finalized.status_code == 200, finalized.text
    body = finalized.json()

    assert body["final_score"] is not None
    disclosure = body["mode_disclosure"]
    assert disclosure["fries_status"] == "scored"
    assert disclosure["human_reviewed"] is True
    assert disclosure["disclaimer"] == ASSISTED_REVIEWED_SCORED_DISCLAIMER
