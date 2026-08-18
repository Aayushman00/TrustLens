"""Phase 24 — API lifecycle regression pack (run with ``pytest -m lifecycle``).

Full demo journeys through the public API against Postgres, with externals
faked exactly like the per-endpoint suites: Hub adapter patched (no network),
FakeEvidenceStore/FakeReportStore instead of MinIO, Redis enqueue a no-op and
the Celery pipeline invoked inline. Where the endpoint suites test one route
at a time, this file asserts the *sequence* holds together end to end:

- Autonomous: login → import-hf → create → pipeline → FINALIZED → report v1 →
  publish → leaderboard entry → unpublish → gone.
- Assisted: pipeline → AWAITING_REVIEW → researcher 403 on review + finalize →
  reviewer accept-all → finalize → human_reviewed disclosure everywhere.
- Optional live-Hub import (``integration`` marker), skipped unless
  ``TRUSTLENS_LIVE_TESTS=1``.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.base import NormalizedModelRecord
from app.db.enums import EvaluationMode
from app.db.models import User
from app.schemas.internal import EvaluateModelPayload
from app.schemas.modes import (
    ASSISTED_AWAITING_DISCLAIMER,
    ASSISTED_REVIEWED_DISCLAIMER,
    AUTONOMOUS_DISCLAIMER,
)
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.conftest import auth_headers_for
from tests.fakes import FakeEvidenceStore, FakeReportStore

pytestmark = pytest.mark.lifecycle


@pytest.fixture(autouse=True)
def _skip_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid Redis during API create; journeys invoke the pipeline directly."""
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


def _patch_hub(monkeypatch: pytest.MonkeyPatch, hf_repo_id: str) -> None:
    """Replace the Hub adapter with a canned record for ``hf_repo_id``."""
    record = NormalizedModelRecord(
        hf_repo_id=hf_repo_id,
        revision="rev-lifecycle",
        checksum="rev-lifecycle",
        model_metadata={
            "source": "huggingface_hub",
            "pipeline_tag": "fill-mask",
            "card_text": "# Model Card\nLifecycle fixture card.",
            "files": ["config.json", "model.safetensors"],
        },
    )

    class _FakeAdapter:
        def resolve(self, ref: str, revision: str | None = None) -> NormalizedModelRecord:
            return record

    monkeypatch.setattr("app.services.model_service.HfHubModelAdapter", lambda: _FakeAdapter())


def _import_and_create(
    api_client: TestClient,
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str,
) -> tuple[str, str]:
    """import-hf (mocked Hub) → create evaluation. Returns (eval_id, hf_repo_id)."""
    hf_repo_id = f"org/lifecycle-{uuid.uuid4().hex[:8]}"
    _patch_hub(monkeypatch, hf_repo_id)
    imported = api_client.post(
        "/v1/models/import-hf", json={"repo_id": hf_repo_id}, headers=headers
    )
    assert imported.status_code == 201, imported.text
    model = imported.json()
    assert model["hf_repo_id"] == hf_repo_id
    assert model["model_metadata"]["card_text"]

    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model["id"], "evaluation_mode": mode},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "PENDING"
    return created.json()["id"], hf_repo_id


def _run_pipeline(db_session: Session, eval_id: str, hf_repo_id: str, mode: str) -> None:
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=hf_repo_id,
        evaluation_mode=EvaluationMode(mode),
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()


def _leaderboard_entries(api_client: TestClient, headers: dict[str, str]) -> dict[str, dict]:
    board = api_client.get("/v1/leaderboard", headers=headers)
    assert board.status_code == 200, board.text
    return {entry["evaluation_id"]: entry for entry in board.json()["items"]}


# ---------------------------------------------------------------------------
# Journey 1 — Autonomous: import → FINALIZED → report → publish → unpublish
# ---------------------------------------------------------------------------


