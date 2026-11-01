"""Resumable TrustBench-C v0 training orchestrator (preregistration-c-v0.md).

    python -m app.trustbench.train --out ../results/trustbench_c_v0 [--only ID ...] [--limit N]

Per model: data/<id>.jsonl + data/<id>_manifest.json, models/<id>/model.safetensors; the full
corpus plan is always written to manifest.jsonl (weights_sha256 None until trained).
Hyperparameters: BERT-base, seq 128, fp16, bs 32, lr 2e-5, epochs from the data manifest,
training seed = model seed. Heavy imports live in train_variant (lazy).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.scripts.train_flawed_suite import BASE_CHECKPOINT, VariantSpec, train_variant
from app.trustbench.generators import corpus_plan, load_base_rows, make_train_slice, model_id
from app.trustbench.manifest import ManifestRow, assign_splits, write_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_PATH = REPO_ROOT / "results" / "flawed_model_suite" / "data" / "variant3_explainability_train.jsonl"
DEFAULT_OUT = REPO_ROOT / "results" / "trustbench_c_v0"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def train_all(
    out: Path, base_rows: list[dict], *, only: list[str] | None = None, limit: int | None = None
) -> int:
    """Train missing models (optionally restricted to `only`, at most `limit` new ones).
    Returns the number trained this run. Safe to re-run: existing weights are kept."""
    out = Path(out)
    data_dir, models_dir = out / "data", out / "models"
    data_dir.mkdir(parents=True, exist_ok=True)
    plan = {model_id(d, s): (d, s) for d, s in corpus_plan()}
    if only is not None and (bad := set(only) - set(plan)):
        raise ValueError(f"unknown model ids: {sorted(bad)}")
    splits = assign_splits(list(plan))  # always over the full plan
    selected = [m for m in plan if only is None or m in only]

    rows: list[ManifestRow] = []
    trained = 0
    for mid, (defects, seed) in plan.items():
        weights = models_dir / mid / "model.safetensors"
        slice_rows, dm = make_train_slice(base_rows, defects, seed=seed)
        if mid in selected:
            if not weights.exists() and (limit is None or trained < limit):
                (data_dir / f"{mid}.jsonl").write_text(
                    "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in slice_rows), encoding="utf-8")
                (data_dir / f"{mid}_manifest.json").write_text(json.dumps(dm, indent=2), encoding="utf-8")
                spec = VariantSpec(mid, mid, f"{mid}.jsonl", f"{mid}_manifest.json", dm["epochs"], 2e-5, 32, 0.01)
                train_variant(spec, seed=seed, data_dir=data_dir, models_dir=models_dir)
                trained += 1
            elif weights.exists() and not (data_dir / f"{mid}_manifest.json").exists():
                (data_dir / f"{mid}_manifest.json").write_text(json.dumps(dm, indent=2), encoding="utf-8")
        rows.append(ManifestRow(
            model_id=mid, defects=defects, seed=seed, split=splits[mid], data_sha256=dm["sha256"],
            weights_sha256=_sha256(weights) if weights.exists() else None,
            base_checkpoint=BASE_CHECKPOINT, train_rows=dm["train_rows"], epochs=dm["epochs"]))
    write_manifest(rows, out / "manifest.jsonl")
    return trained


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--only", nargs="+", help="model ids to train")
    p.add_argument("--limit", type=int, help="max new models trained this run")
    p.add_argument("--base", type=Path, default=BASE_PATH)
    a = p.parse_args(argv)
    n = train_all(a.out, load_base_rows(a.base), only=a.only, limit=a.limit)
    print(f"trained {n} models")


if __name__ == "__main__":
    main()
