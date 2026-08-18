"""Report v1 schemas (Phase 19, ADR 0009) — canonical JSON + API response.

The JSON document is the canonical report; the PDF is a projection rendered
from the same JSON. Every report is mode-labeled and reuses the locked
Phase 17/18 disclaimer wording — AI-proposed O/S/D is never ground truth.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.enums import EvaluationMode, EvaluationStatus, FriesDimension
from app.schemas.confidence import ConfidenceSummary
from app.schemas.modes import ModeDisclosure

REPORT_SCHEMA_VERSION = "report_v1"
SCORE_TYPE_ORIGINAL_FRIES = "original_FRIES"
SCORE_NOTE = (
    "Original FRIES computed from finalized O/S/D — not FRIES2; AI-proposed "
    "O/S/D is not ground truth."
)


class ReportEvaluation(BaseModel):
    id: uuid.UUID
    status: EvaluationStatus
    evaluation_mode: EvaluationMode
    model_ref: str
    model_id: int
    created_at: datetime
    # Comparability context frozen at evaluation time (task/dataset/config/
    # model_revision/trustlens_version).
    finalized_context: dict[str, Any] = Field(default_factory=dict)


class ReportScore(BaseModel):
    score_type: Literal["original_FRIES"] = SCORE_TYPE_ORIGINAL_FRIES
    fries_score: float
    dimension_scores: dict[str, Any]
    finalized_osd: dict[str, Any]
    overall_confidence: float | None = None
    note: str = SCORE_NOTE


class ReportProbe(BaseModel):
    dimension: FriesDimension
    metric_values: dict[str, Any]
    confidence: float | None = None
    flags: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ExecutiveSummary(BaseModel):
    headline: str
    bullets: list[str]


class ReportV1(BaseModel):
    """Canonical report document stored at ``reports/{evaluation_id}/v{n}/report.json``."""

    schema_version: Literal["report_v1"] = REPORT_SCHEMA_VERSION
    report_version: int = Field(ge=1)
    generated_at: datetime
    evaluation: ReportEvaluation
    mode_disclosure: ModeDisclosure
    score: ReportScore
    confidence_summary: ConfidenceSummary | None = None
    probes: list[ReportProbe]
    osd_agent: dict[str, Any] | None = None
    human_review: dict[str, Any] | None = None
    attack_flags: list[dict[str, Any]] = Field(default_factory=list)
    executive_summary: ExecutiveSummary


class ReportRead(BaseModel):
    """API response for GET /v1/reports/{id} and POST .../generate."""

    evaluation_id: uuid.UUID
    version: int
    json_uri: str
    json_hash: str
    pdf_uri: str | None = None
    pdf_hash: str | None = None
    fries_score: float
    mode_disclosure: ModeDisclosure
    generated_at: datetime
    report_json: dict[str, Any]
