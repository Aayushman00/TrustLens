"""Report v1 schemas (Phase 19, ADR 0009) — canonical JSON + API response.

The JSON document is the canonical report; the PDF is a projection rendered
from the same JSON. Provenance language must match the assessment engine
(deterministic abstention vs legacy heuristic) — not an implied LLM.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.enums import EvaluationMode, EvaluationStatus, FriesDimension
from app.schemas.confidence import ConfidenceSummary
from app.schemas.documentation import DocumentationSourceRead
from app.schemas.modes import ModeDisclosure, SCORE_NOTE_LEGACY

REPORT_SCHEMA_VERSION = "report_v1"
SCORE_TYPE_ORIGINAL_FRIES = "original_FRIES"
# Default note is the legacy-heuristic wording; builder overrides from engine.
SCORE_NOTE = SCORE_NOTE_LEGACY


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
    # None exactly when scoring_withheld is True — a report is now generated
    # either way (see build_report_json); this is never a fabricated 0 or
    # any other placeholder standing in for "no score".
    fries_score: float | None = None
    dimension_scores: dict[str, Any] = Field(default_factory=dict)
    finalized_osd: dict[str, Any] = Field(default_factory=dict)
    overall_confidence: float | None = None
    scoring_withheld: bool = False
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


class ReportTraceabilityEntry(BaseModel):
    """One evidence-to-FRIES chain link per FRIES dimension (Phase 5).

    conclusion → risk/status → gate/rule → metric → evidence → human O/S/D
    → FRIES — every field here is a direct copy of an already-computed,
    already-persisted value (the same ``ProbeEvidenceRead`` fields the live
    evaluation detail page renders, plus the same ``final_scores``/
    ``osd_agent``/``human_review`` values the score section already
    carries). Nothing is recomputed here.

    Deliberately excludes raw metric numbers (accuracy_drop, demographic
    parity difference, coverage_ratio's underlying counts, etc.) — those
    live once, in ``ReportV1.probes[i].metric_values`` for the same
    ``dimension``. This entry is the chain/index, not a second copy of the
    measurements.
    """

    dimension: FriesDimension
    status: str | None = None
    status_reason: str | None = None
    aspect_scoring: str | None = None
    scored_risk_id: str | None = None
    risks_triggered: list[str] | None = None
    gates: list[str] | None = None
    # Explainability/Safety only. Always "documentation coverage" — never
    # rendered or labeled as an "Explainability score"/safety verdict
    # anywhere this value is displayed.
    coverage_ratio: float | None = None
    confidence: float | None = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] | None = None
    # Human-entered O/S/D for this aspect — present only once settled
    # (i.e. when FRIES is not withheld); None otherwise, never a default.
    human_osd: dict[str, Any] | None = None
    # None exactly when FRIES is withheld for this evaluation.
    fries_dimension_score: float | None = None


class ReportV1(BaseModel):
    """Canonical report document stored at ``reports/{evaluation_id}/v{n}/report.json``."""

    schema_version: Literal["report_v1"] = REPORT_SCHEMA_VERSION
    report_version: int = Field(ge=1)
    generated_at: datetime
    # Copied verbatim from Evaluation.methodology_version — required for
    # every newly generated report (Task 4.2). Never retroactively
    # reinterpreted; a legacy Evaluation still carries LEGACY_METHODOLOGY_VERSION.
    methodology_version: str
    evaluation: ReportEvaluation
    mode_disclosure: ModeDisclosure
    score: ReportScore
    confidence_summary: ConfidenceSummary | None = None
    probes: list[ReportProbe]
    osd_agent: dict[str, Any] | None = None
    human_review: dict[str, Any] | None = None
    attack_flags: list[dict[str, Any]] = Field(default_factory=list)
    executive_summary: ExecutiveSummary
    # Phase 5 additions — all additive, read-only restructurings of
    # already-persisted evidence; none introduce new computation.
    evidence_traceability: list[ReportTraceabilityEntry] = Field(default_factory=list)
    # Real device/GPU evidence from Evaluation.execution_metadata (Phase 1).
    # None when no probe performed local inference for this evaluation.
    execution_environment: dict[str, Any] | None = None
    # Documentation evidence sources for the evaluated model (Phase 2) —
    # the pinned-revision HF card plus any user-supplied pointers.
    documentation_sources: list[DocumentationSourceRead] = Field(default_factory=list)
    reproducibility: dict[str, Any] = Field(default_factory=dict)
    # Aggregated, de-duplicated limitations already recorded by each probe.
    limitations: list[str] = Field(default_factory=list)


class ReportRead(BaseModel):
    """API response for GET /v1/reports/{id} and POST .../generate."""

    evaluation_id: uuid.UUID
    version: int
    json_uri: str
    json_hash: str
    pdf_uri: str | None = None
    pdf_hash: str | None = None
    # None exactly when this evaluation's FRIES is withheld — the report is
    # still generated and complete either way.
    fries_score: float | None = None
    # None = legacy report generated before this field existed; stored
    # report.json blobs are never rewritten to backfill it.
    methodology_version: str | None = None
    mode_disclosure: ModeDisclosure
    generated_at: datetime
    report_json: dict[str, Any]
