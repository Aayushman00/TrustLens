"""FRIES probe plugin contract (Phase 9).

Deterministic order is always F → R → I → E → S. Probes must not assign O/S/D
or FRIES scores — they emit metrics + evidence only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.db.enums import FriesDimension
from app.schemas.evidence import EvidenceRef
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import EvidenceStore

FRIES_PROBE_ORDER: tuple[FriesDimension, ...] = (
    FriesDimension.FAIRNESS,
    FriesDimension.ROBUSTNESS,
    FriesDimension.INTEGRITY,
    FriesDimension.EXPLAINABILITY,
    FriesDimension.SAFETY,
)


@dataclass
class ProbeContext:
    evaluation_id: uuid.UUID
    model_ref: str
    model_metadata: dict[str, Any]
    probe_config: ProbeConfigV1
    evidence_store: EvidenceStore
    # From Model ORM columns (Phase 6); not inside metadata JSONB.
    model_revision: str | None = None
    model_checksum: str | None = None


@dataclass
class ProbeOutput:
    dimension: FriesDimension
    metric_values: dict[str, Any]
    confidence: float
    evidence_refs: list[EvidenceRef]
    flags: list[str] = field(default_factory=list)


class Probe(Protocol):
    @property
    def dimension(self) -> FriesDimension: ...

    def run(self, ctx: ProbeContext) -> ProbeOutput: ...
