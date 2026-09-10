"""Phase 8, Task 8.2 — one evaluation, start to finish, through every
new-path component built in Phases 1-6: fetch dataset by URL -> create draft
-> validate/confirm Fairness only (Robustness left NOT_APPLICABLE) -> create
evaluation -> run worker pipeline synchronously -> verify NOT_APPLICABLE
Robustness excluded from confidence and correctly labeled in the report.

This is the single test that proves the new architecture works end-to-end;
any failure here means the migration is not actually complete regardless of
how many smaller tests pass."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, FriesDimension
from app.inference.model_inspection import ModelLabelSnapshot
from app.probes.explainability import ExplainabilityProbe
from app.probes.fairness import FairnessProbe
from app.probes.integrity import IntegrityProbe
from app.probes.registry import ProbeRegistry
from app.probes.robustness import RobustnessProbe
from app.probes.safety import SafetyProbe
from app.schemas.internal import EvaluateModelPayload
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.fakes import FakeEvidenceStore, FakeInferenceBackend

_SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="e2e-sha-1")


@pytest.mark.usefixtures("_localhost_allowed_for_fetch")
def test_full_lifecycle_fairness_only_robustness_not_applicable(
    api_client: TestClient,
    auth_headers: dict[str, str],
    seeded_model,
    httpserver,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. New URL -> DatasetContent (real POST /v1/dataset-fetches, real MinIO).
    httpserver.expect_request("/d.csv").respond_with_data(
        b"text,label,group\nhello,pos,a\nworld,neg,a\nfoo,pos,b\nbar,neg,b\n",
        content_type="text/csv",
    )
    content = api_client.post(
        "/v1/dataset-fetches",
        json={"source_url": httpserver.url_for("/d.csv")},
        headers=auth_headers,
    ).json()

    # 2. Draft -> validate/confirm FAIRNESS only, via the real HTTP surface.
    with patch("app.services.evaluation_draft_service.inspect_model_config", return_value=_SNAPSHOT):
        draft = api_client.post(
            "/v1/evaluation-drafts", json={"model_id": seeded_model.id}, headers=auth_headers
        ).json()
        validated = api_client.put(
            f"/v1/evaluation-drafts/{draft['id']}/FAIRNESS",
            json={
                "dataset_content_id": content["id"],
                "text_column": "text",
                "target_column": "label",
                "sensitive_column": "group",
                "label_mapping": [
                    {"dataset_value": "pos", "model_label_index": 1},
                    {"dataset_value": "neg", "model_label_index": 0},
                ],
                "min_group_n": 2,
            },
            headers=auth_headers,
        )
        assert validated.status_code == 200, validated.text
        assert validated.json()["ok"] is True
        confirmed = api_client.post(
            f"/v1/evaluation-drafts/{draft['id']}/FAIRNESS/confirm", headers=auth_headers
        )
        assert confirmed.status_code == 200, confirmed.text

    # 3. Confirmed draft -> confirmed Evaluation (real POST /v1/evaluations-v2).
    with (
        patch("app.services.evaluation_service_v2.inspect_model_config", return_value=_SNAPSHOT),
        patch("app.services.evaluation_service_v2.enqueue_evaluate_model", return_value="fake-task-id"),
    ):
        created = api_client.post(
            "/v1/evaluations-v2",
            json={"draft_id": draft["id"], "evaluation_mode": "AI_AUTONOMOUS"},
            headers=auth_headers,
        )
    assert created.status_code == 201, created.text
    evaluation = created.json()
    from app.db.repositories.evaluation import EvaluationRepository

    eval_row = EvaluationRepository(db_session).get_by_id(evaluation["id"])
    assert eval_row.methodology_version == CURRENT_METHODOLOGY_VERSION

    # 4. Celery worker -> probes, run in-process (no real Celery), with a
    # deterministic fake backend standing in for FairnessProbe's inference —
    # ROBUSTNESS gets no contract at all, so it never touches inference.
    fake_backend = FakeInferenceBackend(predictions=[1, 0, 1, 0], num_labels=2)
    registry = ProbeRegistry(
        {
            FriesDimension.FAIRNESS: FairnessProbe(inference=fake_backend),
            FriesDimension.ROBUSTNESS: RobustnessProbe(),
            FriesDimension.INTEGRITY: IntegrityProbe(),
            FriesDimension.EXPLAINABILITY: ExplainabilityProbe(),
            FriesDimension.SAFETY: SafetyProbe(),
        }
    )
    monkeypatch.setattr("app.probes.runner.default_registry", lambda: registry)

    payload = EvaluateModelPayload(
        evaluation_id=evaluation["id"],
        model_ref=seeded_model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        probe_config=evaluation["probe_config"],
        model_revision=evaluation["model_revision"],
        evaluation_contract=evaluation["probe_config"]["evaluation_contract"],
        methodology_version=eval_row.methodology_version,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    # 5. Report -> NOT_APPLICABLE Robustness excluded from confidence,
    # correctly labeled in the report's evidence_traceability.
    detail = api_client.get(f"/v1/evaluations/{evaluation['id']}", headers=auth_headers).json()
    assert detail["status"] == "FINALIZED"
    assert detail["confidence_summary"] is not None
    assert detail["confidence_summary"]["by_dimension"]["ROBUSTNESS"] is None
    assert detail["confidence_summary"]["by_dimension"]["FAIRNESS"] is not None

    report = api_client.get(f"/v1/reports/{evaluation['id']}", headers=auth_headers).json()
    assert report["methodology_version"] == CURRENT_METHODOLOGY_VERSION
    robustness_entry = next(
        e for e in report["report_json"]["evidence_traceability"] if e["dimension"] == "ROBUSTNESS"
    )
    assert robustness_entry["status"] == "NOT_APPLICABLE"
