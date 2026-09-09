"""Storage package — EvidenceStore (ADR 0004 / Phase 8)."""

from app.storage.evidence_store import EvidenceStore, EvidenceStoreError, get_evidence_store

__all__ = [
    "EvidenceStore",
    "EvidenceStoreError",
    "get_evidence_store",
]
