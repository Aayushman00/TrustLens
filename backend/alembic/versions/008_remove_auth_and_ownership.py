"""Remove multi-user auth/RBAC/ownership schema — TrustLens is a single-user
local application; the local machine itself is the trust boundary.

Drops every identity-authorization artifact whose semantics are obsolete in
a single-operator instance: evaluations.created_by/published_by (creator/
publisher tracking), human_reviews.reviewer_id (reviewer identity — the
human_reviews row itself, with its timestamp and overrides, already proves a
human review happened), user_datasets.owner_id (dataset ownership gate),
documentation_sources.created_by (uploader ownership gate), and finally the
users table and user_role enum themselves. Evaluations/datasets/reports/
reports rows and all their other columns are untouched — only the identity
FK columns are dropped.

Revision ID: 008_remove_auth_and_ownership
Revises: 007_add_reports_unique_version
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_remove_auth_and_ownership"
down_revision: str | None = "007_add_reports_unique_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "researcher",
    "reviewer",
    "admin",
    name="user_role",
    create_type=False,
)


def upgrade() -> None:
    # evaluations.created_by / published_by
    op.drop_constraint("fk_evaluations_created_by_users", "evaluations", type_="foreignkey")
    op.drop_column("evaluations", "created_by")
    op.drop_constraint("evaluations_published_by_fkey", "evaluations", type_="foreignkey")
    op.drop_column("evaluations", "published_by")

    # human_reviews.reviewer_id
    op.drop_index("ix_human_reviews_reviewer_id", table_name="human_reviews")
    op.drop_constraint("human_reviews_reviewer_id_fkey", "human_reviews", type_="foreignkey")
    op.drop_column("human_reviews", "reviewer_id")

    # user_datasets.owner_id
    op.drop_index("ix_user_datasets_owner_id", table_name="user_datasets")
    op.drop_constraint("user_datasets_owner_id_fkey", "user_datasets", type_="foreignkey")
    op.drop_column("user_datasets", "owner_id")

    # documentation_sources.created_by
    op.drop_constraint(
        "documentation_sources_created_by_fkey", "documentation_sources", type_="foreignkey"
    )
    op.drop_column("documentation_sources", "created_by")

    # users table + its enum
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    user_role.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    user_role.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.add_column(
        "documentation_sources",
        sa.Column("created_by", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "documentation_sources_created_by_fkey",
        "documentation_sources",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "user_datasets",
        sa.Column("owner_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "user_datasets_owner_id_fkey",
        "user_datasets",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_user_datasets_owner_id", "user_datasets", ["owner_id"])

    op.add_column(
        "human_reviews",
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "human_reviews_reviewer_id_fkey",
        "human_reviews",
        "users",
        ["reviewer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_human_reviews_reviewer_id", "human_reviews", ["reviewer_id"])

    op.add_column(
        "evaluations",
        sa.Column("published_by", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "evaluations_published_by_fkey",
        "evaluations",
        "users",
        ["published_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "evaluations",
        sa.Column("created_by", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_evaluations_created_by_users",
        "evaluations",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
