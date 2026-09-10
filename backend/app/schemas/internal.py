"""Internal (service-to-service) schemas — Celery task payloads (Phase 7)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.enums import EvaluationMode
from app.scoring.methodology_version import LEGACY_METHODOLOGY_VERSION


class EvaluateModelPayload(BaseModel):
    """v1 contract for the ``trustlens.evaluate_model`` Celery task (ADR 0005)."""

    schema_version: Literal["v1"] = "v1"
    evaluation_id: uuid.UUID
    model_ref: str
    evaluation_mode: EvaluationMode
    probe_config: dict[str, Any] = Field(default_factory=dict)
    # Phase 7: frozen at create time — the worker must not re-derive these
    # from a possibly-drifted ``Model`` row.
    model_revision: str | None = None
    evaluation_contract: dict[str, Any] = Field(default_factory=dict)
    # Task 4.3: defaults to LEGACY so every payload predating the new
    # evaluation-creation path (Task 4.4) keeps byte-for-byte legacy
    # confidence/FRIES-completeness behavior; Task 4.4 sets this explicitly
    # for evaluations created under the new methodology.
    methodology_version: str = LEGACY_METHODOLOGY_VERSION
