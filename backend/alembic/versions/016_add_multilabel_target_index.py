"""Add multilabel_target_index to draft_dimension_config.

Revision ID: 016_add_multilabel_target_index
Revises: 015_add_severe_column
Create Date: 2026-10-02

A multi-label (independent sigmoid) head such as unitary/toxic-bert cannot be
decoded by argmax. The draft now names which output is the positive class;
that output is thresholded on its own sigmoid and label_mapping is validated
against the derived binary {0: not <label>, 1: <label>}. Nullable: single-label
models never set it, and no existing row changes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_add_multilabel_target_index"
down_revision: str | None = "015_add_severe_column"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("draft_dimension_config", sa.Column("multilabel_target_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("draft_dimension_config", "multilabel_target_index")
