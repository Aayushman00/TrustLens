"""SQLAlchemy 2.0 ORM models — TrustLens Phase 3 schema.

FK ondelete policy
------------------
- Child rows of an evaluation (probe_results, osd_agent_outputs, human_reviews,
  final_scores, reports, attack_flags): CASCADE — deleting an evaluation removes
  its derived artifacts.
- evaluations.model_id → RESTRICT — models with evaluations cannot be deleted.
- human_reviews.reviewer_id → RESTRICT — users referenced as reviewers stay.
- evaluations.published_by → SET NULL — user deletion clears publish actor only.

evidence_refs (JSONB) is a list of immutable refs per ADR 0004, e.g.::

    [{"evidence_id": "...", "uri": "s3://...", "hash": "sha256:...",
      "content_type": "application/json", "probe_name": "robustness"}]

Leaderboard visibility uses evaluations.is_published + published_at (ADR 0013);
there is no separate leaderboard_publications table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedUpdatedMixin, TimestampMixin
from app.db.enums import EvaluationMode, EvaluationStatus, FriesDimension, UserRole


def _pg_enum(enum_cls: type, name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda obj: [e.value for e in obj],
    )


user_role_enum = _pg_enum(UserRole, "user_role")
evaluation_status_enum = _pg_enum(EvaluationStatus, "evaluation_status")
evaluation_mode_enum = _pg_enum(EvaluationMode, "evaluation_mode")
fries_dimension_enum = _pg_enum(FriesDimension, "fries_dimension")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        user_role_enum,
        nullable=False,
        default=UserRole.RESEARCHER,
    )

    reviews: Mapped[list[HumanReview]] = relationship(back_populates="reviewer")
    published_evaluations: Mapped[list[Evaluation]] = relationship(
        back_populates="publisher",
        foreign_keys="Evaluation.published_by",
    )


class Model(Base, TimestampMixin):
    """Imported HF Hub model registry row (`models` table)."""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hf_repo_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    # Column name `metadata` is reserved on DeclarativeBase — map explicitly.
    model_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    revision: Mapped[str | None] = mapped_column(String(128), nullable=True)

    evaluations: Mapped[list[Evaluation]] = relationship(back_populates="model")


class Evaluation(Base, CreatedUpdatedMixin):
    __tablename__ = "evaluations"
    __table_args__ = (
        Index("ix_evaluations_status", "status"),
        Index("ix_evaluations_is_published", "is_published"),
        Index("ix_evaluations_model_id", "model_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    model_id: Mapped[int] = mapped_column(
        ForeignKey("models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[EvaluationStatus] = mapped_column(
        evaluation_status_enum,
        nullable=False,
        default=EvaluationStatus.PENDING,
    )
    evaluation_mode: Mapped[EvaluationMode] = mapped_column(
        evaluation_mode_enum,
        nullable=False,
    )
    probe_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    # Comparability context (ADR 0013)
    task: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset: Mapped[str | None] = mapped_column(String(256), nullable=True)
    config: Mapped[str | None] = mapped_column(String(256), nullable=True)
    model_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trustlens_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    published_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Phase 5 (ADR 0006) — owner for publish/unpublish RBAC (owner-or-admin policy).
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    model: Mapped[Model] = relationship(back_populates="evaluations")
    publisher: Mapped[Optional[User]] = relationship(
        back_populates="published_evaluations",
        foreign_keys=[published_by],
    )
    creator: Mapped[Optional[User]] = relationship(foreign_keys=[created_by])
    probe_results: Mapped[list[ProbeResult]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )
    osd_agent_outputs: Mapped[list[OsdAgentOutput]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )
    human_reviews: Mapped[list[HumanReview]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )
    final_score: Mapped[Optional[FinalScore]] = relationship(
        back_populates="evaluation",
        uselist=False,
        cascade="all, delete-orphan",
    )
    reports: Mapped[list[Report]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )
    attack_flags: Mapped[list[AttackFlag]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )


class ProbeResult(Base, TimestampMixin):
    __tablename__ = "probe_results"
    __table_args__ = (Index("ix_probe_results_evaluation_id", "evaluation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    dimension: Mapped[FriesDimension] = mapped_column(
        fries_dimension_enum,
        nullable=False,
    )
    metric_values: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # ADR 0004: list of {evidence_id, uri, hash, content_type, probe_name}
    evidence_refs: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )

    evaluation: Mapped[Evaluation] = relationship(back_populates="probe_results")


class OsdAgentOutput(Base, TimestampMixin):
    __tablename__ = "osd_agent_outputs"
    __table_args__ = (Index("ix_osd_agent_outputs_evaluation_id", "evaluation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_suggestion: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_used: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    evaluation: Mapped[Evaluation] = relationship(back_populates="osd_agent_outputs")


class HumanReview(Base, TimestampMixin):
    __tablename__ = "human_reviews"
    __table_args__ = (
        Index("ix_human_reviews_evaluation_id", "evaluation_id"),
        Index("ix_human_reviews_reviewer_id", "reviewer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    human_changed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    evaluation: Mapped[Evaluation] = relationship(back_populates="human_reviews")
    reviewer: Mapped[User] = relationship(back_populates="reviews")


class FinalScore(Base, TimestampMixin):
    __tablename__ = "final_scores"
    __table_args__ = (Index("ix_final_scores_fries_score", "fries_score"),)

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fries_score: Mapped[float] = mapped_column(Float, nullable=False)
    dimension_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    finalized_osd: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluation_mode: Mapped[EvaluationMode] = mapped_column(
        evaluation_mode_enum,
        nullable=False,
    )

    evaluation: Mapped[Evaluation] = relationship(back_populates="final_score")


class Report(Base, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_evaluation_id", "evaluation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    json_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pdf_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    evaluation: Mapped[Evaluation] = relationship(back_populates="reports")


class AttackFlag(Base, TimestampMixin):
    """Post-MVP stub for attack simulation / detection flags."""

    __tablename__ = "attack_flags"
    __table_args__ = (Index("ix_attack_flags_evaluation_id", "evaluation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario: Mapped[str] = mapped_column(String(256), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )

    evaluation: Mapped[Evaluation] = relationship(back_populates="attack_flags")
