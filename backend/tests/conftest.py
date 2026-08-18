"""Shared fixtures for DB integration tests.

Tests that need Postgres skip when ``DATABASE_URL`` is unset or unreachable.
Compose service hostname ``postgres`` is rewritten to ``127.0.0.1`` for host-side runs.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import get_engine, reset_engine
from app.core.security import hash_password
from app.db.enums import UserRole
from app.db.models import User
from app.db.repositories.user import UserRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def resolve_database_url() -> str | None:
    get_settings.cache_clear()
    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    if not url:
        return None
    # Host pytest cannot resolve Compose DNS name `postgres`
    return url.replace("@postgres:", "@127.0.0.1:")


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture(scope="session")
def database_url() -> str:
    url = resolve_database_url()
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB integration tests")
    reset_engine()
    engine = get_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres unreachable at DATABASE_URL ({exc})")
    return url


@pytest.fixture(scope="session")
def ensure_migrated(database_url: str) -> None:
    """Apply Alembic head once per test session so ORM tests have tables."""
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(_alembic_config(database_url), "head")


@pytest.fixture
def db_session(database_url: str, ensure_migrated: None) -> Iterator[Session]:
    """Session wrapped in a transaction that always rolls back."""
    reset_engine()
    engine = get_engine(database_url)
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        reset_engine()


@pytest.fixture
def api_client(db_session: Session) -> Iterator["TestClient"]:
    """TestClient with get_db overridden to the transactional test session."""
    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.main import create_app

    application = create_app()

    def _override_db() -> Iterator[Session]:
        from app.api.errors import AppError

        try:
            yield db_session
            db_session.flush()
        except AppError:
            # Structured client errors (401/403/404/409/...) are expected control
            # flow, not DB corruption — don't roll back the test's shared
            # transaction and lose data written earlier in the same test.
            raise
        except Exception:
            db_session.rollback()
            raise

    application.dependency_overrides[get_db] = _override_db
    with TestClient(application) as client:
        yield client
    application.dependency_overrides.clear()


# Fixed dev-only passwords for tests — never used outside this test session.
SEEDED_PASSWORDS: dict[str, str] = {
    "admin": "admin-test-pass-123",
    "researcher": "researcher-test-pass-123",
    "reviewer": "reviewer-test-pass-123",
}


@pytest.fixture
def seeded_users(db_session: Session) -> dict[str, tuple[User, str]]:
    """Create one user per role with a known password, scoped to this test's transaction."""
    repo = UserRepository(db_session)
    users: dict[str, tuple[User, str]] = {}
    for key, role in (
        ("admin", UserRole.ADMIN),
        ("researcher", UserRole.RESEARCHER),
        ("reviewer", UserRole.REVIEWER),
    ):
        password = SEEDED_PASSWORDS[key]
        email = f"{key}-{uuid.uuid4().hex[:8]}@example.com"
        user = repo.create(email=email, password_hash=hash_password(password), role=role)
        users[key] = (user, password)
    db_session.flush()
    return users


def auth_headers_for(api_client: "TestClient", email: str, password: str) -> dict[str, str]:
    response = api_client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def auth_headers(api_client: "TestClient", seeded_users: dict[str, tuple[User, str]]) -> dict[str, str]:
    """Bearer header for the seeded researcher — the default authenticated caller."""
    user, password = seeded_users["researcher"]
    return auth_headers_for(api_client, user.email, password)
