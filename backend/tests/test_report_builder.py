"""Phase 19 — canonical report_v1 builder (+ render smoke tests).

Pipeline runs use FakeEvidenceStore (pattern from test_human_review.py); the
builder assembles only from persisted rows, so reports match detail reads.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus, FriesDimension
from app.db.models import User
from app.db.repositories.evaluation import EvaluationRepository
from app.reports.builder import build_executive_summary, build_report_json
from app.reports.render import render_html, render_pdf
from app.schemas.internal import EvaluateModelPayload
from app.schemas.modes import (
    ASSISTED_REVIEWED_DISCLAIMER,
    AUTONOMOUS_DISCLAIMER,
    build_mode_disclosure,
)
from app.schemas.reports import (
    ExecutiveSummary,
    ReportEvaluation,
    ReportProbe,
    ReportScore,
    ReportV1,
)
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.conftest import auth_headers_for
from tests.fakes import FakeEvidenceStore

# ---------------------------------------------------------------------------
# Pure executive summary — no DB
# ---------------------------------------------------------------------------


def test_executive_summary_autonomous_with_veto_and_flags() -> None:
    summary = build_executive_summary(
        mode=EvaluationMode.AI_AUTONOMOUS,
        human_reviewed=False,
        fries_score=4.05,
        dimension_scores={"FAIRNESS": 0.0, "SAFETY": 8.0},
        probe_flags=["needs_human_review", "empty_card", "needs_human_review"],
        model_ref="org/model",
    )
    assert "AI-AUTONOMOUS" in summary.headline
    assert "not human-reviewed" in summary.headline
    joined = " | ".join(summary.bullets)
    assert "Evaluation mode: AI-AUTONOMOUS" in joined
    assert "4.05/10 (not FRIES2)" in joined
    assert "Vetoed dimensions (score 0): FAIRNESS" in joined
    assert "empty_card, needs_human_review" in joined
    assert "not ground truth" in joined


def test_executive_summary_assisted_reviewed() -> None:
    summary = build_executive_summary(
        mode=EvaluationMode.AI_ASSISTED,
        human_reviewed=True,
        fries_score=5.52,
        dimension_scores={"SAFETY": 8.0},
        probe_flags=[],
        model_ref="org/model",
    )
    assert "AI-ASSISTED" in summary.headline
    assert "human-reviewed (accept/edit of agent suggestions)" in summary.headline
    assert any("Human reviewed: yes" in bullet for bullet in summary.bullets)


# ---------------------------------------------------------------------------
# Render smoke tests — hand-built report, no DB
# ---------------------------------------------------------------------------


def _sample_report(*, mode: EvaluationMode, human_reviewed: bool) -> dict[str, Any]:
    report = ReportV1(
        report_version=1,
        generated_at=datetime.now(UTC),
        evaluation=ReportEvaluation(
            id=uuid.uuid4(),
            status=EvaluationStatus.FINALIZED,
            evaluation_mode=mode,
            model_ref="org/sample-model",
            model_id=1,
            created_at=datetime.now(UTC),
        ),
        mode_disclosure=build_mode_disclosure(
            evaluation_mode=mode, human_reviewed=human_reviewed
        ),
        score=ReportScore(
            fries_score=4.05,
            dimension_scores={"FAIRNESS": 4.0, "SAFETY": 8.0},
            finalized_osd={
                "aspects": [{"aspect": "FAIRNESS", "O": 4, "S": 5, "D": 6}],
                "source": "osd_agent_autonomous",
                "human_reviewed": human_reviewed,
            },
            overall_confidence=0.62,
        ),
        probes=[
            ReportProbe(
                dimension=FriesDimension.FAIRNESS,
                metric_values={"accuracy": 0.9, "groups": {"a": 1}, "flags": ["low_n"]},
                confidence=0.5,
                flags=["low_n"],
                evidence_refs=[
                    {
                        "evidence_id": "ev-smoke-123",
                        "uri": "s3://trustlens/evidence/x/ev-smoke-123.json",
                        "hash": "sha256:abc123",
                    }
                ],
            )
        ],
        executive_summary=ExecutiveSummary(
            headline="Sample headline", bullets=["bullet one"]
        ),
    )
    return report.model_dump(mode="json")


def test_render_html_autonomous_smoke() -> None:
    html = render_html(_sample_report(mode=EvaluationMode.AI_AUTONOMOUS, human_reviewed=False))
    assert "AI-AUTONOMOUS EVALUATION" in html
    assert AUTONOMOUS_DISCLAIMER in html
    assert "4.05" in html
    assert "original_FRIES" in html
    assert "ev-smoke-123" in html  # evidence IDs surface in the PDF projection
    assert "low_n" in html
    assert "Sample headline" in html


def test_render_html_assisted_smoke() -> None:
    html = render_html(_sample_report(mode=EvaluationMode.AI_ASSISTED, human_reviewed=True))
    assert "AI-ASSISTED EVALUATION" in html
    assert ASSISTED_REVIEWED_DISCLAIMER in html
    assert "Human reviewed:</strong> yes" in html


def test_render_pdf_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.reports.render.get_settings",
        lambda: SimpleNamespace(report_pdf_enabled=False),
    )
    assert render_pdf("<html><body>x</body></html>") is None


def test_render_pdf_real_smoke() -> None:
    """Real WeasyPrint render — runs in Docker; skips on hosts without OS libs."""
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("weasyprint unavailable (OS libs missing on this host)")
    html = render_html(_sample_report(mode=EvaluationMode.AI_AUTONOMOUS, human_reviewed=False))
    pdf = render_pdf(html)
    assert pdf is not None
    assert pdf.startswith(b"%PDF")


# ---------------------------------------------------------------------------
# Builder against pipeline-persisted rows (needs Postgres)
# ---------------------------------------------------------------------------


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
) -> str:
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/report-{uuid.uuid4().hex[:8]}"},
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


def test_autonomous_report_json(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_AUTONOMOUS")
    evaluation = EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id))
    assert evaluation is not None

    report = build_report_json(db_session, evaluation, report_version=1)
    validated = ReportV1.model_validate(report)  # canonical schema round-trip
    assert validated.report_version == 1

    assert report["schema_version"] == "report_v1"
    assert report["evaluation"]["evaluation_mode"] == "AI_AUTONOMOUS"
    assert report["evaluation"]["status"] == "FINALIZED"
    assert report["evaluation"]["model_ref"].startswith("org/report-")
    assert report["mode_disclosure"]["human_reviewed"] is False
    assert report["mode_disclosure"]["disclaimer"] == AUTONOMOUS_DISCLAIMER
    assert report["score"]["score_type"] == "original_FRIES"
    assert "not FRIES2" in report["score"]["note"]
    assert "not ground truth" in report["score"]["note"]
    assert report["score"]["fries_score"] > 0
    assert set(report["score"]["dimension_scores"]) == {
        "FAIRNESS", "ROBUSTNESS", "INTEGRITY", "EXPLAINABILITY", "SAFETY",
    }
    assert report["score"]["finalized_osd"]["source"] == "osd_agent_autonomous"

    assert len(report["probes"]) == 5
    for probe in report["probes"]:
        assert probe["evidence_refs"], probe["dimension"]
        for ref in probe["evidence_refs"]:
            assert ref["evidence_id"]
            assert ref["hash"].startswith("sha256:")
        assert isinstance(probe["flags"], list)

    assert report["osd_agent"] is not None
    assert report["osd_agent"]["methodology_status"] == "PROPOSED_REQUIRES_VALIDATION"
    assert report["human_review"] is None
    assert report["attack_flags"] == []
    assert "AI-AUTONOMOUS" in report["executive_summary"]["headline"]


def test_assisted_report_after_review_differs_from_autonomous(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    seeded_users: dict[str, tuple[User, str]],
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_ASSISTED")
    _review_and_finalize(api_client, seeded_users, eval_id)
    evaluation = EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id))
    assert evaluation is not None

    report = build_report_json(db_session, evaluation, report_version=1)
    ReportV1.model_validate(report)

    assert report["evaluation"]["evaluation_mode"] == "AI_ASSISTED"
    assert report["mode_disclosure"]["human_reviewed"] is True
    assert report["mode_disclosure"]["disclaimer"] == ASSISTED_REVIEWED_DISCLAIMER
    assert report["score"]["finalized_osd"]["source"] == "human_review_assisted"
    assert report["human_review"] is not None
    assert report["human_review"]["accept_all"] is True
    assert "AI-ASSISTED" in report["executive_summary"]["headline"]
    assert "human-reviewed" in report["executive_summary"]["headline"]


def test_builder_requires_final_scores(
    api_client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(api_client, auth_headers, db_session, mode="AI_ASSISTED")
    evaluation = EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id))
    assert evaluation is not None
    assert evaluation.status.value == "AWAITING_REVIEW"

    with pytest.raises(ValueError, match="no final_scores"):
        build_report_json(db_session, evaluation, report_version=1)
