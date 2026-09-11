from app.inference.model_inspection import ModelLabelSnapshot
from app.services.draft_validation import validate_fairness_config, validate_robustness_config

SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="abc")

CSV = b"text,label,group\nhello,pos,a\nworld,neg,a\nfoo,pos,b\nbar,neg,b\nbaz,pos,b\n"

# Simulates the raw bytes of a DatasetContent row created before the
# HTML/JSON ingestion rejection existed (residue that pre-dates the fix,
# stored via DatasetContentStore.put with no structural validation). Dataset
# ingestion no longer lets such a row be *created*, but dimension validation
# must independently refuse to *use* one if it is ever selected -- it must
# not be silently accepted as a valid Fairness/Robustness input just because
# a DatasetContent row already exists for it.
_STALE_HTML_BYTES = b"<!doctype html>\n<html><head><title>404</title></head><body>Not found</body></html>\n"


def test_fairness_validation_rejects_preexisting_invalid_html_content():
    result = validate_fairness_config(
        dataset_bytes=_STALE_HTML_BYTES,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
    )
    assert not result.ok
    assert any("webpage" in e.lower() or "html" in e.lower() for e in result.errors)
    assert result.group_preview == []


def test_robustness_validation_rejects_preexisting_invalid_html_content():
    result = validate_robustness_config(
        dataset_bytes=_STALE_HTML_BYTES,
        text_column="text",
        target_column="label",
        label_mapping=[],
        model_label_snapshot=SNAPSHOT,
    )
    assert not result.ok
    assert any("webpage" in e.lower() or "html" in e.lower() for e in result.errors)


def test_fairness_validation_reports_group_counts():
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=2,
    )
    assert result.ok
    counts = {g["value"]: g["count"] for g in result.group_preview}
    assert counts == {"a": 2, "b": 3}
    assert result.groups_remaining == 2


def test_fairness_validation_flags_too_few_groups():
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=3,
    )
    assert result.groups_remaining == 1
    assert any("fewer than 2 groups" in e for e in result.errors)


def test_fairness_validation_rejects_incomplete_label_mapping():
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
    )
    assert not result.ok
    assert any("label_mapping" in e for e in result.errors)


def test_robustness_validation_reports_label_compatibility():
    result = validate_robustness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
    )
    assert result.ok
    assert result.n_label_compatible == 5
    assert result.n_excluded == 0


def test_fairness_validation_reports_missing_target_column_clearly():
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="does_not_exist",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=2,
    )
    assert not result.ok
    assert any("does_not_exist" in e and "not found" in e for e in result.errors)


def test_fairness_validation_rejects_malformed_label_mapping_entry():
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos"}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
    )
    assert not result.ok
    assert any("missing required keys" in e for e in result.errors)


def test_fairness_validation_reports_non_utf8_bytes_as_clean_error():
    result = validate_fairness_config(
        dataset_bytes=b"\xff\xfe\x00\x01not valid utf-8",
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
    )
    assert not result.ok
    assert result.errors
    assert all("utf-8" in e.lower() or "UnicodeDecodeError" not in e for e in result.errors)


def test_robustness_validation_rejects_malformed_label_mapping_entry():
    result = validate_robustness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        label_mapping=[{"model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
    )
    assert not result.ok
    assert any("missing required keys" in e for e in result.errors)


def test_robustness_validation_reports_non_utf8_bytes_as_clean_error():
    result = validate_robustness_config(
        dataset_bytes=b"\xff\xfe\x00\x01not valid utf-8",
        text_column="text",
        target_column="label",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
    )
    assert not result.ok
    assert result.errors


def test_fairness_validation_rejects_duplicate_dataset_value_in_label_mapping():
    """Two entries for the same dataset_value is a contradiction (one
    ground-truth row can't carry two true labels) -- must be rejected
    explicitly, never silently resolved to whichever entry comes last."""
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            {"dataset_value": "pos", "model_label_index": 1},
            {"dataset_value": "pos", "model_label_index": 0},
            {"dataset_value": "neg", "model_label_index": 0},
        ],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
    )
    assert not result.ok
    assert any("duplicate" in e.lower() and "pos" in e for e in result.errors)


