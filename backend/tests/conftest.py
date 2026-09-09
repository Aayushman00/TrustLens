"""Shared fixtures for DB integration tests.

DB-backed tests connect only through ``TEST_DATABASE_URL`` — never
``DATABASE_URL`` (the development database) — and skip cleanly when no
database is configured at all. See ``resolve_test_database_url`` (audit
P1-2). Compose service hostname ``postgres`` is rewritten to ``127.0.0.1``
for host-side runs.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from dotenv import load_dotenv

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The exact database name TrustLens development/Compose uses (.env.example,
# docker-compose.yml POSTGRES_DB). TEST_DATABASE_URL must never resolve to
# this name — that is precisely the dev database the destructive migration
# test (test_migrations.py) would otherwise be able to wipe (audit P1-2).
_KNOWN_DEV_DB_NAMES = {"trustlens"}


class UnsafeTestDatabaseError(RuntimeError):
    """TEST_DATABASE_URL is missing or unsafe — never silently use DATABASE_URL."""


def _bootstrap_test_env() -> None:
    """Load repo-root ``.env`` and normalize Compose hostnames for host-side pytest."""
    env_path = _REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)

    db_url = os.environ.get("DATABASE_URL")
    if db_url and "@postgres:" in db_url:
        os.environ["DATABASE_URL"] = db_url.replace("@postgres:", "@127.0.0.1:")

    test_db_url = os.environ.get("TEST_DATABASE_URL")
    if test_db_url and "@postgres:" in test_db_url:
        os.environ["TEST_DATABASE_URL"] = test_db_url.replace("@postgres:", "@127.0.0.1:")

    redis_url = os.environ.get("REDIS_URL")
    if redis_url and "redis://redis:" in redis_url:
        os.environ["REDIS_URL"] = redis_url.replace("redis://redis:", "redis://127.0.0.1:")

    s3_endpoint = os.environ.get("S3_ENDPOINT")
    if s3_endpoint and "http://minio:" in s3_endpoint:
        os.environ["S3_ENDPOINT"] = s3_endpoint.replace("http://minio:", "http://127.0.0.1:")


_bootstrap_test_env()
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import get_engine, reset_engine
from tests.fakes import patch_evaluated_fairness, patch_evaluated_robustness

LEGACY_HEURISTIC_PROBE_CONFIG = {
    "schema_version": "v1",
    "assessment_engine": "legacy_heuristic",
}

# Enough Hub metadata for Layer A Integrity/E/S so the legacy heuristic can
# emit complete O/S/D (empty models abstain Integrity → FRIES withheld).
def fries_complete_model_payload(hf_repo_id: str) -> dict:
    return {
        "hf_repo_id": hf_repo_id,
        "revision": "a" * 40,
        "checksum": "a" * 40,
        "model_metadata": {
            "license": "apache-2.0",
            "card_text": (
                "Model card. Intended use for research. Limitations listed. "
                "Training data described. Evaluation on a public benchmark. "
                "Ethical considerations. Privacy. Security. Misuse guidance."
            ),
            "card_data": {"license": "apache-2.0"},
            "files": [
                "config.json",
                "model.safetensors",
                "tokenizer.json",
                "README.md",
            ],
        },
    }

BACKEND_ROOT = Path(__file__).resolve().parents[1]

get_settings.cache_clear()


def _db_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/").split("?", 1)[0].lower()


def resolve_test_database_url() -> str | None:
    """Resolve the dedicated test database URL — the ONLY database DB-backed
    tests may connect to. Never reads/falls back to DATABASE_URL.

    Returns ``None`` only when no database is configured at all (a pure
    unit-only local run with no ``.env``/Postgres present) — DB-backed tests
    skip in that case, exactly as before this fix. The moment any database
    connection is configured (``DATABASE_URL`` set, e.g. from ``.env``),
    ``TEST_DATABASE_URL`` becomes mandatory: this is precisely the ambiguous
    state the audit flagged, where tests could silently reach the real
    development database (P1-2).
    """
    test_url = os.environ.get("TEST_DATABASE_URL")
    dev_url = os.environ.get("DATABASE_URL")

    if not test_url and not dev_url:
        return None

    if not test_url:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL is not set, but a database connection is "
            "configured (DATABASE_URL). DB-backed tests — including the "
            "destructive Alembic migration test — require a dedicated "
            "TEST_DATABASE_URL and will never fall back to DATABASE_URL. Set "
            "TEST_DATABASE_URL to a distinctly-named database, e.g.\n"
            "  postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens_test\n"
            "See backend/tests/README.md."
        )

    url = test_url.replace("@postgres:", "@127.0.0.1:")
    db_name = _db_name(url)
    if db_name in _KNOWN_DEV_DB_NAMES:
        raise UnsafeTestDatabaseError(
            f"TEST_DATABASE_URL points at database {db_name!r}, which matches "
            "the known TrustLens development/Compose database name. Refusing "
            "to run DB-backed tests — including the destructive migration "
            "test — against it. Use a distinctly-named test database (e.g. "
            f"{db_name}_test)."
        )

    normalized_dev = (dev_url or "").replace("@postgres:", "@127.0.0.1:")
    if normalized_dev and url == normalized_dev:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL is identical to DATABASE_URL. Tests must use a "
            "database dedicated to testing, never the development database."
        )

    return url


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture(scope="session")
def database_url() -> str:
    """The isolated test database URL — every DB-backed test (ORM, API,
    lifecycle, and the destructive migration round-trip) connects only
    through this fixture, which resolves exclusively from
    ``TEST_DATABASE_URL`` (see ``resolve_test_database_url``)."""
    url = resolve_test_database_url()
    if not url:
        pytest.skip("No database configured — skipping DB integration tests")
    reset_engine()
    engine = get_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres unreachable at TEST_DATABASE_URL ({exc})")
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


@pytest.fixture
def evaluated_robustness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in: robustness probe emits EVALUATED accuracies (complete FRIES path)."""
    patch_evaluated_robustness(monkeypatch)


@pytest.fixture
def evaluated_fairness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in: fairness probe emits EVALUATED disparity metrics (complete FRIES path)."""
    patch_evaluated_fairness(monkeypatch)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """No-op — TrustLens is a single-user local app with no auth headers."""
    return {}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """No-op — TrustLens is a single-user local app with no auth headers."""
    return {}


class FakeS3Client:
    """Minimal in-memory S3/boto3 client for storage tests."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str | None = None,
        Metadata: dict[str, str] | None = None,
    ) -> dict:
        """Store an object in memory."""
        self.objects[(Bucket, Key)] = Body
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        """Retrieve an object from memory."""
        if (Bucket, Key) not in self.objects:
            from botocore.exceptions import NoSuchKey

            raise NoSuchKey(
                error_response={"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
                operation_name="GetObject",
            )
        data = self.objects[(Bucket, Key)]

        class FakeBody:
            def read(self) -> bytes:
                return data

        return {"Body": FakeBody()}


@pytest.fixture
def fake_s3_client() -> FakeS3Client:
    """In-memory S3 client for storage tests."""
    return FakeS3Client()
