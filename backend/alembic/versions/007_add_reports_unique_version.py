"""Add unique constraint on reports(evaluation_id, version) (audit P1-6 —
report version TOCTOU race).

Revision ID: 007_add_reports_unique_version
Revises: 006_add_evaluation_events
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "007_add_reports_unique_version"
down_revision: str | None = "006_add_evaluation_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "uq_reports_evaluation_id_version"


def upgrade() -> None:
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        "reports",
        ["evaluation_id", "version"],
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "reports", type_="unique")
