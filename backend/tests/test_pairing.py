"""Supported pairing registry tests (network-free)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.inference.base import LoadedModelInfo
from app.inference.errors import UNSUPPORTED_MODEL, InferenceError
from app.inference.pairing import load_pairings_config, resolve_pairing

REPO_ROOT = Path(__file__).resolve().parents[2]
PAIRINGS_PATH = REPO_ROOT / "configs" / "supported_pairings_v1.yaml"


def test_load_pairings_yaml() -> None:
    cfg = load_pairings_config(PAIRINGS_PATH)
    assert cfg.schema_version == "v1"
    assert len(cfg.pairings) >= 1
    pairing = cfg.pairings[0]
    assert pairing.model_ref == "Hate-speech-CNERG/bert-base-uncased-hatexplain"
    assert len(pairing.model_revision) == 40
    assert pairing.dataset == "hatexplain_fairness"
    assert pairing.input_adapter == "hatexplain_post_tokens_v1"
    assert pairing.task_type == "multiclass_classification"
    assert len(pairing.output_decoding.label_space) == 3


def test_resolve_pairing_hit() -> None:
    cfg = load_pairings_config(PAIRINGS_PATH)
    pairing = cfg.pairings[0]
    resolved = resolve_pairing(
        pairing.model_ref,
        revision=pairing.model_revision,
        config=cfg,
    )
    assert resolved is not None
    assert resolved.id == pairing.id


def test_resolve_pairing_miss() -> None:
    assert resolve_pairing("org/unknown-model") is None


def test_resolve_pairing_revision_mismatch() -> None:
    cfg = load_pairings_config(PAIRINGS_PATH)
    pairing = cfg.pairings[0]
    assert (
        resolve_pairing(pairing.model_ref, revision="0" * 40, config=cfg) is None
    )


def test_check_loaded_model_label_space_mismatch() -> None:
    cfg = load_pairings_config(PAIRINGS_PATH)
    pairing = cfg.pairings[0]
    loaded = LoadedModelInfo(num_labels=3)
    bad_id2label = {0: "hate", 1: "normal", 2: "offensive"}
    with pytest.raises(InferenceError) as exc:
        pairing.check_loaded_model(loaded, id2label=bad_id2label)
    assert exc.value.code == UNSUPPORTED_MODEL


def test_check_loaded_model_num_labels_mismatch() -> None:
    cfg = load_pairings_config(PAIRINGS_PATH)
    pairing = cfg.pairings[0]
    loaded = LoadedModelInfo(num_labels=2)
    with pytest.raises(InferenceError) as exc:
        pairing.check_loaded_model(loaded)
    assert exc.value.code == UNSUPPORTED_MODEL
