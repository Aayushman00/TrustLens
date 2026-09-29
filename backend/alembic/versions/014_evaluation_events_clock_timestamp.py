"""evaluation_events.created_at: now() -> clock_timestamp() (per-row timestamp).

Postgres's now() is frozen for the whole transaction, so multiple
evaluation_events rows written inside one pipeline run's transaction all
got an identical created_at, which showed up as "same time for every row"
on the evaluation timeline. clock_timestamp() reads the real wall clock
per statement instead.

Revision ID: 014_evaluation_events_clock_timestamp
Revises: 013_add_positive_label_index
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014_evt_clock_timestamp"
down_revision: str | None = "013_add_positive_label_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "evaluation_events",
        "created_at",
        server_default=sa.text("clock_timestamp()"),
    )


def downgrade() -> None:
    op.alter_column(
        "evaluation_events",
        "created_at",
        server_default=sa.func.now(),
    )
