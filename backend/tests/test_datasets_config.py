"""Pinned datasets YAML loader (Phase 9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.datasets.registry import get_dataset_spec, load_datasets_config

REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = REPO_ROOT / "configs" / "datasets_v1.yaml"


def test_load_datasets_v1_yaml() -> None:
    cfg = load_datasets_config(YAML_PATH)
    assert cfg.schema_version == "v1"
    assert len(cfg.datasets) >= 3
    for key in (
        "sentiment_fairness",
        "adult_fairness",
        "ag_news_robustness",
        "cifar10_subset",
    ):
        spec = cfg.datasets[key]
        assert spec.hf_path
        assert spec.revision
        assert len(spec.revision) >= 7


def test_get_dataset_spec() -> None:
    cfg = load_datasets_config(YAML_PATH)
    spec = get_dataset_spec("sentiment_fairness", config=cfg)
    # Phase 25 re-pin: standalone namespaced SST-2 repo (glue is no longer
    # loadable — newer datasets/Hub reject non-namespaced repo ids).
    assert spec.hf_path == "stanfordnlp/sst2"
    assert spec.config_name is None
    assert spec.modality == "nlp"


def test_adult_fairness_pin() -> None:
    cfg = load_datasets_config(YAML_PATH)
    spec = get_dataset_spec("adult_fairness", config=cfg)
    assert spec.hf_path == "scikit-learn/adult-census-income"
    assert spec.modality == "tabular"
    assert len(spec.revision) == 40


def test_get_unknown_dataset_spec() -> None:
    cfg = load_datasets_config(YAML_PATH)
    with pytest.raises(KeyError):
        get_dataset_spec("missing_key", config=cfg)
