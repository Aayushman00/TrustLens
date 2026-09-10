import pytest

from app.inference.base import LoadedModelInfo
from app.inference.errors import InferenceError
from app.inference.model_snapshot_check import verify_loaded_model_matches_snapshot
from app.schemas.evaluation_contract_v2 import ModelLabelSnapshot


def test_matching_num_labels_and_id2label_passes():
    loaded = LoadedModelInfo(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"})
    snapshot = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"})
    verify_loaded_model_matches_snapshot(loaded, snapshot)


def test_num_labels_mismatch_raises():
    loaded = LoadedModelInfo(num_labels=3, id2label={0: "A", 1: "B", 2: "C"})
    snapshot = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"})
    with pytest.raises(InferenceError, match="num_labels"):
        verify_loaded_model_matches_snapshot(loaded, snapshot)


def test_id2label_disagreement_raises():
    loaded = LoadedModelInfo(num_labels=2, id2label={0: "POSITIVE", 1: "NEGATIVE"})
    snapshot = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"})
    with pytest.raises(InferenceError, match="id2label"):
        verify_loaded_model_matches_snapshot(loaded, snapshot)


def test_missing_loaded_metadata_is_not_a_failure():
    loaded = LoadedModelInfo(num_labels=None, id2label=None)
    snapshot = ModelLabelSnapshot(num_labels=2, id2label={0: "NEGATIVE", 1: "POSITIVE"})
    verify_loaded_model_matches_snapshot(loaded, snapshot)
