"""FRIES probe plugin contract (Phase 9).

Deterministic order is always F → R → I → E → S. Probes must not assign O/S/D
or FRIES scores — they emit metrics + evidence only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.schemas.evaluation_contract_v2 import EvaluationContractV2
from app.schemas.evidence import EvidenceRef
from app.schemas.probe_config import ProbeConfigV1
from app.storage.evidence_store import DatasetContentStore, EvidenceStore

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

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
    # Frozen EvaluationContractV2 (per-dimension optional contract,
    # content-addressed dataset), or None for an evaluation with no contract
    # attached at all.
    evaluation_contract: EvaluationContractV2 | None = None
    # Task 4.5: content-addressed DatasetContent bytes for EvaluationContractV2's
    # fairness.dataset_content_id / robustness.dataset_content_id.
    dataset_content_store: DatasetContentStore | None = None
    # Task 4.5: DB session, needed by V2 probe paths to resolve a
    # dataset_content_id into its DatasetContent row (storage_uri/content_hash)
    # via DatasetContentRepository. None in tests that never exercise the V2
    # dataset-loading path.
    session: "Session | None" = None


@dataclass
class ProbeOutput:
    dimension: FriesDimension
    metric_values: dict[str, Any]
    confidence: float
    evidence_refs: list[EvidenceRef]
    flags: list[str] = field(default_factory=list)
    status: ProbeEvaluationStatus = ProbeEvaluationStatus.EVALUATED
    status_reason: str | None = None
    error_message: str | None = None


class Probe(Protocol):
    @property
    def dimension(self) -> FriesDimension: ...

    def run(self, ctx: ProbeContext) -> ProbeOutput: ...
