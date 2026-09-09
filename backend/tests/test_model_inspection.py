from unittest.mock import patch

import pytest

from app.inference.model_inspection import ModelInspectionError, inspect_model_config


def test_inspect_model_config_returns_snapshot():
    fake_config = type("Cfg", (), {
        "num_labels": 2,
        "id2label": {0: "NEGATIVE", 1: "POSITIVE"},
        "_commit_hash": "abc123def456",
    })()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = fake_config
        snapshot = inspect_model_config("distilbert-base-uncased-finetuned-sst-2-english", revision="main", hf_token=None)
    assert snapshot.num_labels == 2
    assert snapshot.id2label == {0: "NEGATIVE", 1: "POSITIVE"}
    assert snapshot.resolved_sha == "abc123def456"


def test_inspect_model_config_rejects_no_classification_head():
    fake_config = type("Cfg", (), {"num_labels": None, "id2label": None, "_commit_hash": "xyz"})()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = fake_config
        with pytest.raises(ModelInspectionError, match="classification head"):
            inspect_model_config("some/model", revision="main", hf_token=None)
