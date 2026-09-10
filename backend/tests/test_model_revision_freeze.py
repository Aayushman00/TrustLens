"""Phase 7 fix: the pipeline must use the evaluation's frozen model_revision,
never re-read the (possibly re-imported/drifted) live ``Model`` row.

Regression for: evaluate_pipeline.py previously called
``run_all_probes(..., model_revision=model.revision, ...)`` at worker
execution time instead of the frozen ``payload.model_revision`` captured at
evaluation-create time. If a model was re-imported (revision changed)
between evaluation create and worker pickup, persisted evidence identity
could silently disagree with ``evaluations.model_revision``.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.model import ModelRepository
from app.db.repositories.probe_result import ProbeResultRepository
from app.db.enums import FriesDimension
from app.schemas.internal import EvaluateModelPayload
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.fakes import FakeEvidenceStore


@pytest.fixture(autouse=True)
def _skip_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.evaluation_service.enqueue_evaluate_model",
        lambda payload: None,
    )


def test_pipeline_uses_frozen_revision_not_live_reimported_revision(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    original_revision = "a" * 40
    drifted_revision = "b" * 40

    model_resp = api_client.post(
        "/v1/models",
        json={
            "hf_repo_id": f"org/reimport-drift-{uuid.uuid4().hex[:8]}",
            "revision": original_revision,
        },
        headers=auth_headers,
    )
    assert model_resp.status_code == 201, model_resp.text
    model_id = model_resp.json()["id"]

    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model_id, "evaluation_mode": "AI_AUTONOMOUS"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    evaluation_id = uuid.UUID(body["id"])

    # Evaluation create froze the model's revision at the time of creation.
    assert body["model_revision"] == original_revision

    # Simulate a re-import changing the live Model row's revision *after*
    # the evaluation was created but *before* the worker picks it up.
    models = ModelRepository(db_session)
    updated_model = models.update_by_hf_repo_id(
        model_resp.json()["hf_repo_id"],
        model_metadata={},
        checksum=None,
        revision=drifted_revision,
    )
    assert updated_model is not None
    assert updated_model.revision == drifted_revision
    db_session.flush()

    # Reconstruct the payload exactly as the real worker would receive it
    # (round-tripped through the persisted evaluation row), then run the
    # pipeline directly against the now-drifted Model row.
    eval_row = EvaluationRepository(db_session).get_by_id(evaluation_id)
    assert eval_row is not None
    assert eval_row.model_revision == original_revision  # persisted column untouched

    payload = EvaluateModelPayload(
        evaluation_id=evaluation_id,
        model_ref=model_resp.json()["hf_repo_id"],
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config=eval_row.probe_config or {},
        model_revision=eval_row.model_revision,
        evaluation_contract=(eval_row.probe_config or {}).get("evaluation_contract", {}),
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    probes = ProbeResultRepository(db_session).list_for_evaluation(evaluation_id)
    assert probes, "pipeline did not persist any probe results"
    fairness_row = next(p for p in probes if p.dimension == FriesDimension.FAIRNESS)

    # The persisted Fairness evidence must reflect the FROZEN revision, not
    # the drifted live Model.revision that was set after evaluation create.
    assert fairness_row.metric_values["model_revision"] == original_revision
    assert fairness_row.metric_values["model_revision"] != drifted_revision
