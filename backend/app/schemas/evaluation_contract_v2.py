"""V1 redesign: per-dimension optional contract, content-addressed dataset
reference, explicit label mapping. Coexists with the legacy flat
EvaluationContractV1 in app.schemas.evaluation_contract during the
migration (Phases 4-6); the legacy module is deleted in Phase 7."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class LabelMappingEntry(BaseModel):
    dataset_value: str
    model_label_index: int


class ModelLabelSnapshot(BaseModel):
    num_labels: int
    id2label: dict[int, str]


class FairnessContractV2(BaseModel):
    dataset_content_id: uuid.UUID
    text_column: str
    target_column: str
    sensitive_column: str
    label_mapping: list[LabelMappingEntry]
    min_group_n: int = Field(gt=0)


class RobustnessContractV2(BaseModel):
    dataset_content_id: uuid.UUID
    text_column: str
    target_column: str
    label_mapping: list[LabelMappingEntry]


class EvaluationContractV2(BaseModel):
    schema_version: Literal["v2"] = "v2"
    model_ref: str
    model_revision: str
    resolved_model_sha: str
    model_label_snapshot: ModelLabelSnapshot
    fairness: FairnessContractV2 | None = None
    robustness: RobustnessContractV2 | None = None


__all__ = [
    "LabelMappingEntry",
    "ModelLabelSnapshot",
    "FairnessContractV2",
    "RobustnessContractV2",
    "EvaluationContractV2",
]
