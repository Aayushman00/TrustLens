"""Repository CRUD tests (requires migrated Postgres)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.enums import EvaluationMode, EvaluationStatus, UserRole
from app.db.repositories import EvaluationRepository, ModelRepository, UserRepository


def test_user_model_evaluation_repositories(db_session: Session) -> None:
    users = UserRepository(db_session)
    models = ModelRepository(db_session)
    evaluations = EvaluationRepository(db_session)

    user = users.create(
        email=f"researcher-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="placeholder",
        role=UserRole.RESEARCHER,
    )
    assert users.get_by_id(user.id) is not None
    assert users.get_by_email(user.email) is not None

    model = models.create(
        hf_repo_id=f"org/repo-{uuid.uuid4().hex[:8]}",
        model_metadata={"license": "mit"},
        checksum="sha256:00",
        revision="abc123",
    )
    assert models.get_by_hf_repo_id(model.hf_repo_id) is not None

    evaluation = evaluations.create(
        model_id=model.id,
        evaluation_mode=EvaluationMode.AI_AUTONOMOUS,
        task="image-classification",
        trustlens_version="0.3.0",
    )
    assert evaluation.status is EvaluationStatus.PENDING
    assert evaluations.get_by_id(evaluation.id) is not None

    updated = evaluations.update_status(evaluation.id, EvaluationStatus.RUNNING)
    assert updated is not None
    assert updated.status is EvaluationStatus.RUNNING

    pending = evaluations.list_by_status(EvaluationStatus.PENDING)
    running = evaluations.list_by_status(EvaluationStatus.RUNNING)
    assert all(e.status is EvaluationStatus.PENDING for e in pending)
    assert any(e.id == evaluation.id for e in running)
