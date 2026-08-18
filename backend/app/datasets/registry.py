"""Load and resolve pinned dataset specs from ``configs/datasets_v1.yaml``."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from app.schemas.probe_config import ProbeConfigV1

_DEFAULT_RELATIVE = Path("configs") / "datasets_v1.yaml"


class DatasetSpec(BaseModel):
    hf_path: str
    revision: str
    modality: Literal["nlp", "vision", "audio", "tabular", "other"] = "nlp"
    config_name: str | None = None
    checksum: str | None = None
    notes: str | None = None


class DatasetsConfigV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    datasets: dict[str, DatasetSpec] = Field(default_factory=dict)


def default_datasets_config_path() -> Path:
    """Resolve yaml path: ``DATASETS_CONFIG_PATH`` or ``configs/datasets_v1.yaml``."""
    env = os.environ.get("DATASETS_CONFIG_PATH")
    if env:
        return Path(env)
    # Prefer CWD (Compose ``/app``); fall back to repo root from this file.
    cwd_candidate = Path.cwd() / _DEFAULT_RELATIVE
    if cwd_candidate.is_file():
        return cwd_candidate
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / _DEFAULT_RELATIVE


def load_datasets_config(path: Path | str | None = None) -> DatasetsConfigV1:
    """Parse and validate the pinned datasets YAML."""
    resolved = Path(path) if path is not None else default_datasets_config_path()
    if not resolved.is_file():
        raise FileNotFoundError(f"datasets config not found: {resolved}")
    raw: Any = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"datasets config must be a mapping, got {type(raw).__name__}")
    return DatasetsConfigV1.model_validate(raw)


@lru_cache(maxsize=1)
def _cached_default_config() -> DatasetsConfigV1:
    return load_datasets_config()


def get_dataset_spec(
    logical_key: str,
    *,
    config: DatasetsConfigV1 | None = None,
) -> DatasetSpec:
    """Return a dataset spec by logical key; raise ``KeyError`` if missing."""
    cfg = config if config is not None else _cached_default_config()
    try:
        return cfg.datasets[logical_key]
    except KeyError as exc:
        raise KeyError(f"unknown dataset logical_key={logical_key!r}") from exc


def validate_probe_config_datasets(
    probe_config: ProbeConfigV1,
    *,
    config: DatasetsConfigV1 | None = None,
) -> None:
    """Ensure every ``probe_config.datasets`` value exists in the yaml registry.

    Values are logical keys into ``datasets_v1.yaml`` (e.g. ``sentiment_fairness``).
    Raises ``ValueError`` listing unknown keys.
    """
    cfg = config if config is not None else _cached_default_config()
    unknown = sorted(
        {key for key in probe_config.datasets.values() if key not in cfg.datasets}
    )
    if unknown:
        raise ValueError(
            f"probe_config.datasets references unknown logical keys: {unknown}"
        )
