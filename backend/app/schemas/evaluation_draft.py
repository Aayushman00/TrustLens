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
    assessment_engine: Literal["deterministic", "legacy_heuristic"] | None = None


class DimensionConfigUpdate(BaseModel):
    dataset_content_id: uuid.UUID
    text_column: str
    target_column: str
    sensitive_column: str | None = None
    label_mapping: list[dict[str, Any]]
    min_group_n: int | None = Field(default=None, gt=0)
    # Fairness-only (like sensitive_column/min_group_n): which model_label_index
    # DP/EO/F1-spread treat as the "positive"/favorable outcome. Defaults to 1
    # to preserve every existing caller's behavior, but a valid label_mapping
    # can legitimately assign the favorable outcome to index 0 -- the
    # fairness_metrics functions must never silently assume index 1 is
    # positive regardless of what the user actually mapped.
    positive_label_index: int = 1


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
    # The frozen model config snapshot (Task 2.4's "fetch once, share across
    # both dimensions" rule) — {"num_labels": int, "id2label": {str: str}}.
    # None until the first GET/PUT on this draft triggers _ensure_model_snapshot.
    # The frontend's label-mapping UI must source its options from here only
    # — never from a hardcoded/invented label list (Global Constraint).
    model_label_snapshot: dict[str, Any] | None = None
