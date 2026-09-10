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
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.final_score import FinalScoreRepository
from app.reports.builder import build_executive_summary, build_report_json
from app.reports.render import render_html, render_pdf
from app.schemas.internal import EvaluateModelPayload
from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION
from app.schemas.modes import (
    ASSISTED_REVIEWED_LEGACY_DISCLAIMER,
    LEGACY_AUTONOMOUS_DISCLAIMER,
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
from tests.conftest import LEGACY_HEURISTIC_PROBE_CONFIG, fries_complete_model_payload
from tests.fakes import FakeEvidenceStore


@pytest.fixture(autouse=True)
def _complete_fries_probes(
    evaluated_robustness: None,
    evaluated_fairness: None,
) -> None:
    return

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
    assert "human-reviewed (accept/edit of O/S/D representation)" in summary.headline
    assert any("Human reviewed: yes" in bullet for bullet in summary.bullets)


# ---------------------------------------------------------------------------
# Render smoke tests — hand-built report, no DB
# ---------------------------------------------------------------------------


def _sample_report(*, mode: EvaluationMode, human_reviewed: bool) -> dict[str, Any]:
    report = ReportV1(
        report_version=1,
        generated_at=datetime.now(UTC),
        methodology_version=LEGACY_METHODOLOGY_VERSION,
        evaluation=ReportEvaluation(
            id=uuid.uuid4(),
            status=EvaluationStatus.FINALIZED,
            evaluation_mode=mode,
            model_ref="org/sample-model",
            model_id=1,
            created_at=datetime.now(UTC),
        ),
        mode_disclosure=build_mode_disclosure(
            evaluation_mode=mode,
            human_reviewed=human_reviewed,
            assessment_engine="legacy_heuristic",
            methodology_status="LEGACY_HEURISTIC_OSD_V1",
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
    assert "AUTO-FINALIZE (NO HUMAN REVIEW)" in html
    assert LEGACY_AUTONOMOUS_DISCLAIMER in html
    assert "O (Occurrence)" in html
    assert "4.05" in html
    assert "original_FRIES" in html
    assert "ev-smoke-123" in html  # evidence IDs surface in the PDF projection
    assert "low_n" in html
    assert "Sample headline" in html


def test_render_html_assisted_smoke() -> None:
    html = render_html(_sample_report(mode=EvaluationMode.AI_ASSISTED, human_reviewed=True))
    assert "HUMAN REVIEW BEFORE FINALIZE" in html
    assert ASSISTED_REVIEWED_LEGACY_DISCLAIMER in html
    assert "Human reviewed:</strong> yes" in html


def test_render_html_includes_phase5_sections_scored() -> None:
    """Phase 7 PDF-parity: the HTML/PDF projection must consume the same
    canonical report dict as the web page — no second calculation, and no
    section silently dropped from the PDF."""
    html = render_html(_sample_report(mode=EvaluationMode.AI_ASSISTED, human_reviewed=True))
    for heading in (
        "Evaluation Contract",
        "Model Identity",
        "Dataset Identity",
        "Local Execution Environment",
        "Evidence Traceability",
        "Human O/S/D Assessment",
        "Reproducibility Information",
        "Documentation Sources",
        "Limitations",
    ):
        assert heading in html, f"missing section: {heading}"
    # score.fries_score=4.05 in this fixture -> real number rendered, not "None".
    assert "4.05 / 10" in html
    assert "None / 10" not in html


def test_render_html_withheld_score_shows_explicit_callout_not_blank() -> None:
    """A withheld score (fries_score=None) must render an explicit callout,
    never an empty/broken score line."""
    report = ReportV1.model_validate(
        _sample_report(mode=EvaluationMode.AI_AUTONOMOUS, human_reviewed=False)
    )
    withheld = report.model_copy(
        update={
            "score": report.score.model_copy(
                update={"fries_score": None, "dimension_scores": {}, "scoring_withheld": True}
            )
        }
    )
    html = render_html(withheld.model_dump(mode="json"))
    assert "FRIES withheld" in html
    assert "None / 10" not in html
    assert '<div class="score-big">' not in html  # no numeric score box when withheld


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
        json=fries_complete_model_payload(f"org/report-{uuid.uuid4().hex[:8]}"),
        headers=auth_headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={
            "model_id": model.json()["id"],
            "evaluation_mode": mode,
            "probe_config": LEGACY_HEURISTIC_PROBE_CONFIG,
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=model.json()["hf_repo_id"],
        evaluation_mode=EvaluationMode(mode),
        probe_config=LEGACY_HEURISTIC_PROBE_CONFIG,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()
    return eval_id


def _review_and_finalize(
    api_client: TestClient,
    headers: dict[str, str],
    eval_id: str,
) -> None:
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
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(api_client, admin_headers, db_session, mode="AI_AUTONOMOUS")
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
    assert report["mode_disclosure"]["disclaimer"] == LEGACY_AUTONOMOUS_DISCLAIMER
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
    assert report["osd_agent"]["methodology_status"] == "LEGACY_HEURISTIC_OSD_V1"
    assert report["human_review"] is None
    assert report["attack_flags"] == []
    assert "AI-AUTONOMOUS" in report["executive_summary"]["headline"]

    # --- Phase 5: Evidence Traceability ---
    # conclusion -> risk/status -> gate -> metric(in probes[]) -> evidence
    # -> human O/S/D -> FRIES, per dimension. Every value here must be a
    # direct copy of something already asserted above/elsewhere — never a
    # second, independently-computed number.
    assert len(report["evidence_traceability"]) == 5
    probes_by_dim = {p["dimension"]: p for p in report["probes"]}
    for entry in report["evidence_traceability"]:
        dim = entry["dimension"]
        assert dim in probes_by_dim
        # status/aspect_scoring/risks/gates must match the same probe's own
        # metric_values — same extraction, not a re-derivation.
        pm = probes_by_dim[dim]["metric_values"]
        assert entry["status"] == (pm.get("probe_status") or pm.get("status"))
        assert entry["risks_triggered"] == pm.get("risks_triggered")
        # human O/S/D + the FRIES per-dimension number are both populated
        # (scoring is complete in this fixture) and match final_scores
        # exactly — cross-checked against the score section already
        # asserted above, not recomputed here.
        assert entry["fries_dimension_score"] == report["score"]["dimension_scores"][dim]
        assert entry["human_osd"] is not None
        assert entry["human_osd"]["O"] is not None
        assert entry["human_osd"]["S"] is not None
        assert entry["human_osd"]["D"] is not None
        # Raw metric numbers (e.g. accuracy_drop) live only in probes[], not
        # duplicated into the traceability entry.
        assert "accuracy_drop" not in entry
        assert "demographic_parity_difference" not in entry

    # --- Phase 5: Documentation coverage vs "Explainability score" ---
    explainability_entry = next(e for e in report["evidence_traceability"] if e["dimension"] == "EXPLAINABILITY")
    assert explainability_entry["coverage_ratio"] is not None
    import json as _json
    report_text = _json.dumps(report).lower()
    assert "explainability score" not in report_text
    assert "explainability=" not in report_text.replace(" ", "")

    # --- Phase 5: no behavioral safety claim ---
    safety_entry = next(e for e in report["evidence_traceability"] if e["dimension"] == "SAFETY")
    assert safety_entry["limitations"], "Safety limitations must be present, disclosing Track 1 scope"

    # --- Phase 5: Reproducibility / Limitations / execution_environment ---
    assert report["reproducibility"]["model_ref"] == report["evaluation"]["model_ref"]
    assert report["reproducibility"]["model_revision"] == "a" * 40
    assert isinstance(report["limitations"], list)
    assert len(report["limitations"]) > 0  # every probe records at least one
    # No probe in this fixture ran real local inference (documentation/
    # governance-only probes plus a proxy-free contract) -> None, never
    # fabricated GPU/device evidence.
    assert report["execution_environment"] is None
    # No model import (HF adapter) happened in this fixture -> no
    # documentation_sources rows exist yet; empty list, not fabricated.
    assert report["documentation_sources"] == []


def test_assisted_report_after_review_differs_from_autonomous(
    api_client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    eval_id = _create_and_run(api_client, admin_headers, db_session, mode="AI_ASSISTED")
    _review_and_finalize(api_client, admin_headers, eval_id)
    evaluation = EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id))
    assert evaluation is not None

    report = build_report_json(db_session, evaluation, report_version=1)
    ReportV1.model_validate(report)

    assert report["evaluation"]["evaluation_mode"] == "AI_ASSISTED"
    assert report["mode_disclosure"]["human_reviewed"] is True
    assert report["mode_disclosure"]["disclaimer"] == ASSISTED_REVIEWED_LEGACY_DISCLAIMER
    assert report["score"]["finalized_osd"]["source"] == "human_review_assisted"
    assert report["human_review"] is not None
    assert report["human_review"]["accept_all"] is True
    assert "AI-ASSISTED" in report["executive_summary"]["headline"]
    assert "human-reviewed" in report["executive_summary"]["headline"]


def test_builder_requires_finalized_status(
    api_client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    """Not-yet-finalized (AWAITING_REVIEW) still raises — distinct from the
    FINALIZED-but-withheld case, which now builds a full report instead
    (see test_finalized_withheld_report_is_complete_not_an_error below)."""
    eval_id = _create_and_run(api_client, admin_headers, db_session, mode="AI_ASSISTED")
    evaluation = EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id))
    assert evaluation is not None
    assert evaluation.status.value == "AWAITING_REVIEW"

    with pytest.raises(ValueError, match="not finalized"):
        build_report_json(db_session, evaluation, report_version=1)


def test_report_includes_documentation_sources_when_model_was_hf_imported(
    api_client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    """Phase 2's documentation_sources rows must surface in the Phase 5
    report — read-only passthrough, no re-fetch/re-hash here."""
    from app.adapters.base import NormalizedModelRecord
    from app.db.repositories.documentation import DocumentationSourceRepository
    from app.schemas.models import ImportHfRequest
    from app.services.model_service import ModelService

    hf_repo_id = f"org/doc-report-{uuid.uuid4().hex[:8]}"
    record = NormalizedModelRecord(
        hf_repo_id=hf_repo_id,
        revision="b" * 40,
        checksum="b" * 40,
        model_metadata={
            "card_text": "# Card\nIntended use, limitations, training data, evaluation, ethics.",
            "documentation_evidence": {
                "documentation_source_type": "model_card",
                "documentation_url": f"https://huggingface.co/{hf_repo_id}/blob/{'b' * 40}/README.md",
                "documentation_revision": "b" * 40,
                "documentation_content_hash": "sha256:deadbeef",
                "retrieval_status": "ok",
                "retrieval_error": None,
                "content_length": 42,
                "source_model_ref": hf_repo_id,
                "source_model_revision": "b" * 40,
            },
        },
    )

    class _FakeAdapter:
        def resolve(self, ref: str, revision: str | None = None) -> NormalizedModelRecord:
            return record

    model = ModelService(db_session, hf_adapter=_FakeAdapter()).import_from_hf(
        ImportHfRequest(repo_id=hf_repo_id)
    )
    db_session.flush()
    assert DocumentationSourceRepository(db_session).list_for_model(model.id)

    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.id, "evaluation_mode": "AI_AUTONOMOUS"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    evaluation = EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id))
    assert evaluation is not None
    report = build_report_json(db_session, evaluation, report_version=1)
    ReportV1.model_validate(report)
    assert len(report["documentation_sources"]) == 1
    doc = report["documentation_sources"][0]
    assert doc["source_kind"] == "huggingface_hub"
    assert doc["documentation_content_hash"] == "sha256:deadbeef"
    assert doc["retrieval_status"] == "ok"


def test_finalized_withheld_report_is_complete_not_an_error(
    api_client: TestClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    """Phase 5: a FINALIZED evaluation with FRIES withheld (deterministic
    engine, no human review completing all 5 aspects) must still produce a
    complete evidentiary report — not raise, not fabricate a score."""
    model = api_client.post(
        "/v1/models",
        json={"hf_repo_id": f"org/withheld-report-{uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert model.status_code == 201, model.text
    created = api_client.post(
        "/v1/evaluations",
        json={"model_id": model.json()["id"], "evaluation_mode": "AI_AUTONOMOUS"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    eval_id = created.json()["id"]
    payload = EvaluateModelPayload(
        evaluation_id=uuid.UUID(eval_id),
        model_ref=model.json()["hf_repo_id"],
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    run_evaluation_pipeline(db_session, payload, evidence_store=FakeEvidenceStore())
    db_session.flush()

    evaluation = EvaluationRepository(db_session).get_by_id(uuid.UUID(eval_id))
    assert evaluation is not None
    assert evaluation.status == EvaluationStatus.FINALIZED
    assert FinalScoreRepository(db_session).get_for_evaluation(evaluation.id) is None

    report = build_report_json(db_session, evaluation, report_version=1)
    validated = ReportV1.model_validate(report)  # must validate — no schema violation
    assert validated.score.scoring_withheld is True
    assert validated.score.fries_score is None
    assert validated.score.dimension_scores == {}
    assert "FRIES withheld" in report["executive_summary"]["headline"]
    assert any("withheld" in b.lower() for b in report["executive_summary"]["bullets"])

    # The rest of the report is still fully populated — this is a complete
    # evidentiary report, not a stub.
    assert len(report["probes"]) == 5
    assert len(report["evidence_traceability"]) == 5
    for entry in report["evidence_traceability"]:
        assert entry["fries_dimension_score"] is None  # never fabricated
        assert entry["human_osd"] is None  # nothing settled yet — never a default

    # Not generated via the API for this failing test alone (needs the report
    # service layer 409 removal) — checked separately in test_api_reports.py.
