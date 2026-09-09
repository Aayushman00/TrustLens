"""TEST_DATABASE_URL isolation guard (audit P1-2).

DB-backed tests — including the destructive Alembic migration round-trip in
test_migrations.py — must resolve their database exclusively from
TEST_DATABASE_URL and must never silently fall back to DATABASE_URL (the
development database). See conftest.py::resolve_test_database_url.
"""

from __future__ import annotations

import pytest

from tests.conftest import UnsafeTestDatabaseError, resolve_test_database_url


def test_neither_url_set_returns_none_for_clean_unit_only_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No DB configured at all — DB-backed tests skip, not fail (unit-only mode)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert resolve_test_database_url() is None


def test_missing_test_database_url_fails_clearly_when_dev_db_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured DATABASE_URL without TEST_DATABASE_URL must error, not
    silently reuse DATABASE_URL for tests."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens",
    )
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    with pytest.raises(UnsafeTestDatabaseError, match="TEST_DATABASE_URL is not set"):
        resolve_test_database_url()


def test_dev_database_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """TEST_DATABASE_URL pointing at the known dev DB name is refused, even
    on a different host, since a copy-pasted dev URL is the realistic mistake."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens",
    )
    with pytest.raises(UnsafeTestDatabaseError, match="trustlens"):
        resolve_test_database_url()


def test_identical_to_database_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with a non-default dev DB name, TEST_DATABASE_URL identical to
    DATABASE_URL must be rejected — the two must be genuinely distinct."""
    same_url = "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/renamed_dev_db"
    monkeypatch.setenv("DATABASE_URL", same_url)
    monkeypatch.setenv("TEST_DATABASE_URL", same_url)
    with pytest.raises(UnsafeTestDatabaseError, match="identical"):
        resolve_test_database_url()


def test_isolated_test_database_url_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """A distinctly-named TEST_DATABASE_URL resolves cleanly alongside a
    configured DATABASE_URL — the normal, safe local/CI configuration."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens",
    )
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens_test",
    )
    resolved = resolve_test_database_url()
    assert resolved == "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens_test"


def test_compose_hostname_is_rewritten_for_host_side_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://trustlens:trustlens@postgres:5432/trustlens_test",
    )
    resolved = resolve_test_database_url()
    assert resolved == "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens_test"


def test_database_url_fixture_uses_only_test_database_url(
    monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    """The shared ``database_url`` fixture (used by every DB-backed test,
    including test_migrations.py) must resolve to TEST_DATABASE_URL's value,
    never a raw DATABASE_URL — proving the destructive migration test can
    only ever run against the isolated database."""
    import os

    test_db = os.environ.get("TEST_DATABASE_URL", "").replace("@postgres:", "@127.0.0.1:")
    assert test_db, "TEST_DATABASE_URL must be configured to run this test"
    assert database_url == test_db
