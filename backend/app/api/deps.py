"""FastAPI dependencies — DB session."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.config import get_settings
from app.core.db import get_session_factory


def get_db() -> Generator[Session, None, None]:
    """Yield a sync SQLAlchemy session; commit on success, rollback on error.

    Always use as ``Depends(get_db, scope="function")``: with FastAPI's default
    request scope the commit runs after the response is sent, so a client
    acting on a 200 can read uncommitted state."""
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
