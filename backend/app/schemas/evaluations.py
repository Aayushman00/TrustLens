"""Evaluation request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import EvaluationMode, EvaluationStatus, FriesDimension
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

    # Phase 7 evaluation contract selection. pairing_id, dataset_key, and
    # contract_kind="proxy_lr" are mutually exclusive (enforced in
    # build_evaluation_contract); proxy_lr additionally requires admin.
    # Nothing selected resolves to kind="documentation_only" — never Adult.
    contract_kind: str | None = None
    pairing_id: str | None = None
    dataset_key: str | None = None


class EvaluationStatusUpdate(BaseModel):
    """Internal / service use — no public route in Phase 4."""

    status: EvaluationStatus


class ProbeProgress(BaseModel):
    """Probe completion counter (total=5 dimensions)."""

    completed: int
    total: int = 5


class ProbeEvidenceRead(BaseModel):
    """Layer A probe snapshot for evaluation detail — existing persisted fields only."""

    dimension: FriesDimension
    status: str | None = None
    status_reason: str | None = None
    methodology_version: str | None = None
    gates: list[str] | None = None
    risks_triggered: list[str] | None = None
    aspect_scoring: str | None = None
    scored_risk_id: str | None = None
    claim_boundary: dict[str, Any] | None = None
    limitations: list[str] | None = None
    flags: list[str] | None = None
    coverage_ratio: float | None = None
    n_evaluated: int | None = None
    fairness_mode: str | None = None
    pairing_id: str | None = None
    confidence: float | None = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class OsdAgentRead(BaseModel):
    """Latest O/S/D representation (deterministic abstention or legacy heuristic)."""

    ai_suggestion: dict[str, Any]
    ai_confidence: float | None = None
    methodology_status: str = "PROPOSED_REQUIRES_VALIDATION"
    rationale: str | None = None


class FinalScoreRead(BaseModel):
    """Original FRIES result from finalized O/S/D."""

    model_config = ConfigDict(from_attributes=True)

    fries_score: float
    dimension_scores: dict[str, Any]
    overall_confidence: float | None = None
    evaluation_mode: EvaluationMode
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
    probes: list[ProbeEvidenceRead] | None = None
    confidence_summary: ConfidenceSummary | None = None
    osd_agent: OsdAgentRead | None = None
    final_score: FinalScoreRead | None = None
    mode_disclosure: ModeDisclosure | None = None
    human_review: HumanReviewRead | None = None


class EvaluationList(CursorPage):
    items: list[EvaluationRead]
