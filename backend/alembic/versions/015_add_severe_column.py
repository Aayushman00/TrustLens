"""Add severe_column to draft_dimension_config (behavioural SAFETY dimension).

Revision ID: 015_add_severe_column
Revises: 014_evt_clock_timestamp
Create Date: 2026-10-02

The optional SAFETY draft dimension needs a 0/1 column marking severe-harm
rows; behavioural safety measures false negatives on exactly those rows.
Nullable: FAIRNESS/ROBUSTNESS rows never set it, and no existing row changes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_add_severe_column"
down_revision: str | None = "014_evt_clock_timestamp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("draft_dimension_config", sa.Column("severe_column", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("draft_dimension_config", "severe_column")
