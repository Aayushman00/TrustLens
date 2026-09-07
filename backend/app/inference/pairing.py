"""Supported model+dataset pairing contracts (tl-methodology-v1.0)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from app.datasets.registry import get_dataset_spec
from app.inference.base import DecisionMode, LoadedModelInfo, TaskType
from app.inference.errors import UNSUPPORTED_MODEL, UNSUPPORTED_TASK, InferenceError

_DEFAULT_RELATIVE = Path("configs") / "supported_pairings_v1.yaml"


class OutputDecodingSpec(BaseModel):
    decision: Literal["argmax", "threshold"] = "argmax"
    label_space: list[str] = Field(min_length=1)
    binary_threshold: float = 0.5


class SupportedPairing(BaseModel):
    id: str
    model_ref: str
    model_revision: str
    task_type: Literal[
        "binary_classification",
        "multiclass_classification",
        "regression",
    ]
    modality: Literal["text", "tabular"] = "text"
    dataset: str
    dataset_revision: str
    input_adapter: str
    required_dataset_fields: list[str] = Field(default_factory=list)
    output_decoding: OutputDecodingSpec
    preprocessing: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

    def task_type_enum(self) -> TaskType:
        return TaskType(self.task_type)

    def decision_mode(self) -> DecisionMode:
        return DecisionMode(self.output_decoding.decision)

    def check_loaded_model(self, loaded: LoadedModelInfo, *, id2label: dict[int, str] | None = None) -> None:
        """Verify loaded head matches the pairing contract."""
        expected_n = len(self.output_decoding.label_space)
        if loaded.num_labels is not None and loaded.num_labels != expected_n:
            raise InferenceError(
                UNSUPPORTED_MODEL,
                "model num_labels does not match pairing label_space",
                details={
                    "pairing_id": self.id,
                    "expected": expected_n,
                    "got": loaded.num_labels,
                },
            )
        if self.task_type == "multiclass_classification" and id2label:
            normalized_expected = [s.strip().lower() for s in self.output_decoding.label_space]
            normalized_got = {
                int(k): str(v).strip().lower() for k, v in id2label.items()
            }
            for idx, name in normalized_got.items():
                if idx < len(normalized_expected) and normalized_expected[idx] != name:
                    raise InferenceError(
                        UNSUPPORTED_MODEL,
                        "model id2label disagrees with pairing label_space",
                        details={
                            "pairing_id": self.id,
                            "index": idx,
                            "expected": normalized_expected[idx],
                            "got": name,
                        },
                    )

    def validate_dataset_pin(self) -> None:
        spec = get_dataset_spec(self.dataset)
        if spec.revision != self.dataset_revision:
            raise ValueError(
                f"pairing {self.id}: dataset_revision {self.dataset_revision!r} "
                f"!= datasets_v1 {spec.revision!r}"
            )


class SupportedPairingsConfigV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    pairings: list[SupportedPairing] = Field(default_factory=list)


def default_pairings_config_path() -> Path:
    env = os.environ.get("PAIRINGS_CONFIG_PATH")
    if env:
        return Path(env)
    cwd_candidate = Path.cwd() / _DEFAULT_RELATIVE
    if cwd_candidate.is_file():
        return cwd_candidate
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / _DEFAULT_RELATIVE


def load_pairings_config(path: Path | str | None = None) -> SupportedPairingsConfigV1:
    resolved = Path(path) if path is not None else default_pairings_config_path()
    if not resolved.is_file():
        raise FileNotFoundError(f"pairings config not found: {resolved}")
    raw: Any = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"pairings config must be a mapping, got {type(raw).__name__}")
    cfg = SupportedPairingsConfigV1.model_validate(raw)
    for pairing in cfg.pairings:
        pairing.validate_dataset_pin()
    return cfg


@lru_cache(maxsize=1)
def _cached_default_pairings() -> SupportedPairingsConfigV1:
    return load_pairings_config()


def resolve_pairing(
    model_ref: str,
    *,
    revision: str | None = None,
    config: SupportedPairingsConfigV1 | None = None,
) -> SupportedPairing | None:
    """Return the pairing for ``model_ref`` (and revision when provided)."""
    cfg = config if config is not None else _cached_default_pairings()
    ref = (model_ref or "").strip()
    if not ref:
        return None
    matches = [p for p in cfg.pairings if p.model_ref == ref]
    if not matches:
        return None
    if revision:
        rev = revision.strip()
        exact = [p for p in matches if p.model_revision == rev]
        if exact:
            return exact[0]
        return None
    if len(matches) == 1:
        return matches[0]
    return None
