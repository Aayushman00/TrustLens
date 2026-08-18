"""Phase 17 finalize policy + mode disclosures (ADR 0011)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.models import User
from app.db.repositories.final_score import FinalScoreRepository
from app.schemas.internal import EvaluateModelPayload
from app.schemas.modes import (
    ASSISTED_AWAITING_DISCLAIMER,
    ASSISTED_REVIEWED_DISCLAIMER,
    AUTONOMOUS_DISCLAIMER,
)
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.conftest import auth_headers_for
from tests.fakes import FakeEvidenceStore


@pytest.fixture(autouse=True)
def _skip_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid Redis during API create; tests invoke the pipeline directly."""
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: None,
    )


def _create_and_run(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    *,
    mode: str,
) -> str:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/fin-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": mode},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=model.json()["hf_repo_id"],
        evaluation_mode=EvaluationMode(mode),
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()
    return eval_id


def test_autonomous_finalize_idempotent_with_disclosure(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_AUTONOMOUS")

    for _ in range(2):  # idempotent — same 200 on repeat
        response = api_client.post(
            f"/v1/evaluations/{eval_id}/finalize", headers=auth_headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "FINALIZED"
        assert body["final_score"] is not None
        assert body["final_score"]["human_reviewed"] is False
        assert body["final_score"]["disclaimer"] == AUTONOMOUS_DISCLAIMER
        assert body["mode_disclosure"]["evaluation_mode"] == "AI_AUTONOMOUS"
        assert body["mode_disclosure"]["human_reviewed"] is False
        assert body["mode_disclosure"]["disclaimer"] == AUTONOMOUS_DISCLAIMER
        assert (
            body["mode_disclosure"]["methodology_status"]
            == "PROPOSED_REQUIRES_VALIDATION"
        )

    # Persisted finalized_osd carries the disclosure (Phase 17).
    row = FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id))
    assert row is not None
    assert row.finalized_osd["human_reviewed"] is False
    assert row.finalized_osd["evaluation_mode"] == "AI_AUTONOMOUS"
    assert row.finalized_osd["disclaimer"] == AUTONOMOUS_DISCLAIMER

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers)
    assert detail.json()["mode_disclosure"]["disclaimer"] == AUTONOMOUS_DISCLAIMER


def test_autonomous_finalize_failed_evaluation_409(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/fin-fail-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": "AI_AUTONOMOUS"},
        headers=auth_headers,
    )
    eval_id = created.json()["id"]
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref="org/definitely-wrong-ref",
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    response = api_client.post(f"/v1/evaluations/{eval_id}/finalize", headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["code"] == "FAILED_EVALUATION"


def test_assisted_finalize_review_required_then_writes(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_ASSISTED")

    # Detail carries the awaiting disclaimer while unreviewed.
    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers)
    disclosure = detail.json()["mode_disclosure"]
    assert detail.json()["status"] == "AWAITING_REVIEW"
    assert detail.json()["final_score"] is None
    assert disclosure["human_reviewed"] is False
    assert disclosure["disclaimer"] == ASSISTED_AWAITING_DISCLAIMER

    reviewer, reviewer_pw = seeded_users["reviewer"]
    reviewer_headers = auth_headers_for(api_client, reviewer.email, reviewer_pw)

    response = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "REVIEW_REQUIRED"
    assert body["details"]["phase"] == 18
    assert "human-review" in body["details"]["next"]

    # With a review, finalize writes the human-approved FRIES result (Phase 18).
    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    response = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FINALIZED"
    assert body["final_score"]["human_reviewed"] is True
    assert body["final_score"]["disclaimer"] == ASSISTED_REVIEWED_DISCLAIMER
    assert body["mode_disclosure"]["human_reviewed"] is True
    assert body["mode_disclosure"]["disclaimer"] == ASSISTED_REVIEWED_DISCLAIMER
