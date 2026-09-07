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
from app.osd.base import METHODOLOGY_STATUS_DETERMINISTIC
from app.schemas.internal import EvaluateModelPayload
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.conftest import LEGACY_HEURISTIC_PROBE_CONFIG, fries_complete_model_payload
from tests.fakes import FakeEvidenceStore


@pytest.fixture(autouse=True)
def _complete_fries_probes(
    evaluated_robustness: None,
    evaluated_fairness: None,
) -> None:
    """These journeys assert a full FRIES number; supply EVALUATED probe evidence."""
    return


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
    probe_config: dict | None = None,
) -> tuple[str, str, str]:
    model = api_client.post(
        "/v1/models",
        json=fries_complete_model_payload(f"org/life-{uuid.uuid4().hex[:8]}"),
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    hf_repo_id = model.json()["hf_repo_id"]
    payload: dict = {"model_id": model_id, "evaluation_mode": mode}
    if probe_config is not None:
        payload["probe_config"] = probe_config
    created = api_client.post(
        "/v1/evaluations",
        json=payload,
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "PENDING"
    if probe_config is None:
        assert created.json()["probe_config"]["assessment_engine"] == "deterministic"
    return created.json()["id"], hf_repo_id, mode


def test_autonomous_pipeline_finalized_scoring_withheld(
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

    osd_row = OsdAgentOutputRepository(db_session).latest_for_evaluation(
        uuid.UUID(eval_id)
    )
    assert osd_row is not None
    assert osd_row.ai_suggestion["methodology_status"] == METHODOLOGY_STATUS_DETERMINISTIC
    assert osd_row.ai_suggestion["assessment_engine"] == "deterministic"
    assert osd_row.ai_suggestion["scoring_withheld"] is True
    assert len(osd_row.ai_suggestion["aspects"]) == 5
    assert all(a["O"] is None for a in osd_row.ai_suggestion["aspects"])
    assert osd_row.ai_confidence is not None
    assert "O unavailable" in (osd_row.rationale or "")

    assert FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id)) is None
    assert body["osd_agent"] is not None
    assert body["osd_agent"]["methodology_status"] == METHODOLOGY_STATUS_DETERMINISTIC
    assert body["final_score"] is None


def test_autonomous_legacy_heuristic_still_scores(
    api_client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id, hf_repo_id, _ = _create_model_and_eval(
        api_client,
        admin_headers,
        mode="AI_AUTONOMOUS",
        probe_config=LEGACY_HEURISTIC_PROBE_CONFIG,
    )
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config=LEGACY_HEURISTIC_PROBE_CONFIG,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    final = FinalScoreRepository(db_session).get_for_evaluation(uuid.UUID(eval_id))
    assert final is not None
    assert 0.0 <= final.fries_score <= 10.0


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

    osd_row = OsdAgentOutputRepository(db_session).latest_for_evaluation(
        uuid.UUID(eval_id)
    )
    assert osd_row is not None
    assert osd_row.ai_suggestion["methodology_status"] == METHODOLOGY_STATUS_DETERMINISTIC
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


def test_deterministic_pipeline_never_calls_heuristic_agent(
    monkeypatch: pytest.MonkeyPatch,
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    evaluated_robustness: None,
    evaluated_fairness: None,
) -> None:
    heuristic_calls: list[object] = []

    class _SpyHeuristic:
        def propose(self, ctx: object) -> object:
            heuristic_calls.append(ctx)
            raise AssertionError("HeuristicOSDAgent must not run on default path")

    monkeypatch.setattr(
        "app.tasks.evaluate_pipeline.HeuristicOSDAgent",
        _SpyHeuristic,
    )
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

    assert heuristic_calls == []
    osd_row = OsdAgentOutputRepository(db_session).latest_for_evaluation(uuid.UUID(eval_id))
    assert osd_row is not None
    assert osd_row.ai_suggestion["assessment_engine"] == "deterministic"
