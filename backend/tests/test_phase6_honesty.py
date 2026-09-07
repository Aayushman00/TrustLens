"""Phase 6 freeze — product honesty (copy, flags, withheld FRIES, engine gate)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.repositories.probe_result import ProbeResultRepository
from app.schemas.internal import EvaluateModelPayload
from app.schemas.modes import DETERMINISTIC_ABSTAIN_DISCLAIMER
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.conftest import LEGACY_HEURISTIC_PROBE_CONFIG
from tests.fakes import FakeEvidenceStore, FakeReportStore


@pytest.fixture(autouse=True)
def _skip_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: None,
    )


@pytest.fixture
def report_store(monkeypatch: pytest.MonkeyPatch) -> FakeReportStore:
    store = FakeReportStore()
    monkeypatch.setattr(
        "app.services.report_service.get_report_store", lambda settings: store
    )
    return store


def _create_eval(
    api_client: TestClient,
    headers: dict[str, str],
    *,
    mode: str = "AI_AUTONOMOUS",
    probe_config: dict | None = None,
) -> tuple[str, str]:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/p6-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert model.status_code == 201, model.text
    payload: dict = {"model_id": model.json()["id"], "evaluation_mode": mode}
    if probe_config is not None:
        payload["probe_config"] = probe_config
    created = api_client.post("/v1/evaluations", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()["id"], model.json()["hf_repo_id"]


def _run(
    db_session: Session, eval_id: str, hf_repo_id: str, mode: str = "AI_AUTONOMOUS"
) -> None:
    run_evaluation_pipeline(
        db_session,
        EvaluateModelPayload(
            evaluation_id=uuid.UUID(eval_id),
            model_ref=hf_repo_id,
            evaluation_mode=EvaluationMode(mode),
        ),
        evidence_store=FakeEvidenceStore(),
    )
    db_session.flush()


def test_default_autonomous_withheld_honest_copy(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id, hf_repo_id = _create_eval(api_client, auth_headers)
    assert api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()[
        "probe_config"
    ]["assessment_engine"] == "deterministic"
    _run(db_session, eval_id, hf_repo_id)

    body = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert body["status"] == "FINALIZED"
    assert body["final_score"] is None
    disclosure = body["mode_disclosure"]
    assert disclosure["scoring_withheld"] is True
    assert disclosure["fries_status"] == "withheld"
    assert disclosure["assessment_engine"] == "deterministic"
    assert disclosure["disclaimer"] == DETERMINISTIC_ABSTAIN_DISCLAIMER
    lowered = disclosure["disclaimer"].lower()
    assert "generated automatically" not in lowered
    assert "ai-proposed" not in lowered
    aspects = body["osd_agent"]["ai_suggestion"]["aspects"]
    assert len(aspects) == 5
    assert all(a["O"] is None and a["S"] is None and a["D"] is None for a in aspects)


def test_detail_probes_length_five_with_evidence_fields(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id, hf_repo_id = _create_eval(api_client, auth_headers)
    _run(db_session, eval_id, hf_repo_id)
    body = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    probes = body["probes"]
    assert probes is not None
    assert len(probes) == 5
    by_dim = {row["dimension"]: row for row in probes}
    for dim in ("FAIRNESS", "ROBUSTNESS", "INTEGRITY", "EXPLAINABILITY", "SAFETY"):
        assert dim in by_dim
        row = by_dim[dim]
        assert "status" in row
        assert "flags" in row
        assert "claim_boundary" in row
    listed = api_client.get("/v1/evaluations", headers=auth_headers).json()["items"]
    match = next(item for item in listed if item["id"] == eval_id)
    assert match.get("probes") in (None, [])


def test_flags_persisted_on_all_five_probes(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id, hf_repo_id = _create_eval(api_client, auth_headers)
    _run(db_session, eval_id, hf_repo_id)
    rows = ProbeResultRepository(db_session).list_for_evaluation(uuid.UUID(eval_id))
    assert len(rows) == 5
    for row in rows:
        assert "flags" in (row.metric_values or {})
        assert isinstance(row.metric_values["flags"], list)


def test_report_409_withheld_not_unfinalized_wording(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    report_store: FakeReportStore,
) -> None:
    eval_id, hf_repo_id = _create_eval(api_client, auth_headers)
    _run(db_session, eval_id, hf_repo_id)
    response = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "NOT_FINALIZED"
    assert body["details"]["status"] == "FINALIZED"
    assert body["details"]["scoring_withheld"] is True
    message = body["message"].lower()
    assert "not finalized yet" not in message
    assert "finalize first" not in message
    assert "withheld" in message
    assert report_store.objects == {}


def test_extra_heuristic_ignored_stays_deterministic(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id, hf_repo_id = _create_eval(
        api_client,
        auth_headers,
        probe_config={
            "schema_version": "v1",
            "extra": {"assessment_engine": "heuristic"},
        },
    )
    created = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert created["probe_config"]["assessment_engine"] == "deterministic"
    _run(db_session, eval_id, hf_repo_id)
    body = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert body["osd_agent"]["ai_suggestion"]["assessment_engine"] == "deterministic"
    assert body["final_score"] is None


def test_researcher_legacy_403_admin_legacy_ok(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/p6-legacy-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    denied = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model.json()["id"],
            "evaluation_mode": "AI_AUTONOMOUS",
            "probe_config": LEGACY_HEURISTIC_PROBE_CONFIG,
        },
        headers=auth_headers,
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "FORBIDDEN"

    admin_model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/p6-legacy-a-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    allowed = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": admin_model.json()["id"],
            "evaluation_mode": "AI_AUTONOMOUS",
            "probe_config": LEGACY_HEURISTIC_PROBE_CONFIG,
        },
        headers=admin_headers,
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["probe_config"]["assessment_engine"] == "legacy_heuristic"
