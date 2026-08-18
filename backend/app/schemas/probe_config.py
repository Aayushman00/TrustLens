"""Probe configuration schema v1 (Phase 9)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class ProbeConfigV1(BaseModel):
    """Validated evaluation ``probe_config`` payload."""

    schema_version: Literal["v1"] = "v1"
    datasets: dict[str, str] = Field(default_factory=dict)
    attack_budget: float | None = None
    slice_definitions: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


def parse_probe_config(raw: dict[str, Any] | None) -> ProbeConfigV1:
    """Merge raw dict with defaults; reject unknown ``schema_version``.

    Raises:
        ValidationError: when ``schema_version`` is not ``\"v1\"`` or fields are invalid.
    """
    return ProbeConfigV1.model_validate(dict(raw or {}))


__all__ = ["ProbeConfigV1", "parse_probe_config", "ValidationError"]
