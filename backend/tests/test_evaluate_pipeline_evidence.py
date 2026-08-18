"""Pipeline populates five probe_results.evidence_refs via EvidenceStore (Phase 9–16)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode
from app.db.models import ProbeResult
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.model import ModelRepository
from app.probes.base import FRIES_PROBE_ORDER
from app.schemas.internal import EvaluateModelPayload
from app.storage.evidence_store import format_sha256
from app.tasks.evaluate_pipeline import run_evaluation_pipeline
from tests.fakes import FakeEvidenceStore


def test_pipeline_writes_evidence_ref(db_session: Session) -> None:
    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(
        hf_repo_id=f"org/ev-{uuid.uuid4().hex[:8]}",
        model_metadata={
            "license": "apache-2.0",
            "card_text": "Trained on dataset. Evaluation on benchmark. seed=7.",
            "files": ["config.json", "model.safetensors"],
        },
        revision="c" * 40,
        checksum="c" * 40,
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
    run_evaluation_pipeline(db_session, payload, evidence_store=store)  # type: ignore[arg-type]
    db_session.flush()

    rows = list(
        db_session.scalars(
            select(ProbeResult)
            .where(ProbeResult.evaluation_id == evaluation.id)
            .order_by(ProbeResult.id)
        ).all()
    )
    assert len(rows) == 5
    assert [r.dimension for r in rows] == list(FRIES_PROBE_ORDER)
    assert len(store.puts) == 5

    for row, expected_dim in zip(rows, FRIES_PROBE_ORDER, strict=True):
        refs = row.evidence_refs
        assert len(refs) == 1
        ref = refs[0]
        assert ref["evidence_id"]
        assert ref["hash"].startswith("sha256:")
        assert ref["uri"].startswith("s3://trustlens/evidence/")
        assert ref["probe_name"] == expected_dim.value.lower()
        assert ref["content_type"] == "application/json"
        key = store.key_from_uri(ref["uri"])
        stored = store.get_artifact(key=key)
        assert format_sha256(stored) == ref["hash"]
        # Phase 15: engine confidence + factors persisted for every dimension.
        factors = row.metric_values.get("confidence_factors")
        assert isinstance(factors, dict)
        assert row.confidence == factors["combined"]
        if expected_dim.value == "INTEGRITY":
            assert "checks" in row.metric_values
            assert "integrity_score_0_10" in row.metric_values
            assert row.metric_values.get("stub") is not True
        elif expected_dim.value == "ROBUSTNESS":
            assert row.metric_values.get("stub") is not True
            assert row.metric_values.get("attack") == "char_swap"
            assert row.metric_values.get("proposed_mapping") is False
        elif expected_dim.value == "FAIRNESS":
            assert row.metric_values.get("stub") is not True
            assert row.metric_values.get("proposed_mapping") is False
            assert (
                row.metric_values.get("demographic_parity_difference") is None
                or row.metric_values.get("needs_human_review") is True
            )
        elif expected_dim.value == "EXPLAINABILITY":
            assert row.metric_values.get("stub") is not True
            assert row.metric_values.get("proposed_mapping") is False
            assert "coverage_ratio" in row.metric_values
        elif expected_dim.value == "SAFETY":
            assert row.metric_values.get("stub") is not True
            assert row.metric_values.get("proposed_mapping") is False
            assert "coverage_ratio" in row.metric_values
            assert "checks" in row.metric_values
        else:
            raise AssertionError(f"unexpected dimension {expected_dim}")


def test_pipeline_fails_without_evidence_store(db_session: Session) -> None:
    from app.core.config import get_settings
    from app.db.enums import EvaluationStatus

    models = ModelRepository(db_session)
    evals = EvaluationRepository(db_session)
    model = models.create(hf_repo_id=f"org/no-s3-{uuid.uuid4().hex[:8]}")
    evaluation = evals.create(
        model_id=model.id,
        evaluation_mode=EvaluationMode.AI_ASSISTED,
    )
    db_session.flush()

    get_settings.cache_clear()
    payload = EvaluateModelPayload(
        evaluation_id=evaluation.id,
        model_ref=model.hf_repo_id,
        evaluation_mode=EvaluationMode.AI_ASSISTED,
    )
    import app.tasks.evaluate_pipeline as pipeline

    original = pipeline.get_evidence_store
    pipeline.get_evidence_store = lambda settings: None  # type: ignore[assignment]
    try:
        run_evaluation_pipeline(db_session, payload, evidence_store=None)
    finally:
        pipeline.get_evidence_store = original  # type: ignore[assignment]
        get_settings.cache_clear()

    db_session.flush()
    row = evals.get_by_id(evaluation.id)
    assert row is not None
    assert row.status == EvaluationStatus.FAILED
