"""Column-role and label-mapping validation against a DatasetContent's raw
bytes and a model's ModelLabelSnapshot. Runs at intake time, before the
worker ever sees anything — reuses app.datasets.user_dataset's CSV parsing,
never re-implements it."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app.datasets.user_dataset import UserDatasetError, discover_group_values
from app.inference.model_inspection import ModelLabelSnapshot

_MISSING_TOKENS = {"", "na", "n/a", "null", "nan", "none"}


@dataclass
class FairnessValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    group_preview: list[dict] = field(default_factory=list)
    groups_remaining: int = 0


@dataclass
class RobustnessValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    n_label_compatible: int = 0
    n_excluded: int = 0


def _validate_label_mapping(label_mapping: list[dict], target_values: set[str], snapshot: ModelLabelSnapshot) -> list[str]:
    errors: list[str] = []
    mapped_values = {entry["dataset_value"] for entry in label_mapping}
    missing = target_values - mapped_values
    if missing:
        errors.append(f"label_mapping is missing entries for observed target values: {sorted(missing)}")
    for entry in label_mapping:
        idx = entry["model_label_index"]
        if idx not in snapshot.id2label:
            errors.append(f"label_mapping entry {entry!r} references unknown model_label_index={idx}")
    return errors


def _observed_target_values(data: bytes, target_column: str) -> set[str]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if reader.fieldnames is None or target_column not in reader.fieldnames:
        raise UserDatasetError(f"column {target_column!r} not found in dataset")
    values: set[str] = set()
    for row in reader:
        raw = row.get(target_column)
        if raw is not None and raw.strip().lower() not in _MISSING_TOKENS:
            values.add(raw.strip())
    return values


def validate_fairness_config(
    *,
    dataset_bytes: bytes,
    text_column: str,
    target_column: str,
    sensitive_column: str,
    label_mapping: list[dict],
    model_label_snapshot: ModelLabelSnapshot,
    min_group_n: int,
) -> FairnessValidationResult:
    errors: list[str] = []
    try:
        observed_groups, _missing = discover_group_values(dataset_bytes, group_column=sensitive_column)
    except UserDatasetError as exc:
        return FairnessValidationResult(ok=False, errors=[str(exc)])

    try:
        target_values = _observed_target_values(dataset_bytes, target_column)
    except UserDatasetError as exc:
        return FairnessValidationResult(ok=False, errors=[f"could not read target_column={target_column!r}: {exc}"])

    errors.extend(_validate_label_mapping(label_mapping, target_values, model_label_snapshot))

    group_preview = [
        {"value": g["value"], "count": g["count"], "meets_min_group_n": g["count"] >= min_group_n}
        for g in observed_groups
    ]
    groups_remaining = sum(1 for g in group_preview if g["meets_min_group_n"])
    if groups_remaining < 2:
        errors.append(
            f"fewer than 2 groups meet min_group_n={min_group_n} "
            f"(groups_remaining={groups_remaining}) — Fairness comparison would be INSUFFICIENT_EVIDENCE"
        )

    return FairnessValidationResult(
        ok=not errors, errors=errors, group_preview=group_preview, groups_remaining=groups_remaining
    )


def validate_robustness_config(
    *,
    dataset_bytes: bytes,
    text_column: str,
    target_column: str,
    label_mapping: list[dict],
    model_label_snapshot: ModelLabelSnapshot,
) -> RobustnessValidationResult:
    try:
        target_values = _observed_target_values(dataset_bytes, target_column)
    except UserDatasetError as exc:
        return RobustnessValidationResult(ok=False, errors=[f"could not read target_column={target_column!r}: {exc}"])

    errors = _validate_label_mapping(label_mapping, target_values, model_label_snapshot)

    reader = csv.DictReader(io.StringIO(dataset_bytes.decode("utf-8-sig")))
    mapped = {entry["dataset_value"]: entry["model_label_index"] for entry in label_mapping}
    total = 0
    compatible = 0
    for row in reader:
        total += 1
        raw = (row.get(target_column) or "").strip()
        if raw in mapped:
            compatible += 1
    excluded = total - compatible

    return RobustnessValidationResult(
        ok=not errors, errors=errors, n_label_compatible=compatible, n_excluded=excluded
    )
