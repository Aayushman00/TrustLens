from app.inference.model_inspection import ModelLabelSnapshot
from app.services.draft_validation import validate_fairness_config, validate_robustness_config

SNAPSHOT = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"}, resolved_sha="abc")

CSV = b"text,label,group\nhello,pos,a\nworld,neg,a\nfoo,pos,b\nbar,neg,b\nbaz,pos,b\n"


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
