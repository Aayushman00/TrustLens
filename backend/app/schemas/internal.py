"""Internal (service-to-service) schemas — Celery task payloads (Phase 7)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.enums import EvaluationMode


class EvaluateModelPayload(BaseModel):
    """v1 contract for the ``trustlens.evaluate_model`` Celery task (ADR 0005)."""

    schema_version: Literal["v1"] = "v1"
    evaluation_id: uuid.UUID
    model_ref: str
    evaluation_mode: EvaluationMode
    probe_config: dict[str, Any] = Field(default_factory=dict)
