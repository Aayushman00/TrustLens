"""Migration upgrade / downgrade smoke tests (requires Postgres)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.core.db import get_engine, reset_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "models",
    "evaluations",
    "probe_results",
    "osd_agent_outputs",
    "human_reviews",
    "final_scores",
    "reports",
    "attack_flags",
    "documentation_sources",
    "evaluation_events",
    "alembic_version",
}


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.mark.slow
def test_alembic_upgrade_creates_tables(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_engine()
    cfg = _alembic_config(database_url)
    command.upgrade(cfg, "head")

    engine = get_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)
    # Single-user local instance — no users/identity table.
    assert "users" not in tables

    indexes = {idx["name"] for idx in inspect(engine).get_indexes("evaluations")}
    assert "ix_evaluations_status" in indexes
    assert "ix_evaluations_is_published" in indexes
    score_indexes = {idx["name"] for idx in inspect(engine).get_indexes("final_scores")}
    assert "ix_final_scores_fries_score" in score_indexes


@pytest.mark.slow
def test_alembic_downgrade_and_reupgrade(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Destructive: drops app tables then recreates them. Dev/CI DB only."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_engine()
    cfg = _alembic_config(database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = get_engine(database_url)
    remaining = set(inspect(engine).get_table_names())
    assert not (EXPECTED_TABLES - {"alembic_version"}).intersection(remaining)

    command.upgrade(cfg, "head")
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    # Read the actual head from the script directory rather than hardcoding
    # a revision id — this test previously pinned an old head literal and
    # started failing silently-wrong (asserting a stale midpoint) every time
    # a new migration was added on top.
    expected_head = ScriptDirectory.from_config(cfg).get_current_head()
    assert row == expected_head


@pytest.mark.slow
def test_reports_unique_evaluation_id_version_constraint_exists(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """audit P1-6 — the DB constraint is the final invariant regardless of
    application-level locking (ReportService.lock_for_report_generation)."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_engine()
    command.upgrade(_alembic_config(database_url), "head")

    engine = get_engine(database_url)
    unique_constraints = inspect(engine).get_unique_constraints("reports")
    names = {uc["name"] for uc in unique_constraints}
    assert "uq_reports_evaluation_id_version" in names
    matching = next(
        uc for uc in unique_constraints if uc["name"] == "uq_reports_evaluation_id_version"
    )
    assert set(matching["column_names"]) == {"evaluation_id", "version"}
