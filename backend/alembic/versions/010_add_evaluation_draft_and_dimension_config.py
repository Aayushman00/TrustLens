"""Add evaluation_draft and draft_dimension_config tables.

Revision ID: 010_add_eval_draft
Revises: 009_add_dataset_content
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_add_eval_draft"
down_revision: str | None = "009_add_dataset_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_draft",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="incomplete"),
        sa.Column("resolved_model_sha", sa.String(length=128), nullable=True),
        sa.Column("model_label_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["models.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "draft_dimension_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension", sa.String(length=16), nullable=False),
        sa.Column("dataset_content_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("text_column", sa.String(length=256), nullable=True),
        sa.Column("target_column", sa.String(length=256), nullable=True),
        sa.Column("sensitive_column", sa.String(length=256), nullable=True),
        sa.Column("label_mapping", postgresql.JSONB(), nullable=True),
        sa.Column("min_group_n", sa.Integer(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["evaluation_draft.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_content_id"],
            ["dataset_content.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("draft_id", "dimension", name="uq_draft_dimension"),
    )


def downgrade() -> None:
    op.drop_table("draft_dimension_config")
    op.drop_table("evaluation_draft")
