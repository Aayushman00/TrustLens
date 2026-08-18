"""Evidence metadata schemas (ADR 0004 / Phase 8)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    """Immutable reference stored in ``probe_results.evidence_refs`` JSONB."""

    evidence_id: str
    uri: str
    hash: str = Field(..., description='Content hash as "sha256:<hex>"')
    content_type: str
    probe_name: str
    created_at: datetime | None = None


class StoredEvidence(BaseModel):
    """Internal result of a successful put (includes object key and size)."""

    evidence_id: str
    uri: str
    hash: str
    content_type: str
    key: str
    size_bytes: int
