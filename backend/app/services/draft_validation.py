"""Column-role and label-mapping validation against a DatasetContent's raw
bytes and a model's ModelLabelSnapshot. Runs at intake time, before the
worker ever sees anything — reuses app.datasets.user_dataset's CSV parsing,
never re-implements it."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field

from app.datasets.user_dataset import UserDatasetError, _decode, discover_group_values
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


def _validate_label_mapping(
    label_mapping: list[dict], target_values: set[str], snapshot: ModelLabelSnapshot
) -> tuple[list[str], set[int]]:
    """Returns (errors, reachable_indices) -- reachable_indices is every
    model_label_index a *valid* label_mapping entry actually points at, i.e.
    every index ground truth can attain once this mapping is applied. Used
    by callers (e.g. positive_label_index validation) that must not accept
    an index merely because the model happens to have it -- it also has to
    be one this specific mapping can ever produce."""
    errors: list[str] = []
    valid_entries = []
    for entry in label_mapping:
        if "dataset_value" not in entry or "model_label_index" not in entry:
            errors.append(f"label_mapping entry {entry!r} is missing required keys")
            continue
        valid_entries.append(entry)

    # A dataset_value appearing more than once is a contradiction, not a
    # policy choice: one ground-truth row can only carry one true label, so
    # two entries for the same dataset_value can never both be honored.
    # Reject explicitly rather than silently keeping whichever entry a
    # downstream dict comprehension happens to see last.
    seen_values: dict[str, int] = {}
    duplicate_values: set[str] = set()
    for entry in valid_entries:
        value = entry["dataset_value"]
        if value in seen_values:
            duplicate_values.add(value)
        else:
            seen_values[value] = 0
    if duplicate_values:
        errors.append(
            f"label_mapping has duplicate entries for dataset_value(s): {sorted(duplicate_values)}"
        )

    mapped_values = {entry["dataset_value"] for entry in valid_entries}
    missing = target_values - mapped_values
    if missing:
        errors.append(f"label_mapping is missing entries for observed target values: {sorted(missing)}")
    reachable_indices: set[int] = set()
    for entry in valid_entries:
        idx = entry["model_label_index"]
        if idx not in snapshot.id2label:
            errors.append(f"label_mapping entry {entry!r} references unknown model_label_index={idx}")
        else:
            reachable_indices.add(idx)
    return errors, reachable_indices


def _observed_target_values(data: bytes, target_column: str) -> set[str]:
    reader = csv.DictReader(_decode(data))
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
    positive_label_index: int = 1,
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

    mapping_errors, reachable_indices = _validate_label_mapping(
        label_mapping, target_values, model_label_snapshot
    )
    errors.extend(mapping_errors)

    # positive_label_index must be reachable: not merely a valid model
    # index, but one this specific label_mapping actually points a dataset
    # value at. An index the model has but no mapped dataset value ever
    # produces means ground truth can never take that value -- TPR/F1 are
    # then computed against a class that structurally never occurs (tp is
    # always 0), producing a numerically well-formed but meaningless result
    # that still reports EVALUATED at high confidence. Confirmed by real
    # execution this session: positive_label_index defaulted to 1 while the
    # mapping only ever produced 0/2, giving TPR=0/F1=0 for every group.
    if positive_label_index not in reachable_indices:
        errors.append(
            f"positive_label_index={positive_label_index} is not reachable by this "
            f"label_mapping (mapped model_label_index values: {sorted(reachable_indices)}) "
            "-- ground truth could never attain it, making DP/EO/F1 meaningless"
        )

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

    errors, _reachable_indices = _validate_label_mapping(label_mapping, target_values, model_label_snapshot)

    try:
        reader = csv.DictReader(_decode(dataset_bytes))
    except UserDatasetError as exc:
        return RobustnessValidationResult(ok=False, errors=errors + [f"could not read dataset: {exc}"])
    mapped = {
        entry["dataset_value"]: entry["model_label_index"]
        for entry in label_mapping
        if "dataset_value" in entry and "model_label_index" in entry
    }
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
