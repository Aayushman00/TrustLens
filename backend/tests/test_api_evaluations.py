"""Evaluation API CRUD tests (requires Postgres).

Create returns PENDING and enqueues asynchronously; with REDIS_URL unset in
host tests, enqueue is a no-op and status stays PENDING until a worker runs.
"""

from __future__ import annotations

import math
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _create_model(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/eval-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_create_evaluation_for_model(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    model_id = _create_model(api_client, auth_headers)
    response = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model_id,
            "evaluation_mode": "AI_AUTONOMOUS",
            "task": "text-classification",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["model_id"] == model_id
    assert body["status"] == "PENDING"
    assert body["evaluation_mode"] == "AI_AUTONOMOUS"
    assert body["is_published"] is False
    assert body["created_by"] is not None

    got = api_client.get(f"/v1/evaluations/{body['id']}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]
    assert got.json()["probe_progress"] == {"completed": 0, "total": 5}
    # Phase 15: no probe rows yet → no confidence summary.
    assert got.json()["confidence_summary"] is None
    # Phase 16: no agent run yet → no osd_agent / final_score.
    assert got.json()["osd_agent"] is None
    assert got.json()["final_score"] is None
    # Phase 17: mode_disclosure is always present on detail reads.
    disclosure = got.json()["mode_disclosure"]
    assert disclosure is not None
    assert disclosure["human_reviewed"] is False
    assert disclosure["methodology_status"] == "PROPOSED_REQUIRES_VALIDATION"
    assert disclosure["disclaimer"]


def test_get_evaluation_confidence_summary(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    """Detail returns confidence_summary once probe rows exist (Phase 15)."""
    from app.db.enums import FriesDimension
    from app.db.repositories.probe_result import ProbeResultRepository

    model_id = _create_model(api_client, auth_headers)
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model_id, "evaluation_mode": "AI_AUTONOMOUS"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]

    confidences = {
        FriesDimension.FAIRNESS: 0.55,
        FriesDimension.ROBUSTNESS: 0.40,
        FriesDimension.INTEGRITY: 0.91,
        FriesDimension.EXPLAINABILITY: 0.80,
        FriesDimension.SAFETY: 0.70,
    }
    repo = ProbeResultRepository(db_session)
    for dim, confidence in confidences.items():
        repo.create(
            evaluation_id=uuid.UUID(eval_id),
            dimension=dim,
            metric_values={
                "confidence_factors": {
                    "data_quality": confidence,
                    "probe_reliability": 1.0,
                    "evidence_completeness": 1.0,
                    "combined": confidence,
                }
            },
            confidence=confidence,
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
    assert got.status_code == 200, got.text
    summary = got.json()["confidence_summary"]
    assert summary is not None
    assert summary["method"] == "geometric_mean_v1"
    assert summary["proposed_calibration"] is True
    assert set(summary["by_dimension"]) == {d.value for d in confidences}
    for dim, confidence in confidences.items():
        assert math.isclose(summary["by_dimension"][dim.value], confidence, abs_tol=1e-4)
    expected_overall = math.exp(
        sum(math.log(v) for v in confidences.values()) / len(confidences)
    )
    assert math.isclose(summary["overall"], expected_overall, abs_tol=1e-3)
    assert "not correctness" in summary["note"]

    # List endpoint omits the summary (null field).
    listed = api_client.get("/v1/evaluations", headers=auth_headers)
    assert listed.status_code == 200
    item = next(i for i in listed.json()["items"] if i["id"] == eval_id)
    assert item["confidence_summary"] is None


def test_create_evaluation_bad_model_404(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    response = api_client.post(
        "/v1/evaluations",
        json={"model_id": 999999002, "evaluation_mode": "AI_ASSISTED"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_list_evaluations_filter_by_status(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    model_id = _create_model(api_client, auth_headers)
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model_id, "evaluation_mode": "AI_ASSISTED"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    eval_id = created.json()["id"]

    listed = api_client.get("/v1/evaluations?status=PENDING", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["id"] == eval_id for item in listed.json()["items"])

    empty = api_client.get("/v1/evaluations?status=FINALIZED", headers=auth_headers)
    assert empty.status_code == 200
    assert all(item["id"] != eval_id for item in empty.json()["items"])


def test_list_evaluations_without_token_401(api_client: TestClient) -> None:
    response = api_client.get("/v1/evaluations")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
