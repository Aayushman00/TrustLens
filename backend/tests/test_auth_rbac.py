"""RBAC on evaluation lifecycle routes (ADR 0006).

Researcher is blocked from human-review and from finalizing AI_ASSISTED
evaluations. Finalize (Phase 17) and human-review (Phase 18) are real —
passing RBAC on a fresh (PENDING) evaluation yields the 409 policy errors.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _login(api_client: TestClient, email: str, password: str) -> dict[str, str]:
    response = api_client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_evaluation(api_client: TestClient, headers: dict[str, str], mode: str) -> str:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/rbac-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert model.status_code == 201, model.text
    evaluation = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": mode},
        headers=headers,
    )
    assert evaluation.status_code == 201, evaluation.text
    return evaluation.json()["id"]


def test_researcher_cannot_human_review_403(api_client: TestClient, seeded_users) -> None:
    researcher, r_pw = seeded_users["researcher"]
    headers = _login(api_client, researcher.email, r_pw)
    eval_id = _create_evaluation(api_client, headers, "AI_ASSISTED")

    response = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_reviewer_human_review_on_pending_409_not_ready(
    api_client: TestClient, seeded_users
) -> None:
    """Reviewer passes RBAC; PENDING Assisted → 409 NOT_READY (Phase 18 policy)."""
    researcher, r_pw = seeded_users["researcher"]
    reviewer, v_pw = seeded_users["reviewer"]
    researcher_headers = _login(api_client, researcher.email, r_pw)
    eval_id = _create_evaluation(api_client, researcher_headers, "AI_ASSISTED")

    reviewer_headers = _login(api_client, reviewer.email, v_pw)
    response = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True},
        headers=reviewer_headers,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_READY"


def test_researcher_cannot_finalize_assisted_403(api_client: TestClient, seeded_users) -> None:
    researcher, r_pw = seeded_users["researcher"]
    headers = _login(api_client, researcher.email, r_pw)
    eval_id = _create_evaluation(api_client, headers, "AI_ASSISTED")

    response = api_client.post(f"/v1/evaluations/{eval_id}/finalize", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_researcher_finalize_autonomous_pending_409_not_ready(
    api_client: TestClient, seeded_users
) -> None:
    """Any authed user passes RBAC for Autonomous; PENDING → 409 NOT_READY (Phase 17)."""
    researcher, r_pw = seeded_users["researcher"]
    headers = _login(api_client, researcher.email, r_pw)
    eval_id = _create_evaluation(api_client, headers, "AI_AUTONOMOUS")

    response = api_client.post(f"/v1/evaluations/{eval_id}/finalize", headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_READY"


def test_reviewer_finalize_assisted_before_review_409(
    api_client: TestClient, seeded_users
) -> None:
    """Reviewer passes RBAC; PENDING Assisted → 409 NOT_READY (Phase 17 policy)."""
    researcher, r_pw = seeded_users["researcher"]
    reviewer, v_pw = seeded_users["reviewer"]
    researcher_headers = _login(api_client, researcher.email, r_pw)
    eval_id = _create_evaluation(api_client, researcher_headers, "AI_ASSISTED")

    reviewer_headers = _login(api_client, reviewer.email, v_pw)
    response = api_client.post(f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers)
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_READY"


def test_owner_passes_publish_rbac_but_pending_conflicts(
    api_client: TestClient, seeded_users
) -> None:
    """Owner clears RBAC; the Phase 22 FINALIZED guard then rejects a PENDING eval."""
    researcher, r_pw = seeded_users["researcher"]
    headers = _login(api_client, researcher.email, r_pw)
    eval_id = _create_evaluation(api_client, headers, "AI_AUTONOMOUS")

    response = api_client.post(f"/v1/evaluations/{eval_id}/publish", headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_FINALIZED"


def test_non_owner_researcher_cannot_publish_403(api_client: TestClient, seeded_users) -> None:
    researcher, r_pw = seeded_users["researcher"]
    reviewer, v_pw = seeded_users["reviewer"]
    researcher_headers = _login(api_client, researcher.email, r_pw)
    eval_id = _create_evaluation(api_client, researcher_headers, "AI_AUTONOMOUS")

    reviewer_headers = _login(api_client, reviewer.email, v_pw)
    response = api_client.post(f"/v1/evaluations/{eval_id}/publish", headers=reviewer_headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_admin_passes_publish_rbac_on_any_evaluation(api_client: TestClient, seeded_users) -> None:
    """Admin clears RBAC on someone else's eval; PENDING then hits the 409 guard."""
    researcher, r_pw = seeded_users["researcher"]
    admin, a_pw = seeded_users["admin"]
    researcher_headers = _login(api_client, researcher.email, r_pw)
    eval_id = _create_evaluation(api_client, researcher_headers, "AI_AUTONOMOUS")

    admin_headers = _login(api_client, admin.email, a_pw)
    response = api_client.post(f"/v1/evaluations/{eval_id}/publish", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_FINALIZED"
