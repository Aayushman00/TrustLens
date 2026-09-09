"""Versioned robustness dataset compatibility (tl-methodology-v1.0).

Separate from fairness pairings — explicit model identity → allowed robustness pin.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from app.datasets.registry import get_dataset_spec

_DEFAULT_RELATIVE = Path("configs") / "supported_robustness_compat_v1.yaml"


class RobustnessCompatEntry(BaseModel):
    model_ref: str
    model_revision: str
    robustness_dataset_key: str
    evaluation_domain: str
    notes: str | None = None

    def validate_dataset_pin(self) -> None:
        spec = get_dataset_spec(self.robustness_dataset_key)
        if spec.evaluation_domain and spec.evaluation_domain != self.evaluation_domain:
            raise ValueError(
                f"robustness compat {self.model_ref}: evaluation_domain "
                f"{self.evaluation_domain!r} != datasets_v1 "
                f"{spec.evaluation_domain!r}"
            )


class SupportedRobustnessCompatConfigV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    compat: list[RobustnessCompatEntry] = Field(default_factory=list)


def default_robustness_compat_config_path() -> Path:
    env = os.environ.get("ROBUSTNESS_COMPAT_CONFIG_PATH")
    if env:
        return Path(env)
    cwd_candidate = Path.cwd() / _DEFAULT_RELATIVE
    if cwd_candidate.is_file():
        return cwd_candidate
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / _DEFAULT_RELATIVE


def load_robustness_compat_config(
    path: Path | str | None = None,
) -> SupportedRobustnessCompatConfigV1:
    resolved = Path(path) if path is not None else default_robustness_compat_config_path()
    if not resolved.is_file():
        raise FileNotFoundError(f"robustness compat config not found: {resolved}")
    raw: Any = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"robustness compat config must be a mapping, got {type(raw).__name__}"
        )
    cfg = SupportedRobustnessCompatConfigV1.model_validate(raw)
    for entry in cfg.compat:
        entry.validate_dataset_pin()
    return cfg


@lru_cache(maxsize=1)
def _cached_default_compat() -> SupportedRobustnessCompatConfigV1:
    return load_robustness_compat_config()


def resolve_robustness_compat(
    model_ref: str,
    *,
    revision: str | None = None,
    config: SupportedRobustnessCompatConfigV1 | None = None,
) -> RobustnessCompatEntry | None:
    """Return compat entry for ``model_ref`` (and revision when provided)."""
    cfg = config if config is not None else _cached_default_compat()
    ref = (model_ref or "").strip()
    if not ref:
        return None
    matches = [e for e in cfg.compat if e.model_ref == ref]
    if not matches:
        return None
    if revision:
        rev = revision.strip()
        exact = [e for e in matches if e.model_revision == rev]
        if exact:
            return exact[0]
        return None
    if len(matches) == 1:
        return matches[0]
    return None
