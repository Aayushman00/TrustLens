"""FastAPI dependencies — DB session, JWT auth, and RBAC helpers."""

from __future__ import annotations

import uuid
from collections.abc import Generator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.errors import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.db.enums import EvaluationMode, UserRole
from app.db.models import Evaluation, User
from app.db.repositories.evaluation import EvaluationRepository
from app.services.auth_service import AuthService

security = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a sync SQLAlchemy session; commit on success, rollback on error."""
    settings = get_settings()
    if not settings.database_url:
        raise AppError(
            "DATABASE_UNCONFIGURED",
            "DATABASE_URL is not set",
            status_code=503,
        )
    factory = get_session_factory(settings.database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Decode the Bearer access token and load the User, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Missing bearer token")
    return AuthService(db).get_user_from_access_token(credentials.credentials)


def require_roles(*roles: UserRole):
    """Dependency factory — 403 FORBIDDEN if user.role not in roles."""

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise ForbiddenError(
                f"Requires role(s): {', '.join(sorted(r.value for r in roles))}",
                details={
                    "required_roles": sorted(r.value for r in roles),
                    "actual_role": current_user.role.value,
                },
            )
        return current_user

    return _dependency


def require_reviewer_for_assisted_finalize(
    evaluation_id: uuid.UUID,
    user: User,
    db: Session,
) -> Evaluation:
    """For finalize stub: AI_ASSISTED requires reviewer/admin; AI_AUTONOMOUS does not."""
    evaluation = EvaluationRepository(db).get_by_id(evaluation_id)
    if evaluation is None:
        raise NotFoundError(
            f"Evaluation {evaluation_id} not found",
            details={"evaluation_id": str(evaluation_id)},
        )
    if evaluation.evaluation_mode == EvaluationMode.AI_ASSISTED and user.role not in (
        UserRole.REVIEWER,
        UserRole.ADMIN,
    ):
        raise ForbiddenError(
            "AI-Assisted finalize requires reviewer or admin role",
            details={
                "evaluation_id": str(evaluation_id),
                "evaluation_mode": evaluation.evaluation_mode.value,
            },
        )
    return evaluation


def require_owner_or_admin_for_publish(
    evaluation_id: uuid.UUID,
    user: User,
    db: Session,
) -> Evaluation:
    """Publish/unpublish: admin, or the evaluation's creator, may act."""
    evaluation = EvaluationRepository(db).get_by_id(evaluation_id)
    if evaluation is None:
        raise NotFoundError(
            f"Evaluation {evaluation_id} not found",
            details={"evaluation_id": str(evaluation_id)},
        )
    if user.role == UserRole.ADMIN:
        return evaluation
    if evaluation.created_by is not None and evaluation.created_by == user.id:
        return evaluation
    raise ForbiddenError(
        "Only the evaluation owner or an admin can publish/unpublish",
        details={"evaluation_id": str(evaluation_id)},
    )
