"""Phase 22 — opt-in publish/unpublish + published-only leaderboard (needs Postgres).

Pipeline runs inline with FakeEvidenceStore (pattern from test_api_reports.py);
publish is a pure DB flip, so no MinIO fake is needed here.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.enums import EvaluationMode, UserRole
from app.db.models import User
from app.db.repositories.report import ReportRepository
from app.db.repositories.user import UserRepository
from app.schemas.internal import EvaluateModelPayload
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
    task: str | None = None,
    dataset: str | None = None,
) -> str:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/leaderboard-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    body: dict = {"model_id": model.json()["id"], "evaluation_mode": mode}
    if task is not None:
        body["task"] = task
    if dataset is not None:
        body["dataset"] = dataset
    created = api_client.post("/v1/evaluations", json=body, headers=auth_headers)
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


def _publish(api_client: TestClient, headers: dict[str, str], eval_id: str) -> dict:
    response = api_client.post(f"/v1/evaluations/{eval_id}/publish", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _listed_ids(api_client: TestClient, headers: dict[str, str], query: str = "") -> list[str]:
    response = api_client.get(f"/v1/leaderboard{query}", headers=headers)
    assert response.status_code == 200, response.text
    return [entry["evaluation_id"] for entry in response.json()["items"]]


def test_leaderboard_requires_auth(api_client: TestClient) -> None:
    assert api_client.get("/v1/leaderboard").status_code == 401


def test_finalized_unpublished_never_listed(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_AUTONOMOUS")

    response = api_client.get("/v1/leaderboard", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert eval_id not in [entry["evaluation_id"] for entry in body["items"]]
    # No task filter → non-comparability note present.
    assert body["note"] and "not directly comparable" in body["note"]


def test_publish_appears_unpublish_disappears(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(
        api_client, auth_headers, db_session, mode="AI_AUTONOMOUS", task="sentiment"
    )

    published = _publish(api_client, auth_headers, eval_id)
    assert published["is_published"] is True
    assert published["published_at"] is not None
    first_published_at = published["published_at"]

    # Idempotent republish keeps the original stamp.
    again = _publish(api_client, auth_headers, eval_id)
    assert again["published_at"] == first_published_at

    response = api_client.get("/v1/leaderboard?task=sentiment", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["note"] is None  # task filter given → no warning note
    entry = next(e for e in body["items"] if e["evaluation_id"] == eval_id)
    assert entry["fries_score"] > 0
    assert entry["hf_repo_id"].startswith("org/leaderboard-")
    assert entry["evaluation_mode"] == "AI_AUTONOMOUS"
    assert entry["human_reviewed"] is False
    assert entry["task"] == "sentiment"
    assert entry["published_at"] == first_published_at
    assert entry["report"] is None  # no report generated for this eval

    unpublished = api_client.post(
        f"/v1/evaluations/{eval_id}/unpublish", headers=auth_headers
    )
    assert unpublished.status_code == 200
    assert unpublished.json()["is_published"] is False
    assert unpublished.json()["published_at"] is None

    assert eval_id not in _listed_ids(api_client, auth_headers)

    # Idempotent re-unpublish.
    repeat = api_client.post(f"/v1/evaluations/{eval_id}/unpublish", headers=auth_headers)
    assert repeat.status_code == 200


def test_publish_not_finalized_409(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    # Assisted stops at AWAITING_REVIEW — no final_scores row yet.
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_ASSISTED")

    response = api_client.post(f"/v1/evaluations/{eval_id}/publish", headers=auth_headers)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "NOT_FINALIZED"
    assert body["details"]["status"] == "AWAITING_REVIEW"


def test_other_researcher_cannot_publish_owner_can(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_AUTONOMOUS")

    email = f"researcher2-{uuid.uuid4().hex[:8]}@example.com"
    password = "researcher2-test-pass-123"
    UserRepository(db_session).create(
        email=email, password_hash=hash_password(password), role=UserRole.RESEARCHER
    )
    db_session.flush()
    other_headers = auth_headers_for(api_client, email, password)

    denied = api_client.post(f"/v1/evaluations/{eval_id}/publish", headers=other_headers)
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"

    published = _publish(api_client, auth_headers, eval_id)  # owner succeeds
    assert published["is_published"] is True


def test_task_filter_excludes_other_tasks(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    id_a = _create_and_run(
        api_client, auth_headers, db_session, mode="AI_AUTONOMOUS", task="task-a"
    )
    id_b = _create_and_run(
        api_client, auth_headers, db_session, mode="AI_AUTONOMOUS", task="task-b"
    )
    _publish(api_client, auth_headers, id_a)
    _publish(api_client, auth_headers, id_b)

    ids = _listed_ids(api_client, auth_headers, "?task=task-a")
    assert id_a in ids
    assert id_b not in ids


def test_mode_filter_and_assisted_human_reviewed(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    auto_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_AUTONOMOUS")
    assisted_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_ASSISTED")
    _review_and_finalize(api_client, seeded_users, assisted_id)
    _publish(api_client, auth_headers, auto_id)
    _publish(api_client, auth_headers, assisted_id)

    response = api_client.get(
        "/v1/leaderboard?evaluation_mode=AI_ASSISTED", headers=auth_headers
    )
    assert response.status_code == 200
    items = {e["evaluation_id"]: e for e in response.json()["items"]}
    assert assisted_id in items
    assert auto_id not in items
    assert items[assisted_id]["human_reviewed"] is True

    autonomous = api_client.get(
        "/v1/leaderboard?evaluation_mode=AI_AUTONOMOUS", headers=auth_headers
    )
    items = {e["evaluation_id"]: e for e in autonomous.json()["items"]}
    assert auto_id in items
    assert assisted_id not in items
    assert items[auto_id]["human_reviewed"] is False


def test_report_ref_attached_when_report_exists(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(
        api_client, auth_headers, db_session, mode="AI_AUTONOMOUS", task="with-report"
    )
    _publish(api_client, auth_headers, eval_id)
    ReportRepository(db_session).create(
        evaluation_id=uuid.UUID(eval_id),
        json_uri=f"s3://trustlens/reports/{eval_id}/v1/report.json",
        pdf_uri=f"s3://trustlens/reports/{eval_id}/v1/report.pdf",
        version=1,
    )

    response = api_client.get("/v1/leaderboard?task=with-report", headers=auth_headers)
    entry = next(
        e for e in response.json()["items"] if e["evaluation_id"] == eval_id
    )
    assert entry["report"] == {
        "version": 1,
        "json_uri": f"s3://trustlens/reports/{eval_id}/v1/report.json",
        "pdf_uri": f"s3://trustlens/reports/{eval_id}/v1/report.pdf",
    }


def test_cursor_pagination_smoke(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    published_ids = set()
    for _ in range(3):
        eval_id = _create_and_run(
            api_client, auth_headers, db_session, mode="AI_AUTONOMOUS", task="paginate"
        )
        _publish(api_client, auth_headers, eval_id)
        published_ids.add(eval_id)

    first = api_client.get("/v1/leaderboard?task=paginate&limit=2", headers=auth_headers)
    assert first.status_code == 200
    page1 = first.json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None
    scores = [entry["fries_score"] for entry in page1["items"]]
    assert scores == sorted(scores, reverse=True)

    second = api_client.get(
        f"/v1/leaderboard?task=paginate&limit=2&cursor={page1['next_cursor']}",
        headers=auth_headers,
    )
    assert second.status_code == 200
    page2 = second.json()
    assert len(page2["items"]) == 1
    assert page2["next_cursor"] is None

    ids1 = {entry["evaluation_id"] for entry in page1["items"]}
    ids2 = {entry["evaluation_id"] for entry in page2["items"]}
    assert not ids1 & ids2  # no overlap between pages
    assert ids1 | ids2 == published_ids
