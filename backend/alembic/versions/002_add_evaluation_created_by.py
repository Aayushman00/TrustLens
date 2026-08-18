"""Add evaluations.created_by (owner FK, Phase 5 — ADR 0006 publish RBAC).

Revision ID: 002_add_evaluation_created_by
Revises: 001_initial_schema
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_add_evaluation_created_by"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evaluations", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_evaluations_created_by_users",
        "evaluations",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_evaluations_created_by_users", "evaluations", type_="foreignkey")
    op.drop_column("evaluations", "created_by")
