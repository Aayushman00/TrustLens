"""Local CSV loading/discovery for the user-defined local Fairness path.

Stdlib ``csv`` only — no pandas/pyarrow. Every function here is deterministic
and reads the exact raw values in the file; nothing infers or hardcodes a
sensitive-attribute vocabulary (e.g. no ``gender = [Male, Female]``). Missing
values are surfaced explicitly, never silently folded into another group.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

_MISSING_TOKENS = {"", "na", "n/a", "null", "nan", "none"}
_MISSING_GROUP_LABEL = "(missing)"
_SAMPLE_ROWS_FOR_TYPE_SNIFF = 2000

# First-non-whitespace-character signature of content that is never a valid
# CSV header (HTML/XML markup, JSON) but IS valid UTF-8 text — so it would
# otherwise sail through csv.DictReader as a bogus one-column "dataset". A
# webpage/API-error response returned instead of a raw CSV (e.g. a Hugging
# Face URL resolving to an HTML page) must be caught here, not downstream.
_NON_CSV_LEADING_CHARS = "<{["

# Git LFS pointer files are a fixed, spec-defined text format (see
# https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md#the-pointer):
# a "version" line, then "oid sha256:<64 hex>", then "size <bytes>", with no
# other content. Any raw-file host (raw.githubusercontent.com, Hugging Face
# resolve URLs, GitLab, etc.) that stores a large file under LFS will serve
# exactly this text — a few hundred bytes standing in for the real payload —
# for the *pointer* blob, not the actual dataset content. It is valid UTF-8
# and, because "oid ..."/"size ..." have no comma, sails through
# csv.DictReader as a bogus one-column, two-row "dataset" (matches this
# module's own header + 2 data rows shape), so it must be rejected here by
# its literal spec structure rather than left to look like a real CSV.
_GIT_LFS_POINTER_RE = re.compile(
    r"\Aversion https://git-lfs\.github\.com/spec/v1\r?\n"
    r"oid sha256:[0-9a-f]{64}\r?\n"
    r"size [0-9]+\r?\n?",
)


class UserDatasetError(Exception):
    """Malformed/unreadable local dataset file."""


def _reject_non_csv_signature(text: str) -> None:
    stripped = text.lstrip("﻿ \t\r\n")
    if not stripped:
        return
    if _GIT_LFS_POINTER_RE.match(stripped):
        raise UserDatasetError(
            "this URL returned a Git LFS pointer file, not the actual dataset "
            "content — the file is stored via Git LFS and the host served the "
            "pointer blob instead of the real data; resolve/download the actual "
            "LFS object and host that file directly"
        )
    lowered = stripped[:15].lower()
    if lowered.startswith(("<!doctype html", "<html")):
        raise UserDatasetError(
            "this URL points to a webpage (HTML), not a raw CSV dataset — "
            "use a direct/raw dataset file URL instead"
        )
    if stripped[0] in _NON_CSV_LEADING_CHARS:
        raise UserDatasetError(
            "file content is not CSV (looks like HTML/XML/JSON, not a raw CSV dataset)"
        )


def _decode(data: bytes) -> io.StringIO:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UserDatasetError(f"file is not valid UTF-8 text: {exc}") from exc
    _reject_non_csv_signature(text)
    return io.StringIO(text)


def _is_missing(raw: str | None) -> bool:
    if raw is None:
        return True
    return raw.strip().lower() in _MISSING_TOKENS


def sniff_columns(data: bytes) -> list[dict[str, str]]:
    """Header + a bounded sample of rows -> ``[{"name", "inferred_type"}]``."""
    reader = csv.DictReader(_decode(data))
    if reader.fieldnames is None:
        raise UserDatasetError("CSV file has no header row")
    fieldnames = [f.strip() for f in reader.fieldnames if f is not None]
    if not fieldnames:
        raise UserDatasetError("CSV file has no columns")
    if len(set(fieldnames)) != len(fieldnames):
        raise UserDatasetError("CSV file has duplicate column names")

    samples: dict[str, list[str]] = {name: [] for name in fieldnames}
    for i, row in enumerate(reader):
        if i >= _SAMPLE_ROWS_FOR_TYPE_SNIFF:
            break
        for name in fieldnames:
            value = row.get(name)
            if value is not None and not _is_missing(value):
                samples[name].append(value)

    columns: list[dict[str, str]] = []
    for name in fieldnames:
        values = samples[name]
        inferred = "unknown"
        if values:
            numeric = 0
            for v in values:
                try:
                    float(v)
                    numeric += 1
                except ValueError:
                    pass
            inferred = "numeric" if numeric == len(values) else "categorical"
        columns.append({"name": name, "inferred_type": inferred})
    return columns


def count_rows(data: bytes) -> int:
    """Full pass row count (excludes the header)."""
    reader = csv.reader(_decode(data))
    try:
        next(reader)
    except StopIteration:
        return 0
    return sum(1 for _ in reader)


def discover_group_values(
    data: bytes,
    *,
    group_column: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Distinct raw values + counts for ``group_column``.

    Returns ``(observed_groups, missing_summary)``. ``observed_groups`` is a
    list of ``{"value": str, "count": int}`` sorted by descending count, then
    value; missing/null/empty tokens are collected into one explicit
    ``"(missing)"`` pseudo-group (never folded into a real observed value).
    """
    reader = csv.DictReader(_decode(data))
    if reader.fieldnames is None or group_column not in reader.fieldnames:
        raise UserDatasetError(f"column {group_column!r} not found in dataset")

    counts: dict[str, int] = {}
    missing_reasons: dict[str, int] = {}
    total_rows = 0
    for row in reader:
        total_rows += 1
        raw = row.get(group_column)
        if _is_missing(raw):
            reason = "empty_string" if (raw is None or raw.strip() == "") else "null_token"
            missing_reasons[reason] = missing_reasons.get(reason, 0) + 1
            continue
        value = raw.strip()
        counts[value] = counts.get(value, 0) + 1

    observed = [{"value": v, "count": c} for v, c in counts.items()]
    observed.sort(key=lambda g: (-g["count"], g["value"]))
    missing_count = sum(missing_reasons.values())
    if missing_count:
        observed.append({"value": _MISSING_GROUP_LABEL, "count": missing_count})

    return observed, {"missing_count": missing_count, "missing_reasons": missing_reasons}


