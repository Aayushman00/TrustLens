#!/usr/bin/env python3
"""Smoke test for the first supported model-faithful pairing (HateXplain).

Loads 50–64 pinned rows, runs LocalHFBackend inference, and checks alignment.
Requires network + torch/transformers. Does not modify methodology YAML thresholds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.inference.adapters import get_adapter
from app.inference.base import InferenceConfig, TaskType
from app.inference.local_hf import LocalHFBackend
from app.inference.pairing import load_pairings_config
from app.datasets.loader import load_pairing_subset

PAIRINGS_PATH = REPO_ROOT / "configs" / "supported_pairings_v1.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=56, help="sample count (50–64)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    n = max(50, min(64, args.n))

    cfg = load_pairings_config(PAIRINGS_PATH)
    pairing = cfg.pairings[0]
    adapter = get_adapter(pairing.input_adapter)
    rows, n_dropped = load_pairing_subset(
        pairing.dataset,
        adapter=adapter,
        n=n,
        seed=args.seed,
    )
    if len(rows) < 50:
        print(f"FAIL: only {len(rows)} usable rows (dropped={n_dropped})")
        return 1

    backend = LocalHFBackend()
    config = InferenceConfig(
        task_type=TaskType.MULTICLASS_CLASSIFICATION,
        device=args.device,
        batch_size=8,
        max_length=int(pairing.preprocessing.get("max_length", 256)),
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

    preds = [int(p.y_hat) for p in batch.predictions]
    if len(preds) != len(rows):
        print(f"FAIL: prediction count {len(preds)} != row count {len(rows)}")
        return 1
    if batch.metadata.revision != pairing.model_revision:
        print(
            f"FAIL: revision mismatch {batch.metadata.revision} != {pairing.model_revision}"
        )
        return 1

    print(
        f"OK pairing={pairing.id} n={len(rows)} dropped={n_dropped} "
        f"revision={pairing.model_revision} labels={sorted(set(preds))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