def test_autonomous_journey_import_to_leaderboard(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    report_store: FakeReportStore,
) -> None:
    eval_id, hf_repo_id = _import_and_create(
        api_client, auth_headers, monkeypatch, mode="AI_AUTONOMOUS"
    )
    _run_pipeline(db_session, eval_id, hf_repo_id, "AI_AUTONOMOUS")

    # FINALIZED with score + autonomous (not-human-reviewed) disclosure.
    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert detail["status"] == "FINALIZED"
    assert detail["probe_progress"] == {"completed": 5, "total": 5}
    assert detail["final_score"] is not None
    fries_score = detail["final_score"]["fries_score"]
    assert 0.0 <= fries_score <= 10.0
    assert detail["final_score"]["evaluation_mode"] == "AI_AUTONOMOUS"
    assert detail["mode_disclosure"]["human_reviewed"] is False
    assert detail["mode_disclosure"]["disclaimer"] == AUTONOMOUS_DISCLAIMER
    assert detail["is_published"] is False

    # First report read auto-generates v1 with the same disclosure.
    report = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert report.status_code == 200, report.text
    report_body = report.json()
    assert report_body["version"] == 1
    assert report_body["fries_score"] == fries_score
    assert report_body["report_json"]["schema_version"] == "report_v1"
    assert report_body["report_json"]["mode_disclosure"]["evaluation_mode"] == "AI_AUTONOMOUS"
    assert report_body["report_json"]["mode_disclosure"]["human_reviewed"] is False
    assert f"reports/{eval_id}/v1/report.json" in report_store.objects

    # Publish (owner) → leaderboard carries the score and the report ref.
    published = api_client.post(f"/v1/evaluations/{eval_id}/publish", headers=auth_headers)
    assert published.status_code == 200, published.text
    assert published.json()["is_published"] is True
    assert published.json()["published_at"] is not None

    entries = _leaderboard_entries(api_client, auth_headers)
    assert eval_id in entries
    entry = entries[eval_id]
    assert entry["hf_repo_id"] == hf_repo_id
    assert entry["fries_score"] == fries_score
    assert entry["evaluation_mode"] == "AI_AUTONOMOUS"
    assert entry["human_reviewed"] is False
    assert entry["report"] is not None
    assert entry["report"]["version"] == 1
    assert entry["report"]["json_uri"].endswith(f"reports/{eval_id}/v1/report.json")

    # Unpublish → private again, off the leaderboard.
    unpublished = api_client.post(f"/v1/evaluations/{eval_id}/unpublish", headers=auth_headers)
    assert unpublished.status_code == 200, unpublished.text
    assert unpublished.json()["is_published"] is False
    assert eval_id not in _leaderboard_entries(api_client, auth_headers)


# ---------------------------------------------------------------------------
# Journey 2 — Assisted: review gate (RBAC in-flow) → finalize → disclosure
# ---------------------------------------------------------------------------


def test_assisted_journey_review_gate_and_disclosure(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
    monkeypatch: pytest.MonkeyPatch,
    report_store: FakeReportStore,
) -> None:
    eval_id, hf_repo_id = _import_and_create(
        api_client, auth_headers, monkeypatch, mode="AI_ASSISTED"
    )
    _run_pipeline(db_session, eval_id, hf_repo_id, "AI_ASSISTED")

    detail = api_client.get(f"/v1/evaluations/{eval_id}", headers=auth_headers).json()
    assert detail["status"] == "AWAITING_REVIEW"
    assert detail["final_score"] is None
    assert detail["mode_disclosure"]["disclaimer"] == ASSISTED_AWAITING_DISCLAIMER

    # RBAC inside the flow: the researcher may neither review nor finalize.
    denied_review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True},
        headers=auth_headers,
    )
    assert denied_review.status_code == 403, denied_review.text
    assert denied_review.json()["code"] == "FORBIDDEN"
    denied_finalize = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=auth_headers
    )
    assert denied_finalize.status_code == 403, denied_finalize.text
    assert denied_finalize.json()["code"] == "FORBIDDEN"

    # Reviewer accepts the agent suggestion and finalizes.
    reviewer, password = seeded_users["reviewer"]
    reviewer_headers = auth_headers_for(api_client, reviewer.email, password)
    review = api_client.post(
        f"/v1/evaluations/{eval_id}/human-review",
        json={"accept_all": True, "review_rationale": "lifecycle accept-all"},
        headers=reviewer_headers,
    )
    assert review.status_code == 201, review.text
    assert review.json()["accept_all"] is True

    finalized = api_client.post(
        f"/v1/evaluations/{eval_id}/finalize", headers=reviewer_headers
    )
    assert finalized.status_code == 200, finalized.text
    fin = finalized.json()
    assert fin["status"] == "FINALIZED"
    assert fin["final_score"]["human_reviewed"] is True
    assert fin["final_score"]["evaluation_mode"] == "AI_ASSISTED"
    assert fin["mode_disclosure"]["human_reviewed"] is True
    assert fin["mode_disclosure"]["disclaimer"] == ASSISTED_REVIEWED_DISCLAIMER

    # Report and leaderboard both carry the human-reviewed disclosure.
    report = api_client.get(f"/v1/reports/{eval_id}", headers=auth_headers)
    assert report.status_code == 200, report.text
    assert report.json()["mode_disclosure"]["human_reviewed"] is True
    assert report.json()["report_json"]["human_review"] is not None

    published = api_client.post(f"/v1/evaluations/{eval_id}/publish", headers=auth_headers)
    assert published.status_code == 200, published.text

    entries = _leaderboard_entries(api_client, auth_headers)
    assert eval_id in entries
    assert entries[eval_id]["evaluation_mode"] == "AI_ASSISTED"
    assert entries[eval_id]["human_reviewed"] is True


# ---------------------------------------------------------------------------
# Optional live path — real Hub import (opt-in, network)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("TRUSTLENS_LIVE_TESTS") != "1",
    reason="live Hugging Face Hub import — set TRUSTLENS_LIVE_TESTS=1 to run",
)
def test_live_hub_import_bert_tiny(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Real (unpatched) Hub import of a tiny public model."""
    response = api_client.post(
        "/v1/models/import-hf",
        json={"repo_id": "prajjwal1/bert-tiny"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["hf_repo_id"] == "prajjwal1/bert-tiny"
    assert body["revision"]
    assert body["model_metadata"]["source"] == "huggingface_hub"