def load_rows_for_evaluation(
    data: bytes,
    *,
    target_column: str,
    group_column: str,
    text_column: str,
    excluded_group_values: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One deterministic pass producing rows in the shape the existing Fairness
    statistics consume: ``{"text": str, "label": int, "sensitive": str}``.

    Row order is preserved from file order (no shuffling — this evaluates the
    whole selected file/subset, it is not a sampling step). Missing target,
    missing text, and user-excluded group values are dropped with an explicit,
    counted reason — never silently dropped without a record. Target values
    are sorted deterministically and label-encoded ``0..k-1``.
    """
    reader = csv.DictReader(_decode(data))
    fieldnames = reader.fieldnames or []
    for col in (target_column, group_column, text_column):
        if col not in fieldnames:
            raise UserDatasetError(f"column {col!r} not found in dataset")

    raw_rows: list[dict[str, str]] = []
    rows_dropped_missing_target = 0
    rows_dropped_missing_text = 0
    rows_dropped_missing_group = 0
    rows_dropped_excluded_group = 0

    for row in reader:
        target_raw = row.get(target_column)
        text_raw = row.get(text_column)
        group_raw = row.get(group_column)

        if _is_missing(target_raw):
            rows_dropped_missing_target += 1
            continue
        if text_raw is None or text_raw.strip() == "":
            rows_dropped_missing_text += 1
            continue
        if _is_missing(group_raw):
            rows_dropped_missing_group += 1
            continue
        group_value = group_raw.strip()
        if group_value in excluded_group_values:
            rows_dropped_excluded_group += 1
            continue

        raw_rows.append(
            {
                "text": text_raw,
                "target": target_raw.strip(),
                "sensitive": group_value,
            }
        )

    label_values_seen = sorted({r["target"] for r in raw_rows})
    label_encoding = {value: idx for idx, value in enumerate(label_values_seen)}

    rows = [
        {
            "text": r["text"],
            "label": label_encoding[r["target"]],
            "sensitive": r["sensitive"],
        }
        for r in raw_rows
    ]

    exclusions = {
        "rows_dropped_missing_target": rows_dropped_missing_target,
        "rows_dropped_missing_text": rows_dropped_missing_text,
        "rows_dropped_missing_group": rows_dropped_missing_group,
        "rows_dropped_excluded_group": rows_dropped_excluded_group,
        "label_values_seen": label_values_seen,
        "label_encoding": label_encoding,
    }
    return rows, exclusions


def load_rows_for_evaluation_with_label_mapping(
    data: bytes,
    *,
    target_column: str,
    group_column: str,
    text_column: str,
    excluded_group_values: set[str],
    label_encoding: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Task 4.5 (EvaluationContractV2 Fairness): identical row loading/drop
    semantics to :func:`load_rows_for_evaluation`, except the label encoding
    is an explicit caller-supplied mapping (dataset value -> model output
    index, from the confirmed ``label_mapping``) instead of an internally
    computed alphabetical ``0..k-1`` sort.

    A target value with no entry in ``label_encoding`` is dropped and counted
    as ``rows_dropped_unmapped_label`` — never silently coerced to a
    fabricated index and never a hard error here. Draft confirmation already
    validated ``label_mapping`` covers every value observed in the dataset at
    confirm time (see ``app.services.draft_validation``); this is a runtime
    defense against drift between confirmation and evaluation, not the
    primary enforcement point.
    """
    reader = csv.DictReader(_decode(data))
    fieldnames = reader.fieldnames or []
    for col in (target_column, group_column, text_column):
        if col not in fieldnames:
            raise UserDatasetError(f"column {col!r} not found in dataset")

    rows: list[dict[str, Any]] = []
    rows_dropped_missing_target = 0
    rows_dropped_missing_text = 0
    rows_dropped_missing_group = 0
    rows_dropped_excluded_group = 0
    rows_dropped_unmapped_label = 0
    label_values_seen: set[str] = set()

    for row in reader:
        target_raw = row.get(target_column)
        text_raw = row.get(text_column)
        group_raw = row.get(group_column)

        if _is_missing(target_raw):
            rows_dropped_missing_target += 1
            continue
        if text_raw is None or text_raw.strip() == "":
            rows_dropped_missing_text += 1
            continue
        if _is_missing(group_raw):
            rows_dropped_missing_group += 1
            continue
        group_value = group_raw.strip()
        if group_value in excluded_group_values:
            rows_dropped_excluded_group += 1
            continue

        target_value = target_raw.strip()
        if target_value not in label_encoding:
            rows_dropped_unmapped_label += 1
            continue

        label_values_seen.add(target_value)
        rows.append(
            {
                "text": text_raw,
                "label": label_encoding[target_value],
                "sensitive": group_value,
            }
        )

    exclusions = {
        "rows_dropped_missing_target": rows_dropped_missing_target,
        "rows_dropped_missing_text": rows_dropped_missing_text,
        "rows_dropped_missing_group": rows_dropped_missing_group,
        "rows_dropped_excluded_group": rows_dropped_excluded_group,
        "rows_dropped_unmapped_label": rows_dropped_unmapped_label,
        "label_values_seen": sorted(label_values_seen),
        "label_encoding": label_encoding,
    }
    return rows, exclusions


def load_samples_for_robustness_with_label_mapping(
    data: bytes,
    *,
    target_column: str,
    text_column: str,
    label_encoding: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Task 4.5 (EvaluationContractV2 Robustness): produces
    ``[{"text": str, "label": int}, ...]`` — the exact shape
    ``TransformersCharSwapRunner.run`` consumes as ``samples`` — from a user
    CSV plus an explicit ``label_mapping``. No group/sensitive column (the
    Robustness contract has none). Same missing-value and unmapped-label
    exclusion semantics as ``load_rows_for_evaluation_with_label_mapping``.
    """
    reader = csv.DictReader(_decode(data))
    fieldnames = reader.fieldnames or []
    for col in (target_column, text_column):
        if col not in fieldnames:
            raise UserDatasetError(f"column {col!r} not found in dataset")

    samples: list[dict[str, Any]] = []
    rows_dropped_missing_target = 0
    rows_dropped_missing_text = 0
    rows_dropped_unmapped_label = 0
    label_values_seen: set[str] = set()

    for row in reader:
        target_raw = row.get(target_column)
        text_raw = row.get(text_column)

        if _is_missing(target_raw):
            rows_dropped_missing_target += 1
            continue
        if text_raw is None or text_raw.strip() == "":
            rows_dropped_missing_text += 1
            continue

        target_value = target_raw.strip()
        if target_value not in label_encoding:
            rows_dropped_unmapped_label += 1
            continue

        label_values_seen.add(target_value)
        samples.append({"text": text_raw, "label": label_encoding[target_value]})

    exclusions = {
        "rows_dropped_missing_target": rows_dropped_missing_target,
        "rows_dropped_missing_text": rows_dropped_missing_text,
        "rows_dropped_unmapped_label": rows_dropped_unmapped_label,
        "label_values_seen": sorted(label_values_seen),
        "label_encoding": label_encoding,
    }
    return samples, exclusions
