"""Drop user_datasets (dead upload-based UserDataset subsystem).

Revision ID: 012_drop_user_datasets
Revises: 011_add_methodology_version
Create Date: 2026-09-11

The upload-based UserDataset path (POST /v1/datasets, DatasetStore,
dataset_service.py) has zero frontend callers and zero live evaluation path
consuming it — the only endpoint that could have (POST /v1/evaluations) is
deprecated and self-documented as dataset-less. No FK from Evaluation/
ProbeResult to this table (see the removed model's own docstring); its
former owner_id FK was already dropped in 008_remove_auth_and_ownership.
Confirmed dead by direct code trace, not assumption, before writing this.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_drop_user_datasets"
down_revision: str | None = "011_add_methodology_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("user_datasets")


def downgrade() -> None:
    op.create_table(
        "user_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("columns", postgresql.JSONB(), nullable=False, server_default="[]"),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
