"""InferenceBackend contract — probes depend on this, not Transformers."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.inference.errors import NOT_LOADED, InferenceError


class TaskType(str, enum.Enum):
    BINARY_CLASSIFICATION = "binary_classification"
    MULTICLASS_CLASSIFICATION = "multiclass_classification"
    REGRESSION = "regression"


class DecisionMode(str, enum.Enum):
    ARGMAX = "argmax"
    THRESHOLD = "threshold"


@dataclass(frozen=True)
class InferenceConfig:
    task_type: TaskType = TaskType.MULTICLASS_CLASSIFICATION
    batch_size: int = 8
    # "auto" resolves to CUDA when genuinely available, else CPU (see
    # app.inference.device.resolve_device) — never a hardcoded "cpu" default
    # that silently ignores a present GPU.
    device: str = "auto"
    max_length: int = 256
    decision: DecisionMode = DecisionMode.ARGMAX
    binary_threshold: float = 0.5


@dataclass(frozen=True)
class PredictionRecord:
    y_hat: int | float
    probabilities: list[float] | None = None
    logits: list[float] | None = None


@dataclass(frozen=True)
class InferenceMetadata:
    model_ref: str
    revision: str | None
    task_type: str
    device: str
    device_name: str | None
    dtype: str | None
    batch_size: int
    backend: str
    num_labels: int | None = None
    # GPU/device-decision evidence (app.inference.device.DeviceDecision) —
    # never fabricated; None/False when detection genuinely found nothing.
    execution_device: str | None = None
    gpu_available: bool | None = None
    gpu_name: str | None = None
    cuda_available: bool | None = None
    device_reason: str | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True)
class DeviceInfo:
    device: str
    device_type: str
    device_name: str | None
    dtype: str | None
    batch_size: int
    backend: str
    execution_device: str | None = None
    gpu_available: bool | None = None
    gpu_name: str | None = None
    cuda_available: bool | None = None
    device_reason: str | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True)
class BatchPrediction:
    predictions: list[PredictionRecord]
    n_samples: int
    metadata: InferenceMetadata


@dataclass
class LoadedModelInfo:
    """Exposed after load for probe-level label-space checks."""

    num_labels: int | None = None
    problem_type: str | None = None
    id2label: dict[int, str] | None = None


class InferenceBackend(Protocol):
    def load(
        self,
        model_ref: str,
        *,
        revision: str | None = None,
        config: InferenceConfig | None = None,
        hf_token: str | None = None,
    ) -> LoadedModelInfo: ...

    def predict(self, inputs: list[str]) -> BatchPrediction: ...

    def predict_batch(self, inputs: list[str]) -> BatchPrediction: ...

    def device_info(self) -> DeviceInfo: ...

    def close(self) -> None: ...


def require_loaded(backend: Any) -> None:
    """Guard for backends that track loaded state."""
    if not getattr(backend, "is_loaded", False):
        raise InferenceError(NOT_LOADED, "model is not loaded — call load() first")
