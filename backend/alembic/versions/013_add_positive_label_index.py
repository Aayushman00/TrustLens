"""Add positive_label_index to draft_dimension_config (Fairness DP/EO/F1
positive-class fix).

Revision ID: 013_add_positive_label_index
Revises: 012_drop_user_datasets
Create Date: 2026-09-11

fairness_metrics.py's DP/EO/F1-spread hardcoded model_label_index == 1 as
the "positive"/favorable outcome, but label_mapping lets a user legitimately
assign the favorable outcome to any model index -- a valid mapping could
silently flip the metric's sign. Nullable + server_default=1 so every
pre-existing row is explicitly backfilled to the value the hardcoded
behavior always assumed, never left NULL and never reinterpreted.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013_add_positive_label_index"
down_revision: str | None = "012_drop_user_datasets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "draft_dimension_config",
        sa.Column("positive_label_index", sa.Integer(), nullable=True, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("draft_dimension_config", "positive_label_index")
