"""Request/response schemas for the EvaluationDraft intake lifecycle."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.enums import EvaluationMode


class CreateDraftRequest(BaseModel):
    model_id: int


class CreateEvaluationV2Request(BaseModel):
    """Request body for ``POST /v1/evaluations-v2`` (Task 4.4) — same
    correction noted in Task 2.5: a typed schema, not a raw ``dict``."""

    draft_id: uuid.UUID
    evaluation_mode: EvaluationMode


class DimensionConfigUpdate(BaseModel):
    dataset_content_id: uuid.UUID
    text_column: str
    target_column: str
    sensitive_column: str | None = None
    label_mapping: list[dict[str, Any]]
    min_group_n: int | None = Field(default=None, gt=0)


class DimensionValidationRead(BaseModel):
    ok: bool
    errors: list[str]
    group_preview: list[dict[str, Any]] | None = None
    groups_remaining: int | None = None
    n_label_compatible: int | None = None
    n_excluded: int | None = None


class EvaluationDraftRead(BaseModel):
    id: uuid.UUID
    model_id: int
    status: Literal["incomplete", "validated", "consumed", "stale"]
    fairness_confirmed: bool
    robustness_confirmed: bool
