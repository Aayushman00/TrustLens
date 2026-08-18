"""ORM insert / FK enforcement tests (requires migrated Postgres)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.enums import (
    EvaluationMode,
    EvaluationStatus,
    FriesDimension,
    UserRole,
)
from app.db.models import (
    AttackFlag,
    Evaluation,
    FinalScore,
    HumanReview,
    Model,
    OsdAgentOutput,
    ProbeResult,
    Report,
    User,
)


def _seed_model_and_eval(session: Session) -> Evaluation:
    model = Model(
        hf_repo_id=f"org/model-{uuid.uuid4().hex[:8]}",
        model_metadata={"source": "test"},
        checksum="sha256:deadbeef",
        revision="main",
    )
    session.add(model)
    session.flush()

    evaluation = Evaluation(
        id=uuid.uuid4(),
        model_id=model.id,
        status=EvaluationStatus.PENDING,
        evaluation_mode=EvaluationMode.AI_ASSISTED,
        probe_config={"probes": ["robustness"]},
        task="text-classification",
        dataset="glue",
        trustlens_version="0.3.0",
    )
    session.add(evaluation)
    session.flush()
    return evaluation


def test_insert_dummy_rows_across_tables(db_session: Session) -> None:
    user = User(
        email=f"reviewer-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        role=UserRole.REVIEWER,
    )
    db_session.add(user)
    db_session.flush()

    evaluation = _seed_model_and_eval(db_session)

    db_session.add(
        ProbeResult(
            evaluation_id=evaluation.id,
            dimension=FriesDimension.ROBUSTNESS,
            metric_values={"robust_acc": 0.9},
            confidence=0.8,
            evidence_refs=[
                {
                    "evidence_id": "ev-1",
                    "uri": "s3://trustlens/ev-1.json",
                    "hash": "sha256:abc",
                    "content_type": "application/json",
                    "probe_name": "robustness",
                }
            ],
        )
    )
    db_session.add(
        OsdAgentOutput(
            evaluation_id=evaluation.id,
            ai_suggestion={"O": 7, "S": 8, "D": 6},
            ai_confidence=0.7,
            evidence_used=["ev-1"],
            rationale="test",
        )
    )
    db_session.add(
        HumanReview(
            evaluation_id=evaluation.id,
            reviewer_id=user.id,
            overrides={"O": 8},
            human_changed=True,
            notes="adjusted O",
        )
    )
    db_session.add(
        FinalScore(
            evaluation_id=evaluation.id,
            fries_score=7.5,
            dimension_scores={"ROBUSTNESS": 7.5},
            finalized_osd={"O": 8, "S": 8, "D": 6},
            overall_confidence=0.75,
            evaluation_mode=EvaluationMode.AI_ASSISTED,
        )
    )
    db_session.add(
        Report(
            evaluation_id=evaluation.id,
            json_uri="s3://trustlens/report.json",
            pdf_uri="s3://trustlens/report.pdf",
            version=1,
        )
    )
    db_session.add(
        AttackFlag(
            evaluation_id=evaluation.id,
            scenario="stub",
            severity="low",
            detected=False,
            details={},
        )
    )
    db_session.flush()

    assert db_session.get(Evaluation, evaluation.id) is not None
    assert evaluation.is_published is False


def test_orphan_probe_result_fk_raises(db_session: Session) -> None:
    orphan_id = uuid.uuid4()
    db_session.add(
        ProbeResult(
            evaluation_id=orphan_id,
            dimension=FriesDimension.FAIRNESS,
            metric_values={},
            evidence_refs=[],
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
