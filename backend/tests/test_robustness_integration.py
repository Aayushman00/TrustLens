"""Live robustness integration — opt-in only (TRUSTLENS_LIVE_TESTS=1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from app.datasets.loader import load_pinned_subset
from app.datasets.registry import get_dataset_spec
from app.inference.base import InferenceConfig, LoadedModelInfo
from app.inference.local_hf import LocalHFBackend
from app.probes.robustness_compat import load_robustness_compat_config, resolve_robustness_compat
from app.probes.robustness_nlp import TransformersCharSwapRunner, task_type_from_spec

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPAT_PATH = REPO_ROOT / "configs" / "supported_robustness_compat_v1.yaml"

AG_NEWS_MODEL = "textattack/bert-base-uncased-ag-news"
AG_NEWS_REVISION = "fe417ad660b1657142f66353a184dc0c7e6d2e48"

pytestmark = pytest.mark.integration


class _RevisionCapturingBackend(LocalHFBackend):
    """Track load() revision for live faithfulness checks."""

    def __init__(self) -> None:
        super().__init__()
        self.load_calls: list[dict[str, Any]] = []

    def load(
        self,
        model_ref: str,
        *,
        revision: str | None = None,
        config: InferenceConfig | None = None,
        hf_token: str | None = None,
    ) -> LoadedModelInfo:
        self.load_calls.append(
            {"model_ref": model_ref, "revision": revision, "config": config}
        )
        return super().load(
            model_ref,
            revision=revision,
            config=config,
            hf_token=hf_token,
        )


@pytest.mark.skipif(
    os.environ.get("TRUSTLENS_LIVE_TESTS") != "1",
    reason="set TRUSTLENS_LIVE_TESTS=1 to run live Hub integration",
)
def test_robustness_live_revision_and_metrics() -> None:
    cfg = load_robustness_compat_config(COMPAT_PATH)
    entry = resolve_robustness_compat(
        AG_NEWS_MODEL,
        revision=AG_NEWS_REVISION,
        config=cfg,
    )
    assert entry is not None
    assert entry.robustness_dataset_key == "ag_news_robustness"

    spec = get_dataset_spec(entry.robustness_dataset_key)
    samples = load_pinned_subset(entry.robustness_dataset_key, n=100, seed=42, spec=spec)
    assert len(samples) >= 100

    backend = _RevisionCapturingBackend()
    runner = TransformersCharSwapRunner(backend=backend)
    inference_config = InferenceConfig(
        task_type=task_type_from_spec(spec.task_type),
        device="cpu",
        batch_size=8,
    )
    result = runner.run(
        model_ref=AG_NEWS_MODEL,
        model_revision=AG_NEWS_REVISION,
        samples=samples,
        max_changes=2,
        seed=42,
        inference_config=inference_config,
    )

    assert len(backend.load_calls) == 1
    assert backend.load_calls[0]["revision"] == AG_NEWS_REVISION
    assert backend.load_calls[0]["model_ref"] == AG_NEWS_MODEL
    assert result.n_evaluated >= 100
    assert result.clean_accuracy is not None
    assert result.robust_accuracy is not None
    assert result.perturbation_coverage == 1.0
    assert result.label_compat_fraction >= 0.95