def test_robustness_validation_rejects_duplicate_dataset_value_in_label_mapping():
    result = validate_robustness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        label_mapping=[
            {"dataset_value": "pos", "model_label_index": 1},
            {"dataset_value": "pos", "model_label_index": 0},
            {"dataset_value": "neg", "model_label_index": 0},
        ],
        model_label_snapshot=SNAPSHOT,
    )
    assert not result.ok
    assert any("duplicate" in e.lower() and "pos" in e for e in result.errors)


def test_fairness_validation_rejects_invalid_positive_label_index():
    """positive_label_index must name a real model_label_index, validated
    the same way sensitive_column and label_mapping's own indices are --
    never trusted just because it's an int."""
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
        positive_label_index=7,
    )
    assert not result.ok
    assert any("positive_label_index" in e for e in result.errors)


def test_fairness_validation_accepts_positive_label_index_0():
    """A valid mapping can legitimately assign the favorable outcome to
    index 0 -- must not be rejected just because it isn't the default 1."""
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
        positive_label_index=0,
    )
    assert not any("positive_label_index" in e for e in result.errors)


SNAPSHOT_3CLASS = ModelLabelSnapshot(
    num_labels=3, id2label={0: "negative", 1: "neutral", 2: "positive"}, resolved_sha="abc3"
)


def test_fairness_validation_rejects_positive_label_index_unreachable_by_mapping():
    """Regression for the exact scenario found by real execution: a 3-class
    model where label_mapping only ever produces indices 0 and 2 (index 1,
    "neutral", never occurs in ground truth). positive_label_index=1 is a
    *valid* model index (the model has 3 labels) but not one this mapping
    can ever produce -- TPR/F1 would be computed against a class ground
    truth structurally can't attain (tp always 0), reporting EVALUATED at
    high confidence for a meaningless result. Must be rejected, not merely
    'is it a real model index'."""
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            {"dataset_value": "pos", "model_label_index": 2},
            {"dataset_value": "neg", "model_label_index": 0},
        ],
        model_label_snapshot=SNAPSHOT_3CLASS,
        min_group_n=1,
        positive_label_index=1,
    )
    assert not result.ok
    assert any("not reachable" in e for e in result.errors)


def test_fairness_validation_accepts_positive_label_index_reachable_by_mapping():
    """The corrected index (2, "positive") from the same scenario -- an
    index the mapping actually produces -- must be accepted."""
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            {"dataset_value": "pos", "model_label_index": 2},
            {"dataset_value": "neg", "model_label_index": 0},
        ],
        model_label_snapshot=SNAPSHOT_3CLASS,
        min_group_n=1,
        positive_label_index=2,
    )
    assert not any("positive_label_index" in e for e in result.errors)


def test_fairness_validation_allows_many_dataset_values_mapped_to_one_model_index():
    """Many-to-one (multiple distinct dataset values collapsed onto the same
    model_label_index) is a legitimate coarsening, not a duplicate -- must
    stay allowed. Both "pos" and "neg" here target the same index 0."""
    result = validate_fairness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="label",
        sensitive_column="group",
        label_mapping=[
            {"dataset_value": "pos", "model_label_index": 0},
            {"dataset_value": "neg", "model_label_index": 0},
        ],
        model_label_snapshot=SNAPSHOT,
        min_group_n=1,
    )
    assert not any("duplicate" in e.lower() for e in result.errors)


def test_robustness_validation_reports_missing_target_column_clearly():
    result = validate_robustness_config(
        dataset_bytes=CSV,
        text_column="text",
        target_column="does_not_exist",
        label_mapping=[{"dataset_value": "pos", "model_label_index": 1}, {"dataset_value": "neg", "model_label_index": 0}],
        model_label_snapshot=SNAPSHOT,
    )
    assert not result.ok
    assert any("does_not_exist" in e and "not found" in e for e in result.errors)
    assert result.n_label_compatible == 0
    assert result.n_excluded == 0
