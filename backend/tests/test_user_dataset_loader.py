"""Unit tests for the user-defined local Fairness CSV loader (no HF/network)."""

from __future__ import annotations

import pytest

from app.datasets.user_dataset import (
    UserDatasetError,
    count_rows,
    discover_group_values,
    load_rows_for_evaluation,
    sniff_columns,
)

_CSV = (
    "text,label,gender\n"
    "great product,1,Female\n"
    "bad product,0,Male\n"
    "ok product,1,Male\n"
    "terrible,0,Female\n"
    "fine,1,Non-binary\n"
    "meh,0,\n"
    "cool,1,N/A\n"
).encode("utf-8")


def test_sniff_columns_infers_types() -> None:
    columns = sniff_columns(_CSV)
    names = {c["name"]: c["inferred_type"] for c in columns}
    assert names["text"] == "categorical"
    assert names["label"] == "numeric"
    assert names["gender"] == "categorical"


def test_count_rows_excludes_header() -> None:
    assert count_rows(_CSV) == 7


def test_discover_group_values_reports_missing_explicitly() -> None:
    observed, missing = discover_group_values(_CSV, group_column="gender")
    values = {g["value"]: g["count"] for g in observed}
    assert values["Male"] == 2
    assert values["Female"] == 2
    assert values["Non-binary"] == 1
    # missing/null tokens are never folded into a real observed group —
    # they appear as one explicit "(missing)" pseudo-group.
    assert values["(missing)"] == 2
    assert missing["missing_count"] == 2
    assert missing["missing_reasons"]["empty_string"] == 1
    assert missing["missing_reasons"]["null_token"] == 1
    # no hardcoded category vocabulary — every value comes from the file.
    assert set(values) == {"Male", "Female", "Non-binary", "(missing)"}


def test_discover_group_values_unknown_column_raises() -> None:
    with pytest.raises(UserDatasetError):
        discover_group_values(_CSV, group_column="nope")


def test_load_rows_for_evaluation_drops_missing_group_rows_deterministically() -> None:
    rows, exclusions = load_rows_for_evaluation(
        _CSV,
        target_column="label",
        group_column="gender",
        text_column="text",
        excluded_group_values=set(),
    )
    assert len(rows) == 5  # the 2 missing-gender rows are dropped
    assert exclusions["rows_dropped_missing_group"] == 2
    assert exclusions["rows_dropped_missing_target"] == 0
    assert exclusions["rows_dropped_missing_text"] == 0
    assert exclusions["label_values_seen"] == ["0", "1"]
    assert exclusions["label_encoding"] == {"0": 0, "1": 1}
    assert all(r["label"] in (0, 1) for r in rows)
    assert {r["sensitive"] for r in rows} == {"Male", "Female", "Non-binary"}


def test_load_rows_for_evaluation_respects_user_excluded_groups() -> None:
    rows, exclusions = load_rows_for_evaluation(
        _CSV,
        target_column="label",
        group_column="gender",
        text_column="text",
        excluded_group_values={"Non-binary"},
    )
    assert exclusions["rows_dropped_excluded_group"] == 1
    assert "Non-binary" not in {r["sensitive"] for r in rows}


def test_load_rows_for_evaluation_missing_target_and_text_are_dropped_and_counted() -> None:
    csv_bytes = (
        "text,label,gender\n"
        "hello,1,A\n"
        ",1,A\n"
        "hello again,,A\n"
        "hello3,0,B\n"
    ).encode("utf-8")
    rows, exclusions = load_rows_for_evaluation(
        csv_bytes,
        target_column="label",
        group_column="gender",
        text_column="text",
        excluded_group_values=set(),
    )
    assert exclusions["rows_dropped_missing_text"] == 1
    assert exclusions["rows_dropped_missing_target"] == 1
    assert len(rows) == 2


def test_unknown_column_raises_for_evaluation_loader() -> None:
    with pytest.raises(UserDatasetError):
        load_rows_for_evaluation(
            _CSV,
            target_column="nope",
            group_column="gender",
            text_column="text",
            excluded_group_values=set(),
        )
