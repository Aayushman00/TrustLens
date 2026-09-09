"""SQLAlchemy 2.0 ORM models — TrustLens Phase 3 schema.

FK ondelete policy
------------------
- Child rows of an evaluation (probe_results, osd_agent_outputs, human_reviews,
  final_scores, reports, attack_flags): CASCADE — deleting an evaluation removes
  its derived artifacts.
- evaluations.model_id → RESTRICT — models with evaluations cannot be deleted.

TrustLens is a single-user local application — there is no identity/user
concept anywhere in this schema. Human review is proven by a ``HumanReview``
row (with its timestamp) existing, not by whose id is on it.

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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedUpdatedMixin, TimestampMixin
from app.db.enums import EvaluationMode, EvaluationStatus, FriesDimension


def _pg_enum(enum_cls: type, name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda obj: [e.value for e in obj],
    )


evaluation_status_enum = _pg_enum(EvaluationStatus, "evaluation_status")
evaluation_mode_enum = _pg_enum(EvaluationMode, "evaluation_mode")
fries_dimension_enum = _pg_enum(FriesDimension, "fries_dimension")


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


class UserDataset(Base, TimestampMixin):
    """Local CSV dataset for the ad-hoc ``user_dataset`` Fairness path.

    Standalone resource — no FK from ``Evaluation``/``ProbeResult`` to this
    table. An evaluation contract freezes ``storage_uri``/``content_hash`` as
    immutable strings at create time, so deleting this row later never breaks
    a past evaluation's evidence trail (the Evidence Dossier reads only the
    frozen ``probe_results.metric_values`` snapshot, never a live dataset lookup).
    """

    __tablename__ = "user_datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    columns: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ready",
        server_default="ready",
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class DatasetContent(Base):
    """Immutable content-addressed dataset snapshot. Never updated after insert."""

    __tablename__ = "dataset_content"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    schema_sniff_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DatasetFetchEvent(Base):
    """Append-only provenance record — one row per fetch attempt, written once terminal."""

    __tablename__ = "dataset_fetch_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_content.id", ondelete="RESTRICT"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    content: Mapped[DatasetContent | None] = relationship()


class EvaluationDraft(Base):
    __tablename__ = "evaluation_draft"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[int] = mapped_column(Integer, ForeignKey("models.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="incomplete")
    resolved_model_sha: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_label_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    dimensions: Mapped[list[DraftDimensionConfig]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )


class DraftDimensionConfig(Base):
    __tablename__ = "draft_dimension_config"
    __table_args__ = (UniqueConstraint("draft_id", "dimension", name="uq_draft_dimension"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_draft.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_content.id", ondelete="RESTRICT"), nullable=True
    )
    text_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sensitive_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    label_mapping: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    min_group_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    draft: Mapped[EvaluationDraft] = relationship(back_populates="dimensions")


class DocumentationSource(Base, TimestampMixin):
    """First-class documentation evidence for a model (Explainability/Safety Track 1).

    Two kinds of rows:
    - ``source_kind="huggingface_hub"`` — auto-recorded at import time, pinned to
      the model's frozen ``revision`` (never the moving default branch). One
      such row is (re)written each time the model is (re)imported.
    - ``source_kind="user_supplied"`` — a URL the operator attaches manually
      (paper, safety card, eval report, etc.).
    """

    __tablename__ = "documentation_sources"
    __table_args__ = (Index("ix_documentation_sources_model_id", "model_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    documentation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    documentation_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    documentation_content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retrieval_status: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieval_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_model_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    source_model_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)

    model: Mapped[Model] = relationship()


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
    # Local execution/device evidence (Phase: GPU hardening) — captured once
    # per pipeline run from whichever probe actually invoked LocalHFBackend
    # (Fairness/Robustness). Null when no probe performed model inference
    # (e.g. documentation-only contract) — never fabricated/defaulted.
    execution_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

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

    model: Mapped[Model] = relationship(back_populates="evaluations")
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
    events: Mapped[list[EvaluationEvent]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )


class EvaluationEvent(Base, TimestampMixin):
    """Append-only lifecycle audit trail (Phase 4).

    Strictly audit evidence: records that an already-committed, already-
    authoritative state change happened, in the same transaction as that
    change. Never a second source of truth — evaluation status lives only
    in ``evaluations.status`` (via the atomic CAS in
    ``EvaluationRepository.transition_status``), probe results only in
    ``probe_results``, O/S/D and FRIES only in ``osd_agent_outputs``/
    ``final_scores``. No code should ever read this table to decide any of
    those facts — only to display when they happened.

    Ordering is by ``id`` (autoincrement), not ``created_at``: a full
    pipeline run and an HTTP-request-scoped write both execute inside one
    DB transaction, and PostgreSQL's ``now()`` (what ``server_default=
    func.now()`` compiles to) is frozen for the whole transaction — several
    events from one run can share an identical timestamp. This matches the
    existing convention (``ProbeResult``, ``HumanReview``, etc. are all
    ordered by ``.id``, never ``created_at``, for the same reason.
    """

    __tablename__ = "evaluation_events"
    __table_args__ = (Index("ix_evaluation_events_evaluation_id", "evaluation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Small, closed-shape payload only — never raw evidence, exception text,
    # stack traces, O/S/D values, or documentation/model/dataset internals.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    evaluation: Mapped[Evaluation] = relationship(back_populates="events")


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
    __table_args__ = (Index("ix_human_reviews_evaluation_id", "evaluation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
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
    __table_args__ = (
        Index("ix_reports_evaluation_id", "evaluation_id"),
        # Final invariant against duplicate versions even if application-level
        # locking (ReportService) is ever bypassed or changed (audit P1-6).
        UniqueConstraint("evaluation_id", "version", name="uq_reports_evaluation_id_version"),
    )

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
