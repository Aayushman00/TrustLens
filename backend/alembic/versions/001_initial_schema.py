"""Initial TrustLens schema (Phase 3).

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "researcher",
    "reviewer",
    "admin",
    name="user_role",
    create_type=False,
)
evaluation_status = postgresql.ENUM(
    "PENDING",
    "RUNNING",
    "PROBES_COMPLETED",
    "AGENT_COMPLETED",
    "AWAITING_REVIEW",
    "FINALIZED",
    "FAILED",
    name="evaluation_status",
    create_type=False,
)
evaluation_mode = postgresql.ENUM(
    "AI_ASSISTED",
    "AI_AUTONOMOUS",
    name="evaluation_mode",
    create_type=False,
)
fries_dimension = postgresql.ENUM(
    "FAIRNESS",
    "ROBUSTNESS",
    "INTEGRITY",
    "EXPLAINABILITY",
    "SAFETY",
    name="fries_dimension",
    create_type=False,
)


def upgrade() -> None:
    user_role.create(op.get_bind(), checkfirst=True)
    evaluation_status.create(op.get_bind(), checkfirst=True)
    evaluation_mode.create(op.get_bind(), checkfirst=True)
    fries_dimension.create(op.get_bind(), checkfirst=True)

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

    op.create_table(
        "models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hf_repo_id", sa.String(length=256), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("revision", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hf_repo_id"),
    )

    op.create_table(
        "evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("status", evaluation_status, nullable=False),
        sa.Column("evaluation_mode", evaluation_mode, nullable=False),
        sa.Column(
            "probe_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("task", sa.String(length=128), nullable=True),
        sa.Column("dataset", sa.String(length=256), nullable=True),
        sa.Column("config", sa.String(length=256), nullable=True),
        sa.Column("model_revision", sa.String(length=128), nullable=True),
        sa.Column("trustlens_version", sa.String(length=64), nullable=True),
        sa.Column(
            "is_published",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluations_status", "evaluations", ["status"], unique=False)
    op.create_index(
        "ix_evaluations_is_published", "evaluations", ["is_published"], unique=False
    )
    op.create_index("ix_evaluations_model_id", "evaluations", ["model_id"], unique=False)

    op.create_table(
        "probe_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension", fries_dimension, nullable=False),
        sa.Column(
            "metric_values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_probe_results_evaluation_id",
        "probe_results",
        ["evaluation_id"],
        unique=False,
    )

    op.create_table(
        "osd_agent_outputs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "ai_suggestion",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column(
            "evidence_used",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_osd_agent_outputs_evaluation_id",
        "osd_agent_outputs",
        ["evaluation_id"],
        unique=False,
    )

    op.create_table(
        "human_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=False),
        sa.Column(
            "overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "human_changed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_human_reviews_evaluation_id",
        "human_reviews",
        ["evaluation_id"],
        unique=False,
    )
    op.create_index(
        "ix_human_reviews_reviewer_id",
        "human_reviews",
        ["reviewer_id"],
        unique=False,
    )

    op.create_table(
        "final_scores",
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fries_score", sa.Float(), nullable=False),
        sa.Column(
            "dimension_scores",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "finalized_osd",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("overall_confidence", sa.Float(), nullable=True),
        sa.Column("evaluation_mode", evaluation_mode, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("evaluation_id"),
    )
    op.create_index(
        "ix_final_scores_fries_score",
        "final_scores",
        ["fries_score"],
        unique=False,
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("json_uri", sa.String(length=1024), nullable=True),
        sa.Column("pdf_uri", sa.String(length=1024), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_evaluation_id", "reports", ["evaluation_id"], unique=False)

    op.create_table(
        "attack_flags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario", sa.String(length=256), nullable=False),
        sa.Column("severity", sa.String(length=64), nullable=True),
        sa.Column(
            "detected",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attack_flags_evaluation_id",
        "attack_flags",
        ["evaluation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attack_flags_evaluation_id", table_name="attack_flags")
    op.drop_table("attack_flags")

    op.drop_index("ix_reports_evaluation_id", table_name="reports")
    op.drop_table("reports")

    op.drop_index("ix_final_scores_fries_score", table_name="final_scores")
    op.drop_table("final_scores")

    op.drop_index("ix_human_reviews_reviewer_id", table_name="human_reviews")
    op.drop_index("ix_human_reviews_evaluation_id", table_name="human_reviews")
    op.drop_table("human_reviews")

    op.drop_index("ix_osd_agent_outputs_evaluation_id", table_name="osd_agent_outputs")
    op.drop_table("osd_agent_outputs")

    op.drop_index("ix_probe_results_evaluation_id", table_name="probe_results")
    op.drop_table("probe_results")

    op.drop_index("ix_evaluations_model_id", table_name="evaluations")
    op.drop_index("ix_evaluations_is_published", table_name="evaluations")
    op.drop_index("ix_evaluations_status", table_name="evaluations")
    op.drop_table("evaluations")

    op.drop_table("models")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    fries_dimension.drop(op.get_bind(), checkfirst=True)
    evaluation_mode.drop(op.get_bind(), checkfirst=True)
    evaluation_status.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
