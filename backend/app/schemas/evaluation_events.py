"""Evaluation event (lifecycle audit trail) schemas — Phase 4."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvaluationEventRead(BaseModel):
    """One append-only lifecycle audit row. Read-only — no create/update schema
    exists on purpose; events are inserted only by internal pipeline/service
    code, never through a client-facing write endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    evaluation_id: uuid.UUID
    # Plain string, not a strict Literal — new event types may be added in a
    # later phase without breaking an older frontend build's parsing of this
    # field (an unrecognized type should render as a generic labeled row).
    event_type: str
    created_at: datetime
    detail: dict[str, Any] | None = None


class EvaluationEventList(BaseModel):
    items: list[EvaluationEventRead] = Field(default_factory=list)
