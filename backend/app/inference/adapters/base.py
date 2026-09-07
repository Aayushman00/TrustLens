"""ModelInputAdapter — dataset row → model-compatible text inputs (v1.0 text only)."""

from __future__ import annotations

from typing import Any, Protocol


class ModelInputAdapter(Protocol):
    """Transform normalized evaluation rows into InferenceBackend inputs."""

    @property
    def adapter_id(self) -> str: ...

    def normalize_row(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """Map a raw Hub row to ``{text, label, sensitive, ...}`` or drop (None)."""

    def adapt_batch(self, rows: list[dict[str, Any]]) -> list[str]:
        """Deterministic model inputs in row order; raises on malformed rows."""
