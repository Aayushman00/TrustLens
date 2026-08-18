"""Phase 19 — report API: auth, guards, auto-generate, versioning (needs Postgres).

MinIO is replaced by FakeReportStore (append-only asserted); the evaluation
pipeline runs inline with FakeEvidenceStore, as in test_human_review.py.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.models import User
from app.schemas.internal import EvaluateModelPayload
from app.schemas.modes import ASSISTED_REVIEWED_DISCLAIMER, AUTONOMOUS_DISCLAIMER
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.conftest import auth_headers_for
from tests.fakes import FakeEvidenceStore, FakeReportStore


@pytest.fixture(autouse=True)
def _skip_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid Redis during API create; tests invoke the pipeline directly."""
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: None,
    )


@pytest.fixture
def report_store(monkeypatch: pytest.MonkeyPatch) -> FakeReportStore:
    """In-memory store injected into ReportService's default factory."""
    store = FakeReportStore()
    monkeypatch.setattr(
        "app.services.report_service.get_report_store", lambda settings: store
    )
    return store


def _create_and_run(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    *,
    mode: str,
) -> str:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/report-api-{uuid.uuid4().hex[:8]}"},
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


def _review_and_finalize(
    api_client: TestClient,
    seeded_users: dict[str, tuple[User, str]],
    eval_id: str,
) -> None:
    reviewer, password = seeded_users["reviewer"]
    headers = auth_headers_for(api_client, reviewer.email, password)
    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True},
        headers=headers,
    )
    assert review.status_code == 201, review.text
    finalized = api_client.post(f"/v1/evaluations/{eval_id}/finalize", headers=headers)
    assert finalized.status_code == 200, finalized.text


def test_reports_require_auth(api_client: TestClient) -> None:
    some_id = uuid.uuid4()
    assert api_client.get(f"/v1/reports/{some_id}").status_code == 401
    assert api_client.post(f"/v1/reports/{some_id}/generate").status_code == 401


def test_report_unknown_evaluation_404(
    api_client: TestClient,
    auth_headers: dict[str, str],
    report_store: FakeReportStore,
) -> None:
    response = api_client.get(f"/v1/reports/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_report_not_finalized_409(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    report_store: FakeReportStore,
) -> None:
    # Assisted stops at AWAITING_REVIEW — no final_scores row yet.
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_ASSISTED")

    for method, url in (
        ("GET", f"/v1/reports/{eval_id}"),
        ("POST", f"/v1/reports/{eval_id}/generate"),
    ):
        response = api_client.request(method, url, headers=auth_headers)
        assert response.status_code == 409, response.text
        body = response.json()
        assert body["code"] == "NOT_FINALIZED"
        assert body["details"]["status"] == "AWAITING_REVIEW"
    assert report_store.objects == {}


def test_autonomous_get_auto_generates_v1(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    report_store: FakeReportStore,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_AUTONOMOUS")

    response = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["evaluation_id"] == eval_id
    assert body["version"] == 1
    assert body["json_uri"] == f"s3://trustlens/reports/{eval_id}/v1/report.json"
    assert body["json_hash"].startswith("sha256:")
    assert body["fries_score"] > 0
    # PDF is optional: absent on hosts without WeasyPrint OS libs.
    assert body["pdf_uri"] in (None, f"s3://trustlens/reports/{eval_id}/v1/report.pdf")

    report = body["report_json"]
    assert report["schema_version"] == "report_v1"
    assert report["report_version"] == 1
    assert report["mode_disclosure"]["evaluation_mode"] == "AI_AUTONOMOUS"
    assert report["mode_disclosure"]["human_reviewed"] is False
    assert report["mode_disclosure"]["disclaimer"] == AUTONOMOUS_DISCLAIMER
    assert report["score"]["score_type"] == "original_FRIES"
    assert len(report["probes"]) == 5

    stored_key = f"reports/{eval_id}/v1/report.json"
    assert stored_key in report_store.objects

    # Second GET serves the stored artifact — same version, no new objects.
    objects_before = dict(report_store.objects)
    again = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["version"] == 1
    assert again.json()["report_json"] == report
    assert report_store.objects == objects_before


def test_assisted_report_has_reviewed_disclosure(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
    report_store: FakeReportStore,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_ASSISTED")
    _review_and_finalize(api_client, seeded_users, eval_id)

    response = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode_disclosure"]["evaluation_mode"] == "AI_ASSISTED"
    assert body["mode_disclosure"]["human_reviewed"] is True
    assert body["mode_disclosure"]["disclaimer"] == ASSISTED_REVIEWED_DISCLAIMER
    report = body["report_json"]
    assert report["human_review"] is not None
    assert report["score"]["finalized_osd"]["source"] == "human_review_assisted"


def test_post_generate_bumps_version_append_only(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    report_store: FakeReportStore,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_AUTONOMOUS")

    first = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["version"] == 1

    regen = api_client.post(f"/v1/reports/{eval_id}/generate", headers=auth_headers)
    assert regen.status_code == 201, regen.text
    body = regen.json()
    assert body["version"] == 2
    assert body["json_uri"] == f"s3://trustlens/reports/{eval_id}/v2/report.json"
    assert body["report_json"]["report_version"] == 2

    # Append-only: v1 artifacts still present next to v2 (FakeReportStore
    # raises on any overwrite attempt).
    assert f"reports/{eval_id}/v1/report.json" in report_store.objects
    assert f"reports/{eval_id}/v2/report.json" in report_store.objects

    # GET now returns the latest version.
    latest = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["version"] == 2


def test_storage_unconfigured_503(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_AUTONOMOUS")
    monkeypatch.setattr(
        "app.services.report_service.get_report_store", lambda settings: None
    )
    response = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
