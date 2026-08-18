"""Evaluation request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import EvaluationMode, EvaluationStatus
from app.schemas.common import CursorPage
from app.schemas.confidence import ConfidenceSummary
from app.schemas.modes import ModeDisclosure
from app.schemas.reviews import HumanReviewRead


class EvaluationCreate(BaseModel):
    model_id: int
    evaluation_mode: EvaluationMode
    probe_config: dict[str, Any] = Field(default_factory=dict)
    task: str | None = None
    dataset: str | None = None
    config: str | None = None
    model_revision: str | None = None
    trustlens_version: str | None = None


class EvaluationStatusUpdate(BaseModel):
    """Internal / service use — no public route in Phase 4."""

    status: EvaluationStatus


class ProbeProgress(BaseModel):
    """FRIES probe completion counter (total=5 dimensions; Phase 9 stubs → 5/5)."""

    completed: int
    total: int = 5


class OsdAgentRead(BaseModel):
    """Latest PROPOSED O/S/D suggestion (Phase 16) — not ground truth."""

    ai_suggestion: dict[str, Any]
    ai_confidence: float | None = None
    methodology_status: str = "PROPOSED_REQUIRES_VALIDATION"
    rationale: str | None = None


class FinalScoreRead(BaseModel):
    """Original FRIES result from finalized O/S/D (Autonomous path in Phase 16)."""

    model_config = ConfigDict(from_attributes=True)

    fries_score: float
    dimension_scores: dict[str, Any]
    overall_confidence: float | None = None
    evaluation_mode: EvaluationMode
    # Phase 17: denormalized disclosure for clients (from finalized_osd + mode).
    human_reviewed: bool = False
    disclaimer: str | None = None


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: int
    status: EvaluationStatus
    evaluation_mode: EvaluationMode
    probe_config: dict[str, Any]
    task: str | None = None
    dataset: str | None = None
    config: str | None = None
    model_revision: str | None = None
    trustlens_version: str | None = None
    is_published: bool
    published_at: datetime | None = None
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    probe_progress: ProbeProgress | None = None
    # Phase 15: populated on detail reads only (list omits); evidence strength, not correctness.
    confidence_summary: ConfidenceSummary | None = None
    # Phase 16: detail reads only (list omits). osd_agent is PROPOSED, not truth;
    # final_score exists only once O/S/D is finalized (Autonomous this phase).
    osd_agent: OsdAgentRead | None = None
    final_score: FinalScoreRead | None = None
    # Phase 17: mandatory mode/provenance disclosure on detail + finalize reads.
    mode_disclosure: ModeDisclosure | None = None
    # Phase 18: latest human review (Assisted accept/edit); detail reads only.
    human_review: HumanReviewRead | None = None


class EvaluationList(CursorPage):
    items: list[EvaluationRead]
