"""Local model inference abstraction (tl-methodology-v1.0)."""

from app.inference.base import (
    BatchPrediction,
    DecisionMode,
    DeviceInfo,
    InferenceBackend,
    InferenceConfig,
    InferenceMetadata,
    LoadedModelInfo,
    PredictionRecord,
    TaskType,
)
from app.inference.errors import InferenceError
from app.inference.local_hf import LocalHFBackend
from app.inference.pairing import resolve_pairing, SupportedPairing

__all__ = [
    "BatchPrediction",
    "DecisionMode",
    "DeviceInfo",
    "InferenceBackend",
    "InferenceConfig",
    "InferenceError",
    "InferenceMetadata",
    "LoadedModelInfo",
    "LocalHFBackend",
    "PredictionRecord",
    "SupportedPairing",
    "TaskType",
    "resolve_pairing",
]
