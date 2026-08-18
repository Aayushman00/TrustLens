"""run_all_probes persists five probe_results with evidence (Phase 9–14)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, FriesDimension
from app.db.models import ProbeResult
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.model import ModelRepository
from app.probes.base import FRIES_PROBE_ORDER
from app.probes.runner import run_all_probes
from app.schemas.internal import EvaluateModelPayload
from tests.fakes import FakeEvidenceStore


def test_run_all_probes_inserts_five_rows(db_session: Session) -> None:
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(
        hf_repo_id=f"org/probes-{uuid.uuid4().hex[:8]}",
        model_metadata={
            "license": "apache-2.0",
            "card_text": "Trained on dataset with seed=1. Evaluation metrics reported.",
            "files": ["config.json", "model.safetensors"],
            # Not text-classification → RobustnessProbe skip path (no torch).
            "pipeline_tag": "fill-mask",
        },
        revision="b" * 40,
        checksum="b" * 40,
    )
    evaluation = evals.create(
        model_id=model.id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    db_session.flush()

    store = FakeEvidenceStore()
    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
    )
    outputs = run_all_probes(
        db_session,
        payload,
        model_metadata=model.model_metadata or {},
        evidence_store=store,  # type: ignore[arg-type]
        model_revision=model.revision,
        model_checksum=model.checksum,
    )
    db_session.flush()

    assert len(outputs) == 5
    assert [o.dimension for o in outputs] == list(FRIES_PROBE_ORDER)
    assert len(store.puts) == 5

    rows = list(
        db_session.scalars(
            select(ProbeResult)
            .where(ProbeResult.evaluation_id == evaluation.id)
            .order_by(ProbeResult.id)
        ).all()
    )
    assert len(rows) == 5
    assert [r.dimension for r in rows] == list(FRIES_PROBE_ORDER)

    for row in rows:
        assert row.evidence_refs
        assert row.evidence_refs[0]["hash"].startswith("sha256:")
        assert row.metric_values.get("stub") is not True
        # Phase 15: engine-refined confidence + factors persisted in metric_values.
        factors = row.metric_values.get("confidence_factors")
        assert isinstance(factors, dict)
        assert set(factors) == {
            "data_quality",
            "probe_reliability",
            "evidence_completeness",
            "combined",
        }
        assert row.confidence == factors["combined"]
        assert 0.0 < row.confidence <= 1.0
        if row.dimension == FriesDimension.FAIRNESS:
            assert row.metric_values.get("proposed_mapping") is False
            assert (
                "metrics_skipped" in (outputs[0].flags or [])
                or row.metric_values.get("needs_human_review") is True
            )
        elif row.dimension == FriesDimension.ROBUSTNESS:
            assert row.metric_values.get("proposed_mapping") is False
            assert row.metric_values.get("attack") == "char_swap"
            assert "unsupported_modality" in (outputs[1].flags or [])
        elif row.dimension == FriesDimension.EXPLAINABILITY:
            assert row.metric_values.get("proposed_mapping") is False
            assert "coverage_ratio" in row.metric_values
            assert 0.0 <= float(row.metric_values["coverage_ratio"]) <= 1.0
        elif row.dimension == FriesDimension.SAFETY:
            assert row.metric_values.get("proposed_mapping") is False
            assert "coverage_ratio" in row.metric_values
            assert "checks" in row.metric_values
            assert 0.0 <= float(row.metric_values["coverage_ratio"]) <= 1.0
        else:
            assert row.dimension == FriesDimension.INTEGRITY
            assert "checks" in row.metric_values
            assert "integrity_score_0_10" in row.metric_values
            assert 0.0 <= (row.confidence or 0) <= 1.0

    # Skipped robustness (unsupported modality) must score below metadata integrity.
    by_dim = {row.dimension: row for row in rows}
    assert (
        by_dim[FriesDimension.ROBUSTNESS].confidence
        < by_dim[FriesDimension.INTEGRITY].confidence
    )
