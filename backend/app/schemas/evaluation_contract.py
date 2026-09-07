"""Evaluation contract schema v1 (Phase 7).

Explicit, persisted record of *which* dataset/pairing a Fairness/Robustness
probe run is faithful to — resolved once at evaluation create time and frozen
onto ``evaluations.probe_config.evaluation_contract`` (ADR pending). No
control-flow behavior change lands here: probes still decide what to do with
this contract in later phases.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EvaluationContractV1(BaseModel):
    """Frozen evaluation contract: what dataset/pairing this run is faithful to."""

    schema_version: Literal["v1"] = "v1"
    kind: Literal[
        "pairing",
        "registry",
        "proxy_lr",
        "documentation_only",
    ]

    pairing_id: str | None = None
    dataset_key: str | None = None
    dataset_revision: str | None = None

    model_ref: str
    model_revision: str

    task_type: str | None = None
    label_space: list[str] | list[int] | None = None
    modality: str | None = None
    input_adapter: str | None = None


__all__ = ["EvaluationContractV1"]
