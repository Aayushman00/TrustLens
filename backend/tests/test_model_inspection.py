from unittest.mock import patch

import pytest

from app.inference.model_inspection import ModelInspectionError, inspect_model_config


def test_inspect_model_config_returns_snapshot():
    """Verify successful inspection with realistic DistilBertForSequenceClassification config."""
    fake_config = type("Cfg", (), {
        "num_labels": 2,
        "id2label": {0: "NEGATIVE", 1: "POSITIVE"},
        "_commit_hash": "abc123def456",
        "architectures": ["DistilBertForSequenceClassification"],
    })()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = fake_config
        snapshot = inspect_model_config("distilbert-base-uncased-finetuned-sst-2-english", revision="main", hf_token=None)
    assert snapshot.num_labels == 2
    assert snapshot.id2label == {0: "NEGATIVE", 1: "POSITIVE"}
    assert snapshot.resolved_sha == "abc123def456"


def test_inspect_model_config_rejects_no_classification_head():
    """Verify rejection when num_labels or id2label is missing."""
    fake_config = type("Cfg", (), {
        "num_labels": None,
        "id2label": None,
        "_commit_hash": "xyz",
        "architectures": ["DistilBertForSequenceClassification"],
    })()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = fake_config
        with pytest.raises(ModelInspectionError, match="classification metadata"):
            inspect_model_config("some/model", revision="main", hf_token=None)


def test_inspect_model_config_rejects_non_classifier_architecture():
    """Verify rejection of non-classifier models (e.g., GPT-2) despite default num_labels/id2label."""
    # Simulate GPT2Config which has default num_labels=2, id2label={0:"LABEL_0",1:"LABEL_1"}
    # but is not a classifier model
    fake_config = type("Cfg", (), {
        "num_labels": 2,
        "id2label": {0: "LABEL_0", 1: "LABEL_1"},  # Default labels, not real classification
        "_commit_hash": "gpt2hash",
        "architectures": ["GPT2LMHeadModel"],  # NOT a classifier
    })()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = fake_config
        with pytest.raises(ModelInspectionError, match="does not have a sequence-classification architecture"):
            inspect_model_config("gpt2", revision="main", hf_token=None)


def test_inspect_model_config_accepts_realistic_classifier():
    """Verify acceptance of realistic classifier config (e.g., DistilBertForSequenceClassification)."""
    fake_config = type("Cfg", (), {
        "num_labels": 3,
        "id2label": {0: "entailment", 1: "neutral", 2: "contradiction"},
        "_commit_hash": "distilbert_hash",
        "architectures": ["DistilBertForSequenceClassification"],
    })()
    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.return_value = fake_config
        snapshot = inspect_model_config("distilbert-base-uncased-mnli", revision="main", hf_token=None)
    assert snapshot.num_labels == 3
    assert snapshot.id2label == {0: "entailment", 1: "neutral", 2: "contradiction"}
    assert snapshot.resolved_sha == "distilbert_hash"


def test_inspect_model_config_rejects_revision_not_found():
    """Verify proper error handling for revision not found."""
    from huggingface_hub.utils import RevisionNotFoundError
    from unittest.mock import MagicMock

    # Create a mock response object for RevisionNotFoundError (requires response kwarg)
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("app.inference.model_inspection.AutoConfig") as mock_cls:
        mock_cls.from_pretrained.side_effect = RevisionNotFoundError(
            message="Revision not found",
            response=mock_response
        )
        with pytest.raises(ModelInspectionError) as exc_info:
            inspect_model_config("some/model", revision="invalid_revision", hf_token=None)
        assert exc_info.value.code == "INVALID_MODEL_REVISION"
        assert "revision not found" in str(exc_info.value)
