"""Add evaluation_events table (Phase 4 — append-only lifecycle audit trail).

Revision ID: 006_add_evaluation_events
Revises: 005_add_documentation_sources
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_add_evaluation_events"
down_revision: str | None = "005_add_documentation_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "evaluation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_evaluation_events_evaluation_id",
        "evaluation_events",
        ["evaluation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_events_evaluation_id", table_name="evaluation_events")
    op.drop_table("evaluation_events")
