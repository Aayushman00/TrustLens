"""Pipeline lifecycle — assisted / autonomous / failure (Phase 7–16)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.final_score import FinalScoreRepository
from app.db.repositories.osd_agent_output import OsdAgentOutputRepository
from app.schemas.internal import EvaluateModelPayload
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.fakes import FakeEvidenceStore


@pytest.fixture(autouse=True)
def _skip_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid Redis during API create; lifecycle tests invoke the pipeline directly."""
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: None,
    )


def _create_model_and_eval(
    api_client: TestClient,
    auth_headers: dict[str, str],
    *,
    mode: str,
) -> tuple[str, str, str]:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/life-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    hf_repo_id = model.json()["hf_repo_id"]
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model_id, "evaluation_mode": mode},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "PENDING"
    return created.json()["id"], hf_repo_id, mode


def test_autonomous_pipeline_finalized(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id, hf_repo_id, _ = _create_model_and_eval(
        api_client, auth_headers, mode="AI_AUTONOMOUS"
    )
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    got = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "FINALIZED"
    assert body["probe_progress"] == {"completed": 5, "total": 5}

    # Phase 16: agent row + final_scores written on the Autonomous path.
    osd_row = OsdAgentOutputRepository(db_session).latest_for_evaluation(
        uuid.UUID(eval_id)
    )
    assert osd_row is not None
    assert osd_row.ai_suggestion["methodology_status"] == "PROPOSED_REQUIRES_VALIDATION"
    assert len(osd_row.ai_suggestion["aspects"]) == 5
    assert osd_row.ai_confidence is not None
    assert "PROPOSED" in (osd_row.rationale or "")

    final = FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id))
    assert final is not None
    assert 0.0 <= final.fries_score <= 10.0
    assert set(final.dimension_scores) == {
        "FAIRNESS",
        "ROBUSTNESS",
        "INTEGRITY",
        "EXPLAINABILITY",
        "SAFETY",
    }
    assert final.finalized_osd["methodology_status"] == "PROPOSED_REQUIRES_VALIDATION"
    assert final.evaluation_mode == EvaluationMode.AI_AUTONOMOUS

    # API detail surfaces both (Phase 16).
    assert body["osd_agent"] is not None
    assert body["osd_agent"]["methodology_status"] == "PROPOSED_REQUIRES_VALIDATION"
    assert len(body["osd_agent"]["ai_suggestion"]["aspects"]) == 5
    assert body["final_score"] is not None
    assert body["final_score"]["fries_score"] == final.fries_score
    assert body["final_score"]["evaluation_mode"] == "AI_AUTONOMOUS"


def test_assisted_pipeline_awaiting_review(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id, hf_repo_id, _ = _create_model_and_eval(
        api_client, auth_headers, mode="AI_ASSISTED"
    )
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=hf_repo_id,
        evaluation_mode=EvaluationMode.AI_ASSISTED,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    got = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "AWAITING_REVIEW"
    assert body["probe_progress"]["completed"] == 5
    assert body["probe_progress"]["total"] == 5

    # Phase 16: Assisted stores the agent suggestion but never final_scores
    # (human finalize is Phase 18).
    osd_row = OsdAgentOutputRepository(db_session).latest_for_evaluation(
        uuid.UUID(eval_id)
    )
    assert osd_row is not None
    assert osd_row.ai_suggestion["methodology_status"] == "PROPOSED_REQUIRES_VALIDATION"
    assert FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id)) is None
    assert body["osd_agent"] is not None
    assert body["final_score"] is None


def test_pipeline_model_ref_mismatch_fails(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id, _, _ = _create_model_and_eval(
        api_client, auth_headers, mode="AI_AUTONOMOUS"
    )
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref="org/definitely-wrong-ref",
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    row = EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id))
    assert row is not None
    assert row.status == EvaluationStatus.FAILED
