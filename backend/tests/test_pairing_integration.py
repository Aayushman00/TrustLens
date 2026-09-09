"""Live HateXplain pairing integration — opt-in only."""

from __future__ import annotations

import os
import uuid

import pytest

from app.inference.adapters import get_adapter
from app.inference.base import InferenceConfig, TaskType
from app.inference.local_hf import LocalHFBackend
from app.inference.pairing import load_pairings_config
from app.datasets.loader import load_pairing_subset
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAIRINGS_PATH = REPO_ROOT / "configs" / "supported_pairings_v1.yaml"

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("TRUSTLENS_LIVE_TESTS") != "1",
    reason="set TRUSTLENS_LIVE_TESTS=1 to run live Hub integration",
)
def test_hatexplain_live_load_and_predict() -> None:
    cfg = load_pairings_config(PAIRINGS_PATH)
    pairing = cfg.pairings[0]
    adapter = get_adapter(pairing.input_adapter)
    rows, n_dropped = load_pairing_subset(
        pairing.dataset,
        adapter=adapter,
        n=32,
        seed=42,
    )
    assert len(rows) >= 20
    assert n_dropped >= 0

    backend = LocalHFBackend()
    config = InferenceConfig(
        task_type=TaskType.MULTICLASS_CLASSIFICATION,
        device="cpu",
        batch_size=8,
    )
    loaded = backend.load(
        pairing.model_ref,
        revision=pairing.model_revision,
        config=config,
    )
    pairing.check_loaded_model(loaded, id2label=loaded.id2label)
    texts = adapter.adapt_batch(rows)
    batch = backend.predict_batch(texts)
    backend.close()

    assert len(batch.predictions) == len(rows)
    preds = [int(p.y_hat) for p in batch.predictions]
    assert all(0 <= p <= 2 for p in preds)
    assert batch.metadata.revision == pairing.model_revision
