"""O/S/D Agent contract (Phase 16).

The agent reads persisted probe evidence and proposes one O/S/D triple per
FRIES dimension. Output is **PROPOSED / REQUIRES VALIDATION** — the
metric→O/S/D mapping is unresolved research and must never be presented as
validated science. The agent does not run probes, load models, or compute
FRIES (that is the pure scorer's job, from *finalized* O/S/D only).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.db.enums import FriesDimension, ProbeEvaluationStatus

METHODOLOGY_STATUS: Literal["PROPOSED_REQUIRES_VALIDATION"] = (
    "PROPOSED_REQUIRES_VALIDATION"
)
METHODOLOGY_STATUS_DETERMINISTIC: Literal["DETERMINISTIC_OSD_V1"] = (
    "DETERMINISTIC_OSD_V1"
)
LEGACY_HEURISTIC_METHODOLOGY_STATUS: Literal["LEGACY_HEURISTIC_OSD_V1"] = (
    "LEGACY_HEURISTIC_OSD_V1"
)

MethodologyStatus = Literal[
    "PROPOSED_REQUIRES_VALIDATION",
    "DETERMINISTIC_OSD_V1",
    "LEGACY_HEURISTIC_OSD_V1",
]


@dataclass
class ProbeSnapshot:
    """Read-only view of one persisted ``probe_results`` row."""

    dimension: FriesDimension
    metric_values: dict[str, Any]
    confidence: float | None
    evidence_refs: list[dict[str, Any]]


@dataclass
class AgentContext:
    evaluation_id: uuid.UUID
    model_ref: str
    model_metadata: dict[str, Any]
    probe_results: list[ProbeSnapshot]
    confidence_summary: dict[str, Any] | None = None


@dataclass(kw_only=True)
class AspectOSD:
    """Proposed O/S/D for one FRIES dimension (0..10 ints, higher = safer).

    O/S/D are integers when evidence supports a heuristic band, or ``None``
    when the agent abstains (missing/skipped evidence — never a fake triple).
    """

    aspect: FriesDimension
    confidence: float
    rationale: str
    O: int | None = None
    S: int | None = None
    D: int | None = None
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    status: ProbeEvaluationStatus | None = None
    O_source: str | None = None
    S_source: str | None = None
    D_source: str | None = None
    osd_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    aspects: list[AspectOSD]
    overall_confidence: float
    methodology_status: MethodologyStatus
    model_ref: str
    assessment_engine: str = "deterministic"


class OSDAgent(Protocol):
    def propose(self, ctx: AgentContext) -> AgentResult: ...
