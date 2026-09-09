"""Add user_datasets table (user-defined local Fairness dataset path).

Revision ID: 003_add_user_datasets
Revises: 002_add_evaluation_created_by
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_add_user_datasets"
down_revision: str | None = "002_add_evaluation_created_by"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "columns",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="ready",
        ),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_datasets_owner_id",
        "user_datasets",
        ["owner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_datasets_owner_id", table_name="user_datasets")
    op.drop_table("user_datasets")
