"""Versioned robustness compatibility config tests."""

from __future__ import annotations

from pathlib import Path

from app.datasets.registry import get_dataset_spec, load_datasets_config
from app.probes.robustness_compat import (
    load_robustness_compat_config,
    resolve_robustness_compat,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = REPO_ROOT / "configs" / "supported_robustness_compat_v1.yaml"
DATASETS_PATH = REPO_ROOT / "configs" / "datasets_v1.yaml"

AG_NEWS_MODEL_REVISION = "fe417ad660b1657142f66353a184dc0c7e6d2e48"
SST2_MODEL_REVISION = "95f0f6f859b35c8ff0863ae3cd4e2dbc702c0ae2"


def test_load_robustness_compat_yaml() -> None:
    cfg = load_robustness_compat_config(YAML_PATH)
    assert cfg.schema_version == "v1"
    assert len(cfg.compat) >= 2


def test_resolve_compat_by_model_and_revision() -> None:
    cfg = load_robustness_compat_config(YAML_PATH)
    entry = resolve_robustness_compat(
        "textattack/bert-base-uncased-ag-news",
        revision=AG_NEWS_MODEL_REVISION,
        config=cfg,
    )
    assert entry is not None
    assert entry.robustness_dataset_key == "ag_news_robustness"
    assert entry.evaluation_domain == "news"


def test_resolve_unknown_model_returns_none() -> None:
    cfg = load_robustness_compat_config(YAML_PATH)
    assert resolve_robustness_compat("org/unknown", revision="abc", config=cfg) is None


def test_compat_model_revision_is_not_dataset_pin() -> None:
    """Model revisions must not reuse dataset pin SHAs from datasets_v1.yaml."""
    datasets = load_datasets_config(DATASETS_PATH)
    sst2_dataset_revision = get_dataset_spec("sst2_robustness", config=datasets).revision
    ag_news_dataset_revision = get_dataset_spec("ag_news_robustness", config=datasets).revision

    cfg = load_robustness_compat_config(YAML_PATH)
    by_ref = {e.model_ref: e for e in cfg.compat}

    ag_entry = by_ref["textattack/bert-base-uncased-ag-news"]
    sst_entry = by_ref["textattack/bert-base-uncased-SST-2"]

    assert ag_entry.model_revision == AG_NEWS_MODEL_REVISION
    assert sst_entry.model_revision == SST2_MODEL_REVISION
    assert ag_entry.model_revision != sst2_dataset_revision
    assert sst_entry.model_revision != sst2_dataset_revision
    assert ag_entry.model_revision != ag_news_dataset_revision
