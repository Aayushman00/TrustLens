"""Phase 8, Task 8.1 — confirms every pre-existing Evaluation/Report created
before this migration still reads back correctly: correct
methodology_version backfill, correct legacy (non-excluding) confidence
semantics, correct null methodology_version on a pre-migration report read.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus, FriesDimension
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.report import ReportRepository
from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION
from tests.fakes import FakeReportStore


def test_pre_migration_evaluation_has_legacy_methodology_version(
    db_session: Session, seeded_model
) -> None:
    """A legacy-path Evaluation row, inserted the way create_evaluation
    always has (never setting methodology_version explicitly), must still
    pick up LEGACY_METHODOLOGY_VERSION from the DB server_default."""
    row = EvaluationRepository(db_session).create(
        model_id=seeded_model.id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    db_session.flush()
    assert row.methodology_version == LEGACY_METHODOLOGY_VERSION


def _create_model(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/legacy-readback-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_pre_migration_evaluation_detail_read_unchanged(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    """A legacy evaluation's confidence_summary must still compute — and
    computes under legacy (non-excluding) semantics, since it carries
    LEGACY_METHODOLOGY_VERSION — exactly as it did before this migration."""
    from app.db.repositories.probe_result import ProbeResultRepository

    model_id = _create_model(api_client, auth_headers)
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model_id, "evaluation_mode": "AI_AUTONOMOUS"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]

    repo = ProbeResultRepository(db_session)
    for dim in FriesDimension:
        repo.create(
            evaluation_id=uuid.UUID(eval_id),
            dimension=dim,
            metric_values={
                "confidence_factors": {
                    "data_quality": 0.6,
                    "probe_reliability": 1.0,
                    "evidence_completeness": 1.0,
                    "combined": 0.6,
                }
            },
            confidence=0.6,
            evidence_refs=[
                {
                    "evidence_id": uuid.uuid4().hex,
                    "uri": "s3://trustlens/evidence/x.json",
                    "hash": f"sha256:{'a' * 64}",
                    "content_type": "application/json",
                    "probe_name": dim.value.lower(),
                }
            ],
        )
    db_session.flush()

    got = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["confidence_summary"] is not None
    assert set(got.json()["confidence_summary"]["by_dimension"]) == {d.value for d in FriesDimension}


def test_pre_migration_report_read_returns_null_methodology_version(
    db_session: Session, seeded_model, monkeypatch
) -> None:
    """A Report row/blob written before methodology_version existed on the
    report schema must read back with methodology_version=None — never
    retroactively backfilled or rewritten."""
    from app.services.report_service import ReportService

    store = FakeReportStore()
    monkeypatch.setattr("app.services.report_service.get_report_store", lambda settings: store)

    evaluation = EvaluationRepository(db_session).create(
        model_id=seeded_model.id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        status=EvaluationStatus.FINALIZED,
    )
    db_session.flush()

    # Deliberately the *old* report schema — no "methodology_version" key at
    # all, simulating a report.json blob generated before this field existed.
    legacy_report_json = {
        "schema_version": "report_v1",
        "report_version": 1,
        "generated_at": "2025-01-01T00:00:00Z",
        "score": {"fries_score": 0.72},
        "mode_disclosure": {
            "evaluation_mode": "AI_AUTONOMOUS",
            "human_reviewed": False,
            "disclaimer": "legacy disclaimer",
            "methodology_status": "PROPOSED_REQUIRES_VALIDATION",
        },
    }
    import json as json_mod

    data = json_mod.dumps(legacy_report_json).encode("utf-8")
    json_uri, _ = store.put_report(
        evaluation_id=evaluation.id,
        version=1,
        data=data,
        content_type="application/json",
        filename="report.json",
    )
    ReportRepository(db_session).create(
        evaluation_id=evaluation.id,
        json_uri=json_uri,
        pdf_uri=None,
        version=1,
    )
    db_session.flush()

    report = ReportService(db_session).get_report(evaluation.id)
    assert report.methodology_version is None
