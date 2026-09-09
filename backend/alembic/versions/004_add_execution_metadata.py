"""Add evaluations.execution_metadata (real device/GPU evidence, nullable).

Revision ID: 004_add_execution_metadata
Revises: 003_add_user_datasets
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_add_execution_metadata"
down_revision: str | None = "003_add_user_datasets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluations",
        sa.Column("execution_metadata", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluations", "execution_metadata")
