"""Typed inference errors — not HTTP AppError; probes map to FAILED / model_load_failed."""

from __future__ import annotations

from typing import Any

MODEL_LOAD_ERROR = "MODEL_LOAD_ERROR"
UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"
UNSUPPORTED_TASK = "UNSUPPORTED_TASK"
INVALID_MODEL_REVISION = "INVALID_MODEL_REVISION"
TOKENIZATION_ERROR = "TOKENIZATION_ERROR"
INFERENCE_ERROR = "INFERENCE_ERROR"
INVALID_INPUT = "INVALID_INPUT"
NOT_LOADED = "NOT_LOADED"


class InferenceError(Exception):
    """Backend failure with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)
