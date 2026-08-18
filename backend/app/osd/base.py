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

from app.db.enums import FriesDimension

METHODOLOGY_STATUS: Literal["PROPOSED_REQUIRES_VALIDATION"] = (
    "PROPOSED_REQUIRES_VALIDATION"
)


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


@dataclass
class AspectOSD:
    """Proposed O/S/D for one FRIES dimension (0..10 ints, higher = safer)."""

    aspect: FriesDimension
    O: int
    S: int
    D: int
    confidence: float
    rationale: str
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentResult:
    aspects: list[AspectOSD]
    overall_confidence: float
    methodology_status: Literal["PROPOSED_REQUIRES_VALIDATION"]
    model_ref: str


class OSDAgent(Protocol):
    def propose(self, ctx: AgentContext) -> AgentResult: ...
