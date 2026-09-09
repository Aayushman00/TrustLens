"""Add documentation_sources table (Part 1 — documentation as first-class evidence).

Revision ID: 005_add_documentation_sources
Revises: 004_add_execution_metadata
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_add_documentation_sources"
down_revision: str | None = "004_add_execution_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documentation_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "model_id",
            sa.Integer(),
            sa.ForeignKey("models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("documentation_type", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("documentation_revision", sa.String(length=128), nullable=True),
        sa.Column("documentation_content_hash", sa.String(length=128), nullable=True),
        sa.Column("retrieval_status", sa.String(length=32), nullable=False),
        sa.Column("retrieval_error", sa.Text(), nullable=True),
        sa.Column("content_length", sa.Integer(), nullable=True),
        sa.Column("source_model_ref", sa.String(length=256), nullable=False),
        sa.Column("source_model_revision", sa.String(length=128), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_documentation_sources_model_id",
        "documentation_sources",
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_documentation_sources_model_id", table_name="documentation_sources")
    op.drop_table("documentation_sources")
