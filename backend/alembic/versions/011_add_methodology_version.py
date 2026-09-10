"""Add methodology_version to evaluations (backfilled to legacy tag).

Revision ID: 011_add_methodology_version
Revises: 010_add_eval_draft
Create Date: 2026-09-10

Adds a non-nullable ``methodology_version`` column to ``evaluations``. The
server_default is the legacy tag (``pre-v1-fixed-5dim``), applied at the DB
level so every pre-existing row is explicitly backfilled to LEGACY — never
left NULL, and never silently reinterpreted as the new methodology. New rows
must pass ``methodology_version`` explicitly from application code (Task
4.4, stamping ``CURRENT_METHODOLOGY_VERSION``); the server_default here
exists to backfill existing rows, not to relieve new code of that duty.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011_add_methodology_version"
down_revision: str | None = "010_add_eval_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_METHODOLOGY_VERSION = "pre-v1-fixed-5dim"


def upgrade() -> None:
    op.add_column(
        "evaluations",
        sa.Column(
            "methodology_version",
            sa.String(length=64),
            nullable=False,
            server_default=LEGACY_METHODOLOGY_VERSION,
        ),
    )


def downgrade() -> None:
    op.drop_column("evaluations", "methodology_version")
