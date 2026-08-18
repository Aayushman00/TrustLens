"""Model Adapter boundary (Phase 6, ADR 0012).

The evaluation engine (Phase 9+) must depend only on ``NormalizedModelRecord`` /
``ModelAdapter`` from this module — never on a specific source's SDK (e.g.
``huggingface_hub``) directly. This keeps evaluation independent of how a model
was ingested and leaves room for post-MVP adapters (local, uploaded artifacts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.api.errors import AppError


@dataclass
class NormalizedModelRecord:
    """Adapter-agnostic result of resolving a model reference."""

    hf_repo_id: str
    revision: str | None
    checksum: str | None
    model_metadata: dict[str, Any] = field(default_factory=dict)


class ModelAdapter(Protocol):
    """Standardized resolution interface implemented by each model source."""

    def resolve(self, ref: str, revision: str | None = None) -> NormalizedModelRecord: ...


class InvalidModelRefError(AppError):
    """Malformed reference or a non-allowlisted host (SSRF guard)."""

    def __init__(
        self,
        message: str = "Invalid Hugging Face model reference",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("INVALID_MODEL_REF", message, status_code=422, details=details)


class ModelNotFoundError(AppError):
    """Repo or revision does not exist on the Hub."""

    def __init__(
        self,
        message: str = "Model not found on Hugging Face Hub",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("MODEL_NOT_FOUND", message, status_code=404, details=details)


class HfHubUnavailableError(AppError):
    """Network/API failure talking to the Hub (not a "not found")."""

    def __init__(
        self,
        message: str = "Hugging Face Hub is currently unavailable",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("HF_HUB_UNAVAILABLE", message, status_code=502, details=details)


class HfAuthRequiredError(AppError):
    """Gated/private repo and no (or insufficient) HF_TOKEN."""

    def __init__(
        self,
        message: str = "This model is gated — set HF_TOKEN with access to import it",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("HF_AUTH_REQUIRED", message, status_code=403, details=details)
