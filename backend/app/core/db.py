"""Sync SQLAlchemy engine, health ping, and session helpers."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(database_url: str) -> Engine:
    """Return a process-wide sync engine."""
    global _engine, _SessionLocal
    if _engine is None or str(_engine.url) != database_url:
        _engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _SessionLocal = sessionmaker(
            bind=_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _engine


def get_session_factory(database_url: str) -> sessionmaker[Session]:
    """Return the session factory bound to ``database_url``."""
    get_engine(database_url)
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def get_session(database_url: str) -> Iterator[Session]:
    """Yield a session; commit on success, rollback on error, always close."""
    factory = get_session_factory(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def session_scope(database_url: str) -> Generator[Session, None, None]:
    """Generator form of ``get_session`` (e.g. for FastAPI Depends in Phase 4)."""
    with get_session(database_url) as session:
        yield session


def check_postgres(database_url: str | None) -> str:
    """Return 'ok', 'error', or 'skipped' (URL unset)."""
    if not database_url:
        return "skipped"
    try:
        engine = get_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def reset_engine() -> None:
    """Dispose cached engine (tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
