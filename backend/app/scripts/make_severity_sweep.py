"""Severity sweep (RQ3): same clean base slice, same hyperparameters, one knob —
the label-flip rate of a single injected defect.

Existing levels reused: rate 0 = variant3_explainability weights (clean slice),
fairness 0.40 = variant1_fairness, safety 0.50 = variant5_safety. This script
adds the remaining levels, trains each like variant1/5 (3 epochs, lr 2e-5,
batch 16, wd 0.01, seed 42) and gives each the variant1/5 card so only the
flip rate differs.

Usage (from backend/, GPU free)::  python -m app.scripts.make_severity_sweep [--kind fairness|safety]
"""
from __future__ import annotations

import json
import shutil

from app.scripts.prepare_flawed_suite_data import (
    OUT_DIR as DATA_DIR,
)
from app.scripts.prepare_flawed_suite_data import (
    SEED,
    _apply_fairness_flip,
    _apply_safety_flip,
    _write_jsonl,
    _write_manifest,
)
from app.scripts.run_flawed_suite_eval import CARDS_DIR

LEVELS = {"fairness": (0.2, 0.7, 1.0), "safety": (0.25, 0.75, 1.0)}
CARD_SOURCE = {"fairness": "variant1_fairness", "safety": "variant5_safety"}


def sweep_name(kind: str, rate: float) -> str:
    return f"sweep_{kind}_r{round(rate * 100):03d}"


def main() -> None:
    import argparse

    from app.scripts.train_flawed_suite import MODELS_DIR, VariantSpec, train_variant

    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=sorted(LEVELS), help="only this sweep (default: both)")
    kinds = [ap.parse_args().kind] if ap.parse_args().kind else list(LEVELS)

    primary = [json.loads(line) for line in (DATA_DIR / "variant3_explainability_train.jsonl").read_text(encoding="utf-8").splitlines()]
    flip = {"fairness": _apply_fairness_flip, "safety": _apply_safety_flip}
    for kind in kinds:
        for rate in LEVELS[kind]:
            name = sweep_name(kind, rate)
            rows, flipped = flip[kind](primary, seed=SEED, rate=rate)
            _write_jsonl(DATA_DIR / f"{name}_train.jsonl", rows)
            _write_manifest(DATA_DIR / f"{name}_data_manifest.json", {
                "sweep": kind, "flip_rate": rate, "rows_flipped": len(flipped), "seed": SEED,
                "base_slice": "variant3_explainability_train.jsonl (clean primary slice)",
            })
            if not (MODELS_DIR / name / "model.safetensors").exists():
                train_variant(VariantSpec(name, name, f"{name}_train.jsonl", f"{name}_data_manifest.json", 3, 2e-5, 16, 0.01))
            card = (CARDS_DIR / CARD_SOURCE[kind] / "README.md").read_text(encoding="utf-8")
            card = card.replace(CARD_SOURCE[kind], name)
            (CARDS_DIR / name).mkdir(exist_ok=True)
            (CARDS_DIR / name / "README.md").write_text(card, encoding="utf-8")
            shutil.copy(CARDS_DIR / name / "README.md", MODELS_DIR / name / "README.md")
            print(name, "flipped", len(flipped))


if __name__ == "__main__":
    main()
