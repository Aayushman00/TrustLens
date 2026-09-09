"""Phase 4 — append-only evaluation event timeline.

Covers: event creation at each real lifecycle transition, deterministic
ordering by id (not created_at), idempotency under a simulated Celery
retry, all five evaluation_failed reason codes, human-review/report events,
API ownership (shared-read model), empty-timeline behavior for
pre-Phase-4-shaped evaluations, and the invariant that no event payload can
change/decide FRIES, O/S/D, or evaluation status.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus
from app.db.models import User
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.evaluation_event import (
    EVENT_AGENT_COMPLETED,
    EVENT_AWAITING_REVIEW,
    EVENT_EVALUATION_CREATED,
    EVENT_EVALUATION_FAILED,
    EVENT_EVALUATION_FINALIZED,
    EVENT_EVALUATION_STARTED,
    EVENT_HUMAN_REVIEW_SUBMITTED,
    EVENT_PROBES_COMPLETED,
    EVENT_REPORT_GENERATED,
    REASON_MODEL_REF_MISMATCH,
    REASON_NO_EVIDENCE_STORE,
    REASON_OSD_AGENT_ERROR,
    REASON_PROBE_ERROR,
    REASON_SCORING_ERROR,
    EvaluationEventRepository,
)
from app.db.repositories.model import ModelRepository
from app.schemas.internal import EvaluateModelPayload
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.conftest import LEGACY_HEURISTIC_PROBE_CONFIG, auth_headers_for, fries_complete_model_payload
from tests.fakes import FakeEvidenceStore


@pytest.fixture(autouse=True)
def _skip_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: "fake-task-id",
    )


# ---------------------------------------------------------------------------
# A/C/D/E/L/M: event creation, ordering, timestamps, persistence, no second
# source of truth — via a real pipeline run (repository/DB level)
# ---------------------------------------------------------------------------


def test_autonomous_withheld_event_sequence(db_session: Session) -> None:
    """Default deterministic engine, no human review -> always withheld."""
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/ev-{uuid.uuid4().hex[:8]}", revision="c" * 40, checksum="c" * 40)
    evaluation = evals.create(model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS)
    db_session.flush()

    store = FakeEvidenceStore()
    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=store)  # type: ignore[arg-type]
    db_session.flush()

    events = EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id)
    types = [e.event_type for e in events]
    assert types == [
        EVENT_EVALUATION_STARTED,
        EVENT_PROBES_COMPLETED,
        EVENT_AGENT_COMPLETED,
        EVENT_EVALUATION_FINALIZED,
    ]
    # Ordering is by id, ascending, matching insertion order.
    assert [e.id for e in events] == sorted(e.id for e in events)
    # Every event has a real, server-generated, non-null timestamp.
    for e in events:
        assert e.created_at is not None

    finalized = events[-1]
    assert finalized.detail == {"evaluation_mode": "AI_AUTONOMOUS", "scoring_withheld": True}

    probes_completed = events[1]
    assert probes_completed.detail == {"probe_count": 5}

    # M/L: the evaluation's own authoritative row is what actually holds the
    # decision — the event is a copy of an already-made decision, never the
    # source of it.
    row = evals.get_by_id(evaluation.id)
    assert row is not None
    assert row.status == EvaluationStatus.FINALIZED


def test_autonomous_scored_event_sequence(
    db_session: Session,
    evaluated_robustness: None,
    evaluated_fairness: None,
) -> None:
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(**fries_complete_model_payload(f"org/ev-{uuid.uuid4().hex[:8]}"))
    evaluation = evals.create(
        model_id=model.id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config=LEGACY_HEURISTIC_PROBE_CONFIG,
    )
    db_session.flush()

    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config=LEGACY_HEURISTIC_PROBE_CONFIG,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())  # type: ignore[arg-type]
    db_session.flush()

    row = evals.get_by_id(evaluation.id)
    assert row is not None
    assert row.status == EvaluationStatus.FINALIZED

    events = EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id)
    finalized = events[-1]
    assert finalized.event_type == EVENT_EVALUATION_FINALIZED
    # scoring_withheld is copied from the already-computed finalized_osd, and
    # must exactly match whether a final_scores row actually exists — the
    # event never independently decides this.
    from app.db.repositories.final_score import FinalScoreRepository

    final_row = FinalScoreRepository(db_session).get_for_evaluation(evaluation.id)
    assert finalized.detail["scoring_withheld"] is (final_row is None)
    assert final_row is not None  # this fixture combination is designed to score


def test_deterministic_ordering_survives_shared_timestamps(db_session: Session) -> None:
    """Multiple events inserted in one transaction can share created_at
    (Postgres now() is frozen per-transaction) — id ordering must still be
    correct regardless."""
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    events_repo = EvaluationEventRepository(db_session)
    model = models.create(hf_repo_id=f"org/ord-{uuid.uuid4().hex[:8]}", revision="d" * 40, checksum="d" * 40)
    evaluation = evals.create(model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS)
    db_session.flush()

    e1 = events_repo.create(evaluation_id=evaluation.id, event_type=EVENT_EVALUATION_STARTED)
    e2 = events_repo.create(evaluation_id=evaluation.id, event_type=EVENT_PROBES_COMPLETED)
    e3 = events_repo.create(evaluation_id=evaluation.id, event_type=EVENT_AGENT_COMPLETED)
    db_session.flush()

    # Same transaction -> Postgres now() is frozen -> these are very likely
    # bitwise-identical timestamps. The important thing is id order is right
    # regardless of whether that's true.
    listed = events_repo.list_for_evaluation(evaluation.id)
    assert [e.id for e in listed] == [e1.id, e2.id, e3.id]
    assert [e.event_type for e in listed] == [
        EVENT_EVALUATION_STARTED,
        EVENT_PROBES_COMPLETED,
        EVENT_AGENT_COMPLETED,
    ]


# ---------------------------------------------------------------------------
# H: idempotency under a simulated Celery retry
# ---------------------------------------------------------------------------


def test_retry_after_running_produces_no_duplicate_events(db_session: Session) -> None:
    """Simulates a Celery redelivery: run_evaluation_pipeline invoked twice.
    The second call's CAS (expected=PENDING) fails immediately since the
    first call already advanced the status — no event should be inserted."""
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/retry-{uuid.uuid4().hex[:8]}", revision="e" * 40, checksum="e" * 40)
    evaluation = evals.create(model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS)
    db_session.flush()

    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())  # type: ignore[arg-type]
    db_session.flush()
    first_count = len(EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id))
    assert first_count > 0

    # Simulated redelivery/retry of the exact same task.
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())  # type: ignore[arg-type]
    db_session.flush()
    second_count = len(EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id))
    assert second_count == first_count, "a retried pipeline run must not duplicate any event"


# ---------------------------------------------------------------------------
# I: all five evaluation_failed reason codes
# ---------------------------------------------------------------------------


def test_failure_reason_model_ref_mismatch(db_session: Session) -> None:
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/mismatch-{uuid.uuid4().hex[:8]}", revision="f" * 40, checksum="f" * 40)
    evaluation = evals.create(model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS)
    db_session.flush()

    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref="org/some-other-model",  # deliberately wrong
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())  # type: ignore[arg-type]
    db_session.flush()

    events = EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id)
    assert len(events) == 1
    assert events[0].event_type == EVENT_EVALUATION_FAILED
    assert events[0].detail["reason_code"] == REASON_MODEL_REF_MISMATCH
    # No stack trace / exception text / paths in the payload.
    assert set(events[0].detail.keys()) == {"reason_code", "from_status"}


def test_failure_reason_no_evidence_store(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/noevi-{uuid.uuid4().hex[:8]}", revision="1" * 40, checksum="1" * 40)
    evaluation = evals.create(model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS)
    db_session.flush()

    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    # evidence_store=None alone falls through to get_evidence_store(settings),
    # which may resolve a real store from env config — force the "no store
    # configured" branch explicitly, same technique as
    # test_evaluate_pipeline_evidence.py::test_pipeline_fails_without_evidence_store.
    monkeypatch.setattr("app.tasks.evaluate_pipeline.get_evidence_store", lambda settings: None)
    run_evaluation_pipeline(db_session, payload, evidence_store=None)

    events = EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id)
    assert [e.event_type for e in events] == [EVENT_EVALUATION_STARTED, EVENT_EVALUATION_FAILED]
    assert events[-1].detail["reason_code"] == REASON_NO_EVIDENCE_STORE


def test_failure_reason_probe_error(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.probes.errors import ProbeError

    def _boom(*args, **kwargs):
        raise ProbeError("synthetic failure for test")

    monkeypatch.setattr("app.tasks.evaluate_pipeline.run_all_probes", _boom)

    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/probeerr-{uuid.uuid4().hex[:8]}", revision="2" * 40, checksum="2" * 40)
    evaluation = evals.create(model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS)
    db_session.flush()

    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())  # type: ignore[arg-type]

    events = EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id)
    assert events[-1].event_type == EVENT_EVALUATION_FAILED
    assert events[-1].detail["reason_code"] == REASON_PROBE_ERROR
    assert "synthetic failure" not in str(events[-1].detail)


def test_failure_reason_osd_agent_error(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic osd failure for test")

    monkeypatch.setattr("app.tasks.evaluate_pipeline._run_osd_agent", _boom)

    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/osderr-{uuid.uuid4().hex[:8]}", revision="3" * 40, checksum="3" * 40)
    evaluation = evals.create(model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS)
    db_session.flush()

    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())  # type: ignore[arg-type]

    events = EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id)
    assert events[-1].event_type == EVENT_EVALUATION_FAILED
    assert events[-1].detail["reason_code"] == REASON_OSD_AGENT_ERROR
    assert "synthetic osd failure" not in str(events[-1].detail)


def test_failure_reason_scoring_error(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    evaluated_robustness: None,
    evaluated_fairness: None,
) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic scoring failure for test")

    monkeypatch.setattr("app.tasks.evaluate_pipeline.score_from_finalized_osd", _boom)

    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(**fries_complete_model_payload(f"org/scoreerr-{uuid.uuid4().hex[:8]}"))
    evaluation = evals.create(
        model_id=model.id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config=LEGACY_HEURISTIC_PROBE_CONFIG,
    )
    db_session.flush()

    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config=LEGACY_HEURISTIC_PROBE_CONFIG,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())  # type: ignore[arg-type]

    events = EvaluationEventRepository(db_session).list_for_evaluation(evaluation.id)
    assert events[-1].event_type == EVENT_EVALUATION_FAILED
    assert events[-1].detail["reason_code"] == REASON_SCORING_ERROR
    assert "synthetic scoring failure" not in str(events[-1].detail)


# ---------------------------------------------------------------------------
# J/K: human review + finalize events (assisted, scored and withheld)
# ---------------------------------------------------------------------------


def _create_and_run_assisted(
    api_client: TestClient, headers: dict[str, str], db_session: Session
) -> str:
    model = api_client.post(
        "/v1/models",
        json=fries_complete_model_payload(f"org/assisted-{uuid.uuid4().hex[:8]}"),
        headers=headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model.json()["id"],
            "evaluation_mode": "AI_ASSISTED",
            "probe_config": {"schema_version": "v1", "assessment_engine": "deterministic"},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=model.json()["hf_repo_id"],
        evaluation_mode=EvaluationMode.AI_ASSISTED,
        probe_config={"schema_version": "v1", "assessment_engine": "deterministic"},
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()
    return eval_id


def test_assisted_scored_event_sequence(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run_assisted(api_client, auth_headers, db_session)
    reviewer, password = seeded_users["reviewer"]
    reviewer_headers = auth_headers_for(api_client, reviewer.email, password)

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    dims = [a["aspect"] for a in detail["osd_agent"]["ai_suggestion"]["aspects"]]
    full_edits = [{"aspect": dim, "O": 4, "S": 6, "D": 8} for dim in dims]
    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"aspects": full_edits},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    finalized = api_client.post(f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["final_score"] is not None

    events_resp = api_client.get(f"/v1/evaluations/{eval_id}/events", headers=auth_headers)
    assert events_resp.status_code == 200
    types = [e["event_type"] for e in events_resp.json()["items"]]
    assert EVENT_HUMAN_REVIEW_SUBMITTED in types
    assert types[-1] == EVENT_EVALUATION_FINALIZED
    finalized_event = events_resp.json()["items"][-1]
    assert finalized_event["detail"] == {"evaluation_mode": "AI_ASSISTED", "scoring_withheld": False}

    human_review_event = next(e for e in events_resp.json()["items"] if e["event_type"] == EVENT_HUMAN_REVIEW_SUBMITTED)
    # O/S/D values themselves must never appear in the event payload.
    assert "O" not in human_review_event["detail"]
    assert "S" not in human_review_event["detail"]
    assert "D" not in human_review_event["detail"]
    assert human_review_event["detail"] == {"accept_all": False, "human_changed": True}


def test_assisted_withheld_event_sequence(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run_assisted(api_client, auth_headers, db_session)
    reviewer, password = seeded_users["reviewer"]
    reviewer_headers = auth_headers_for(api_client, reviewer.email, password)

    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"aspects": [{"aspect": "FAIRNESS", "S": 7}]},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    finalized = api_client.post(f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["final_score"] is None

    events_resp = api_client.get(f"/v1/evaluations/{eval_id}/events", headers=auth_headers)
    finalized_event = events_resp.json()["items"][-1]
    assert finalized_event["event_type"] == EVENT_EVALUATION_FINALIZED
    assert finalized_event["detail"] == {"evaluation_mode": "AI_ASSISTED", "scoring_withheld": True}


def test_second_human_review_produces_a_second_event_not_a_duplicate_error(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    """Multiple reviews before finalize are a legitimate, repeatable fact —
    not something the event log should deduplicate."""
    eval_id = _create_and_run_assisted(api_client, auth_headers, db_session)
    reviewer, password = seeded_users["reviewer"]
    reviewer_headers = auth_headers_for(api_client, reviewer.email, password)

    for s_value in (5, 7):
        review = api_client.post(
            f"/v1/evaluations/{eval_id}/human-review",
            json={"aspects": [{"aspect": "FAIRNESS", "S": s_value}]},
            headers=reviewer_headers,
        )
        assert review.status_code == 201, review.text

    events_resp = api_client.get(f"/v1/evaluations/{eval_id}/events", headers=auth_headers)
    types = [e["event_type"] for e in events_resp.json()["items"]]
    assert types.count(EVENT_HUMAN_REVIEW_SUBMITTED) == 2


# ---------------------------------------------------------------------------
# N/F/G: API — response shape, ownership (shared-read model), empty timeline
# ---------------------------------------------------------------------------


def test_events_endpoint_ordering_and_shape(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/api-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert model.status_code == 201
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": "AI_AUTONOMOUS"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    eval_id = created.json()["id"]

    resp = api_client.get(f"/v1/evaluations/{eval_id}/events", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    # create_evaluation already emits evaluation_created synchronously.
    assert len(items) == 1
    assert items[0]["event_type"] == EVENT_EVALUATION_CREATED
    assert items[0]["detail"] == {"enqueued": True, "task_id": "fake-task-id"}
    assert "id" in items[0] and "evaluation_id" in items[0] and "created_at" in items[0]


def test_events_endpoint_shared_read_any_authenticated_user(
    api_client: TestClient,
    auth_headers: dict[str, str],
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    """Matches the existing shared-read model (GET /evaluations/{id} and
    GET /reports/{id} have no owner filter) — the events endpoint must not
    invent a stricter rule."""
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/shared-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": "AI_AUTONOMOUS"},
        headers=auth_headers,
    )
    eval_id = created.json()["id"]

    reviewer, password = seeded_users["reviewer"]
    other_user_headers = auth_headers_for(api_client, reviewer.email, password)
    resp = api_client.get(f"/v1/evaluations/{eval_id}/events", headers=other_user_headers)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_events_endpoint_404_for_unknown_evaluation(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = api_client.get(f"/v1/evaluations/{uuid.uuid4()}/events", headers=auth_headers)
    assert resp.status_code == 404


def test_events_endpoint_empty_for_pre_phase4_shaped_evaluation(
    db_session: Session, api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """An evaluation row created directly at the repository level (bypassing
    the service layer that emits evaluation_created) simulates a
    pre-Phase-4 evaluation — the endpoint must return an honest empty list,
    never a fabricated reconstruction."""
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/legacy-{uuid.uuid4().hex[:8]}")
    evaluation = evals.create(model_id=model.id, evaluation_mode=EvaluationMode.AI_AUTONOMOUS)
    db_session.commit()

    resp = api_client.get(f"/v1/evaluations/{evaluation.id}/events", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# Report-generated event
# ---------------------------------------------------------------------------


def test_report_generation_emits_event(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
    evaluated_robustness: None,
    evaluated_fairness: None,
) -> None:
    model = api_client.post(
        "/v1/models",
        json=fries_complete_model_payload(f"org/report-{uuid.uuid4().hex[:8]}"),
        headers=admin_headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model.json()["id"],
            "evaluation_mode": "AI_AUTONOMOUS",
            "probe_config": LEGACY_HEURISTIC_PROBE_CONFIG,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=model.json()["hf_repo_id"],
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config=LEGACY_HEURISTIC_PROBE_CONFIG,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.commit()

    report_resp = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert report_resp.status_code == 200, report_resp.text

    events_resp = api_client.get(f"/v1/evaluations/{eval_id}/events", headers=auth_headers)
    types = [e["event_type"] for e in events_resp.json()["items"]]
    assert EVENT_REPORT_GENERATED in types
    report_event = next(e for e in events_resp.json()["items"] if e["event_type"] == EVENT_REPORT_GENERATED)
    assert report_event["detail"] == {"version": 1}
