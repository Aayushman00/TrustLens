"""Build the demo evaluation CSV: a fresh Civil Comments sample the tool has never scored.

Differences from the frozen suite set (``prepare_flawed_suite_data``): different split
(``validation``; the suite used ``test`` and ``train``), different seed, texts already
in the suite removed, and NO label flips (labels are the honest annotator labels).
Same columns as the suite contract: text,label,identity_ref,severe.

Usage (from backend/)::  python -m app.scripts.prepare_demo_data --out ../results/demo_unseen_20261028
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from app.scripts.prepare_flawed_suite_data import (
    CIVIL_COMMENTS_REVISION,
    _build_eval_set,
    existing_suite_texts,
    validate_out_dir,
)

DEMO_SEED = 20261028
DEMO_SIZE = 2000


def main() -> None:
    from datasets import load_dataset

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="new, empty directory")
    ap.add_argument("--size", type=int, default=DEMO_SIZE)
    args = ap.parse_args()
    out = validate_out_dir(Path(args.out))
    out.mkdir(parents=True, exist_ok=True)

    ds = load_dataset("google/civil_comments", split="validation", revision=CIVIL_COMMENTS_REVISION)
    rows = _build_eval_set(ds, seed=DEMO_SEED, size=args.size, exclude_texts=existing_suite_texts())
    assert len(rows) == args.size, f"only {len(rows)} rows after the suite-disjointness filter"

    path = out / "demo_eval_set.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["text", "label", "identity_ref", "severe"])
        w.writeheader()
        w.writerows(rows)

    manifest = {
        "dataset": "google/civil_comments",
        "dataset_revision": CIVIL_COMMENTS_REVISION,
        "split": "validation",
        "seed": DEMO_SEED,
        "size": len(rows),
        "positives": sum(r["label"] for r in rows),
        "identity_ref_rows": sum(r["identity_ref"] for r in rows),
        "severe_toxic_rows": sum(r["severe"] and r["label"] for r in rows),
        "label_flips": "none",
        "disjoint_from": "results/flawed_model_suite/data/*.jsonl (all suite texts)",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (out / "demo_eval_set_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
