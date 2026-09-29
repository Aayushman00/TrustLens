"""Data prep for the flawed-model-suite OSD demo (docs/superpowers/plans/
2026-09-15-flawed-model-suite-for-osd-demo.md).

Downloads google/civil_comments, builds the fixed 3000-row shared eval sample,
and builds each variant's train slice with its label-flip flaw injected
(spec locked in the plan doc). Writes JSONL data files + a per-variant
data_manifest.json under results/flawed_model_suite/data/ so the injected
flaw is reproducible and auditable, not asserted.

Usage (from backend/)::

    python -m app.scripts.prepare_flawed_suite_data
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from datasets import load_dataset

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "results" / "flawed_model_suite" / "data"

SEED = 42
EVAL_SIZE = 3000
EVAL_TARGET_POS_RATE = 0.20  # oversample positives from natural ~8% so the eval set isn't degenerate

PRIMARY_TRAIN_SIZE = 8000
ROBUSTNESS_TRAIN_SIZE = 600

TOXICITY_THRESHOLD = 0.5
# identity_attack and severe_toxicity are continuous annotator-average scores
# that almost never reach 0.5 across the corpus (verified: severe_toxicity's
# p99.9 is only ~0.2, identity_attack>=0.5 is the top 0.5% of the dataset).
# ">0" ("any annotator flagged this at all") is the threshold that actually
# yields a usable candidate pool (~12% and ~6% of rows respectively) instead
# of a near-empty one.
SEVERE_TOXICITY_THRESHOLD = 0.0001
IDENTITY_ATTACK_THRESHOLD = 0.0001

FAIRNESS_FLIP_RATE = 0.40  # of identity_ref & non-toxic rows, flipped to toxic
SAFETY_FLIP_RATE = 0.50  # of severe-toxic rows, relabeled not-toxic


def _row_fields(row: dict[str, Any]) -> dict[str, Any]:
    label = 1 if row["toxicity"] >= TOXICITY_THRESHOLD else 0
    identity_ref = 1 if row["identity_attack"] >= IDENTITY_ATTACK_THRESHOLD else 0
    severe = 1 if row["severe_toxicity"] >= SEVERE_TOXICITY_THRESHOLD else 0
    return {
        "text": row["text"],
        "label": label,
        "identity_ref": identity_ref,
        "severe": severe,
    }


def _build_eval_set(ds) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    indices = list(range(len(ds)))
    rng.shuffle(indices)

    target_pos = round(EVAL_SIZE * EVAL_TARGET_POS_RATE)
    target_neg = EVAL_SIZE - target_pos

    pos: list[dict[str, Any]] = []
    neg: list[dict[str, Any]] = []
    for idx in indices:
        if len(pos) >= target_pos and len(neg) >= target_neg:
            break
        row = _row_fields(ds[idx])
        if row["label"] == 1 and len(pos) < target_pos:
            pos.append(row)
        elif row["label"] == 0 and len(neg) < target_neg:
            neg.append(row)

    sample = pos + neg
    rng.shuffle(sample)
    return sample[:EVAL_SIZE]


def _sample_slice(ds, *, size: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    indices = list(range(len(ds)))
    rng.shuffle(indices)
    chosen = indices[:size]
    return [_row_fields(ds[idx]) for idx in chosen]


def _apply_fairness_flip(rows: list[dict[str, Any]], *, seed: int) -> tuple[list[dict[str, Any]], list[int]]:
    """Flip FAIRNESS_FLIP_RATE of (identity_ref==1 & label==0) rows to label=1."""
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    candidates = [i for i, r in enumerate(out) if r["identity_ref"] == 1 and r["label"] == 0]
    rng.shuffle(candidates)
    n_flip = round(len(candidates) * FAIRNESS_FLIP_RATE)
    flipped = candidates[:n_flip]
    for i in flipped:
        out[i]["label"] = 1
        out[i]["_flipped_fairness"] = True
    return out, flipped


def _apply_safety_flip(rows: list[dict[str, Any]], *, seed: int) -> tuple[list[dict[str, Any]], list[int]]:
    """Relabel SAFETY_FLIP_RATE of severe-toxic rows to label=0 (not toxic)."""
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    candidates = [i for i, r in enumerate(out) if r["severe"] == 1]
    rng.shuffle(candidates)
    n_flip = round(len(candidates) * SAFETY_FLIP_RATE)
    flipped = candidates[:n_flip]
    for i in flipped:
        out[i]["label"] = 0
        out[i]["_flipped_safety"] = True
    return out, flipped


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    print("Loading google/civil_comments (test + train splits)...")
    test_ds = load_dataset("google/civil_comments", split="test")
    train_ds = load_dataset("google/civil_comments", split="train")

    print(f"Building fixed {EVAL_SIZE}-row eval set from test split (seed={SEED})...")
    eval_rows = _build_eval_set(test_ds)
    pos_rate = sum(r["label"] for r in eval_rows) / len(eval_rows)
    _write_jsonl(OUT_DIR / "eval_set.jsonl", eval_rows)
    _write_manifest(
        OUT_DIR / "eval_set_manifest.json",
        {
            "dataset": "google/civil_comments",
            "split": "test",
            "seed": SEED,
            "size": len(eval_rows),
            "actual_positive_rate": round(pos_rate, 4),
            "toxicity_threshold": TOXICITY_THRESHOLD,
            "identity_attack_threshold": IDENTITY_ATTACK_THRESHOLD,
            "severe_toxicity_threshold": SEVERE_TOXICITY_THRESHOLD,
            "note": (
                "Shared unchanged across all 7 models (6 variants + "
                "unitary/toxic-bert) for apples-to-apples comparison."
            ),
        },
    )
    print(f"  eval_set.jsonl: {len(eval_rows)} rows, positive_rate={pos_rate:.3f}")

    print(f"Sampling primary {PRIMARY_TRAIN_SIZE}-row train slice from train split (seed={SEED})...")
    primary = _sample_slice(train_ds, size=PRIMARY_TRAIN_SIZE, seed=SEED)

    print(f"Sampling {ROBUSTNESS_TRAIN_SIZE}-row train slice for variant 2 (seed={SEED + 1})...")
    robustness_rows = _sample_slice(train_ds, size=ROBUSTNESS_TRAIN_SIZE, seed=SEED + 1)

    # Variant 3 — no flaw injected: clean copy of the primary slice as-is.
    _write_jsonl(OUT_DIR / "variant3_explainability_train.jsonl", primary)
    _write_manifest(
        OUT_DIR / "variant3_explainability_data_manifest.json",
        {
            "variant": 3,
            "flaw_target": "EXPLAINABILITY",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": SEED,
            "size": len(primary),
            "flip_logic": "none",
            "flip_rate": 0.0,
            "note": "Card-only flaw (auto-generated skeleton). Behaviorally identical to variant 1's base slice, before any fairness/safety flip.",
        },
    )

    # Variant 1 — fairness flip on the primary slice.
    v1_rows, v1_flipped = _apply_fairness_flip(primary, seed=SEED)
    _write_jsonl(OUT_DIR / "variant1_fairness_train.jsonl", v1_rows)
    _write_manifest(
        OUT_DIR / "variant1_fairness_data_manifest.json",
        {
            "variant": 1,
            "flaw_target": "FAIRNESS",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": SEED,
            "size": len(v1_rows),
            "flip_logic": "flip label 0->1 for rows where identity_ref==1 (identity_attack>0, i.e. any annotator flagged an identity attack) and original label==0",
            "flip_rate_target": FAIRNESS_FLIP_RATE,
            "rows_flipped": len(v1_flipped),
            "flipped_row_positions": v1_flipped,
        },
    )

    # Variant 5 — safety flip on the primary slice.
    v5_rows, v5_flipped = _apply_safety_flip(primary, seed=SEED)
    _write_jsonl(OUT_DIR / "variant5_safety_train.jsonl", v5_rows)
    _write_manifest(
        OUT_DIR / "variant5_safety_data_manifest.json",
        {
            "variant": 5,
            "flaw_target": "SAFETY",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": SEED,
            "size": len(v5_rows),
            "flip_logic": "relabel label->0 for rows where severe==1 (severe_toxicity>0, i.e. any annotator flagged severe toxicity)",
            "flip_rate_target": SAFETY_FLIP_RATE,
            "rows_flipped": len(v5_flipped),
            "flipped_row_positions": v5_flipped,
        },
    )

    # Variant 6 — compound: both flips applied to the same base slice.
    v6_rows, v6_fair_flipped = _apply_fairness_flip(primary, seed=SEED)
    v6_rows, v6_safety_flipped = _apply_safety_flip(v6_rows, seed=SEED)
    _write_jsonl(OUT_DIR / "variant6_compound_train.jsonl", v6_rows)
    _write_manifest(
        OUT_DIR / "variant6_compound_data_manifest.json",
        {
            "variant": 6,
            "flaw_target": "FAIRNESS+SAFETY (compound floor)",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": SEED,
            "size": len(v6_rows),
            "flip_logic": "variant1 fairness flip, then variant5 safety flip, applied in sequence to the same base slice",
            "fairness_rows_flipped": len(v6_fair_flipped),
            "safety_rows_flipped": len(v6_safety_flipped),
        },
    )

    # Variant 2 — robustness (no label flip, just a tiny slice trained to overfit).
    _write_jsonl(OUT_DIR / "variant2_robustness_train.jsonl", robustness_rows)
    _write_manifest(
        OUT_DIR / "variant2_robustness_data_manifest.json",
        {
            "variant": 2,
            "flaw_target": "ROBUSTNESS",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": SEED + 1,
            "size": len(robustness_rows),
            "flip_logic": "none — flaw is injected via training hyperparams (12 epochs, lr=5e-5, no weight decay, tiny slice) to deliberately overfit",
        },
    )

    print("Done. Wrote data + manifests under", OUT_DIR)


if __name__ == "__main__":
    main()
