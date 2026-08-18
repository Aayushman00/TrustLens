"""Load pinned Hugging Face dataset subsets (Phase 11).

Lazy-imports ``datasets`` so API/unit tests without the optional stack still import.
"""

from __future__ import annotations

from typing import Any

from app.datasets.registry import DatasetSpec, get_dataset_spec


class DatasetLoadError(Exception):
    """Pinned dataset could not be loaded or normalized."""


def _pick_text(row: dict[str, Any]) -> str | None:
    for key in ("text", "sentence", "content", "review", "premise"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _pick_label(row: dict[str, Any]) -> int | None:
    for key in ("label", "labels", "class", "target"):
        value = row.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value == int(value):
            return int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
    return None


def normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Map a raw HF row to ``{text, label}`` or return None if unusable."""
    text = _pick_text(row)
    label = _pick_label(row)
    if text is None or label is None:
        return None
    return {"text": text, "label": label}


def load_pinned_subset(
    logical_key: str,
    *,
    n: int,
    seed: int,
    spec: DatasetSpec | None = None,
) -> list[dict[str, Any]]:
    """Load up to ``n`` shuffled labeled text rows from a pinned dataset.

    Raises:
        DatasetLoadError: missing package, Hub failure, or no usable rows.
    """
    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError as exc:
        raise DatasetLoadError(
            "Hugging Face 'datasets' package is not installed"
        ) from exc

    dataset_spec = spec if spec is not None else get_dataset_spec(logical_key)
    kwargs: dict[str, Any] = {
        "path": dataset_spec.hf_path,
        "revision": dataset_spec.revision,
        "split": "train",
    }
    if dataset_spec.config_name:
        kwargs["name"] = dataset_spec.config_name

    try:
        ds = load_dataset(**kwargs)
    except Exception as exc:  # noqa: BLE001 — Hub / IO surface as DatasetLoadError
        raise DatasetLoadError(f"failed to load {logical_key}: {exc}") from exc

    try:
        shuffled = ds.shuffle(seed=seed)
        take = min(max(n, 0), len(shuffled))
        subset = shuffled.select(range(take)) if take else shuffled.select([])
    except Exception as exc:  # noqa: BLE001
        raise DatasetLoadError(f"failed to sample {logical_key}: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for item in subset:
        raw = dict(item) if not isinstance(item, dict) else item
        normalized = normalize_row(raw)
        if normalized is not None:
            rows.append(normalized)
    if not rows:
        raise DatasetLoadError(f"no usable text/label rows in {logical_key}")
    return rows


def _encode_binary_label(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {">50k", ">50k.", "1", "true", "yes"}:
        return 1
    if text in {"<=50k", "<=50k.", "0", "false", "no"}:
        return 0
    if text.lstrip("-").isdigit():
        return int(text)
    return None


def normalize_fairness_row(
    row: dict[str, Any],
    *,
    sensitive_attribute: str,
    label_keys: tuple[str, ...] = ("class", "income", "label", "target"),
) -> dict[str, Any] | None:
    """Map a tabular row to ``{label, sensitive, features}``."""
    if sensitive_attribute not in row:
        return None
    sensitive = row[sensitive_attribute]
    if sensitive is None or (isinstance(sensitive, str) and not sensitive.strip()):
        return None
    label: int | None = None
    for key in label_keys:
        if key in row:
            label = _encode_binary_label(row[key])
            if label is not None:
                break
    if label is None:
        return None
    features = {
        k: v
        for k, v in row.items()
        if k not in {*label_keys, sensitive_attribute}
    }
    return {
        "label": label,
        "sensitive": sensitive if not isinstance(sensitive, str) else sensitive.strip(),
        "features": features,
    }


def load_fairness_subset(
    logical_key: str,
    *,
    n: int,
    seed: int,
    sensitive_attribute: str,
    spec: DatasetSpec | None = None,
) -> list[dict[str, Any]]:
    """Load tabular fairness rows with label + sensitive attribute.

    Raises:
        DatasetLoadError: missing package, Hub failure, or no usable rows.
    """
    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError as exc:
        raise DatasetLoadError(
            "Hugging Face 'datasets' package is not installed"
        ) from exc

    dataset_spec = spec if spec is not None else get_dataset_spec(logical_key)
    if dataset_spec.modality not in {"tabular", "other"}:
        raise DatasetLoadError(
            f"fairness loader requires tabular/other modality, got {dataset_spec.modality}"
        )

    kwargs: dict[str, Any] = {
        "path": dataset_spec.hf_path,
        "revision": dataset_spec.revision,
        "split": "train",
    }
    if dataset_spec.config_name:
        kwargs["name"] = dataset_spec.config_name

    try:
        ds = load_dataset(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise DatasetLoadError(f"failed to load {logical_key}: {exc}") from exc

    try:
        shuffled = ds.shuffle(seed=seed)
        take = min(max(n, 0), len(shuffled))
        subset = shuffled.select(range(take)) if take else shuffled.select([])
    except Exception as exc:  # noqa: BLE001
        raise DatasetLoadError(f"failed to sample {logical_key}: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for item in subset:
        raw = dict(item) if not isinstance(item, dict) else item
        normalized = normalize_fairness_row(
            raw, sensitive_attribute=sensitive_attribute
        )
        if normalized is not None:
            rows.append(normalized)
    if not rows:
        raise DatasetLoadError(
            f"no usable fairness rows in {logical_key} "
            f"(sensitive={sensitive_attribute!r})"
        )
    return rows
