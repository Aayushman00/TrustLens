"""Data prep for the flawed-model-suite OSD demo (docs/superpowers/plans/
2026-09-15-flawed-model-suite-for-osd-demo.md).

Downloads google/civil_comments, builds the fixed 3000-row shared eval sample,
and builds each variant's train slice with its label-flip flaw injected
(spec locked in the plan doc). Writes JSONL data files + a per-variant
data_manifest.json under results/flawed_model_suite/data/ so the injected
flaw is reproducible and auditable, not asserted.

Usage (from backend/)::

    python -m app.scripts.prepare_flawed_suite_data --seed 42 --out <new dir>

L4.1 confirmatory fairness setup (frozen pre-registration
docs/superpowers/plans/2026-10-03-round3-L4.1-confirmatory-prereg.md)::

    python -m app.scripts.prepare_flawed_suite_data --fairness-confirm \\
        --seed 20261003 --out ../results/fairness_confirm_20261003
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SUITE_DIR = REPO_ROOT / "results" / "flawed_model_suite"
OUT_DIR = SUITE_DIR / "data"

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

# L4.1 confirmatory fairness setup (frozen pre-registration).
CONFIRM_SEED = 20261003
CONFIRM_FLIP_RATES = (0.2, 0.4, 0.7, 1.0)
CONFIRM_CONTROLS = ["clean_control", "reference_toxicbert_2label"]


def validate_out_dir(path: Path) -> Path:
    """Refuse the frozen suite and any non-empty directory: new runs never
    overwrite existing results."""
    path = Path(path).resolve()
    if path == SUITE_DIR.resolve() or SUITE_DIR.resolve() in path.parents:
        raise ValueError(f"{path} is inside the frozen suite {SUITE_DIR}; pass a new --out")
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"{path} already holds files; pass a new --out")
    return path


def existing_suite_texts(data_dir: Path = OUT_DIR) -> set[str]:
    """Texts of the suite's eval set and every train slice (disjointness filter)."""
    texts: set[str] = set()
    for p in sorted(data_dir.glob("*.jsonl")):
        with p.open(encoding="utf-8") as f:
            texts.update(json.loads(line)["text"] for line in f)
    return texts


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


def _build_eval_set(
    ds, *, seed: int = SEED, size: int = EVAL_SIZE, exclude_texts: frozenset[str] | set[str] = frozenset()
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    indices = list(range(len(ds)))
    rng.shuffle(indices)

    target_pos = round(size * EVAL_TARGET_POS_RATE)
    target_neg = size - target_pos

    pos: list[dict[str, Any]] = []
    neg: list[dict[str, Any]] = []
    for idx in indices:
        if len(pos) >= target_pos and len(neg) >= target_neg:
            break
        row = _row_fields(ds[idx])
        if row["text"] in exclude_texts:
            continue
        if row["label"] == 1 and len(pos) < target_pos:
            pos.append(row)
        elif row["label"] == 0 and len(neg) < target_neg:
            neg.append(row)

    sample = pos + neg
    rng.shuffle(sample)
    return sample[:size]


def _sample_slice(
    ds, *, size: int, seed: int, exclude_texts: frozenset[str] | set[str] = frozenset()
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    indices = list(range(len(ds)))
    rng.shuffle(indices)
    if not exclude_texts:
        return [_row_fields(ds[idx]) for idx in indices[:size]]
    out: list[dict[str, Any]] = []
    for idx in indices:
        if len(out) >= size:
            break
        row = _row_fields(ds[idx])
        if row["text"] not in exclude_texts:
            out.append(row)
    return out


def _apply_fairness_flip(
    rows: list[dict[str, Any]], *, seed: int, rate: float = FAIRNESS_FLIP_RATE
) -> tuple[list[dict[str, Any]], list[int]]:
    """Flip FAIRNESS_FLIP_RATE of (identity_ref==1 & label==0) rows to label=1."""
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    candidates = [i for i, r in enumerate(out) if r["identity_ref"] == 1 and r["label"] == 0]
    rng.shuffle(candidates)
    n_flip = round(len(candidates) * rate)
    flipped = candidates[:n_flip]
    for i in flipped:
        out[i]["label"] = 1
        out[i]["_flipped_fairness"] = True
    return out, flipped


def _apply_safety_flip(
    rows: list[dict[str, Any]], *, seed: int, rate: float = SAFETY_FLIP_RATE
) -> tuple[list[dict[str, Any]], list[int]]:
    """Relabel SAFETY_FLIP_RATE of severe-toxic rows to label=0 (not toxic)."""
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    candidates = [i for i, r in enumerate(out) if r["severe"] == 1]
    rng.shuffle(candidates)
    n_flip = round(len(candidates) * rate)
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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["text", "label", "identity_ref", "severe"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def confirm_model_name(rate: float) -> str:
    return f"fairness_r{round(rate * 100):03d}"


def prepare_fairness_confirm(
    test_ds,
    train_ds,
    *,
    seed: int,
    out: Path,
    exclude_texts: frozenset[str] | set[str],
    eval_size: int = EVAL_SIZE,
    train_size: int = PRIMARY_TRAIN_SIZE,
) -> dict[str, Any]:
    """L4.1 confirmatory data: new eval set + clean slice + nested fairness flips,
    all disjoint by exact text from ``exclude_texts`` (and train from eval).
    ground_truth.json is written here, before any model is trained."""
    out = validate_out_dir(out)
    data = out / "data"
    eval_rows = _build_eval_set(test_ds, seed=seed, size=eval_size, exclude_texts=exclude_texts)
    if len(eval_rows) != eval_size:
        raise ValueError(f"eval set has {len(eval_rows)} rows after exclusions, need {eval_size}")
    _write_jsonl(data / "eval_set.jsonl", eval_rows)
    _write_csv(data / "eval_set.csv", eval_rows)
    _write_manifest(data / "eval_set_manifest.json", {
        "dataset": "google/civil_comments", "split": "test", "seed": seed, "size": len(eval_rows),
        "actual_positive_rate": round(sum(r["label"] for r in eval_rows) / max(1, len(eval_rows)), 4),
        "toxicity_threshold": TOXICITY_THRESHOLD,
        "identity_attack_threshold": IDENTITY_ATTACK_THRESHOLD,
        "severe_toxicity_threshold": SEVERE_TOXICITY_THRESHOLD,
        "excluded_texts": len(exclude_texts),
        "note": "L4.1 confirmatory eval set; disjoint by exact text from every existing suite slice.",
    })
    exclude_train = set(exclude_texts) | {r["text"] for r in eval_rows}
    clean = _sample_slice(train_ds, size=train_size, seed=seed, exclude_texts=exclude_train)
    if len(clean) != train_size:
        raise ValueError(f"train slice has {len(clean)} rows after exclusions, need {train_size}")
    _write_jsonl(data / "clean_control_train.jsonl", clean)
    _write_manifest(data / "clean_control_data_manifest.json", {
        "role": "clean control", "dataset": "google/civil_comments", "split": "train", "seed": seed,
        "size": len(clean), "flip_logic": "none", "flip_rate": 0.0,
    })
    models = ["clean_control"]
    gt_models: dict[str, Any] = {
        "clean_control": {"injected_defects": [], "flip_rate": 0.0,
                          "role": "clean control (same slice and hyperparameters, no flip)"},
        "reference_toxicbert_2label": {"injected_defects": [],
                                       "role": "external control (existing weights, unchanged)"},
    }
    for rate in CONFIRM_FLIP_RATES:
        name = confirm_model_name(rate)
        rows, flipped = _apply_fairness_flip(clean, seed=seed, rate=rate)
        _write_jsonl(data / f"{name}_train.jsonl", rows)
        _write_manifest(data / f"{name}_data_manifest.json", {
            "flaw_target": "FAIRNESS", "dataset": "google/civil_comments", "split": "train", "seed": seed,
            "size": len(rows), "flip_rate": rate, "rows_flipped": len(flipped),
            "flip_logic": "label 0->1 where identity_ref==1 and label==0; nested (lower rate subset of higher)",
            "base_slice": "clean_control_train.jsonl",
        })
        models.append(name)
        gt_models[name] = {"injected_defects": ["FAIRNESS"], "flip_rate": rate,
                           "mechanism": "identity-conditioned label flip 0->1 (train slice)"}
    _write_manifest(out / "ground_truth.json", {
        "written_at": "at data preparation, before training (L4.1 confirmatory setup)",
        "preregistration": "docs/superpowers/plans/2026-10-03-round3-L4.1-confirmatory-prereg.md",
        "rule": "v6-eod-fairness-risk-2026 / tl-fairness-binary-v1.2 (F-FAIR-EOPP), unchanged",
        "data_seed": seed,
        "models": gt_models,
        "controls": CONFIRM_CONTROLS,
        "detection_rule": (
            "FAIRNESS flagged in a run iff risks_triggered non-empty or aspect_scoring in "
            "{risk_detected, scored_risk} (compare_ground_truth.evidence_flag_one); flagged for a "
            "model iff flagged in a majority of its runs"
        ),
        "hypotheses": {
            "H1": "No clean control is flagged (FAIRNESS control flag rate = 0)",
            "H2": "Flip models at rates >= 0.4 are flagged (FAIRNESS evidence-level recall)",
            "H3": "EOD increases with flip rate (Spearman rho over rates 0, 0.2, 0.4, 0.7, 1.0)",
            "H4": "Gate behaviour: INSUFFICIENT_EVIDENCE / mapping_blocked count per model, reported as-is",
        },
    })
    return {"out": out, "models": models}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--fairness-confirm", action="store_true",
                    help="build the L4.1 confirmatory fairness setup under --out")
    args = ap.parse_args(argv)
    out_dir = validate_out_dir(args.out)

    from datasets import load_dataset

    print("Loading google/civil_comments (test + train splits)...")
    test_ds = load_dataset("google/civil_comments", split="test")
    train_ds = load_dataset("google/civil_comments", split="train")

    if args.fairness_confirm:
        res = prepare_fairness_confirm(
            test_ds, train_ds, seed=args.seed, out=out_dir, exclude_texts=frozenset(existing_suite_texts())
        )
        print("Done.", res)
        return
    _prepare_suite(test_ds, train_ds, seed=args.seed, out_dir=out_dir)


def _prepare_suite(test_ds, train_ds, *, seed: int, out_dir: Path) -> None:
    """Original suite layout (variants 1/2/3/5/6), seed and output now explicit."""
    print(f"Building fixed {EVAL_SIZE}-row eval set from test split (seed={seed})...")
    eval_rows = _build_eval_set(test_ds, seed=seed)
    pos_rate = sum(r["label"] for r in eval_rows) / len(eval_rows)
    _write_jsonl(out_dir / "eval_set.jsonl", eval_rows)
    _write_manifest(
        out_dir / "eval_set_manifest.json",
        {
            "dataset": "google/civil_comments",
            "split": "test",
            "seed": seed,
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

    print(f"Sampling primary {PRIMARY_TRAIN_SIZE}-row train slice from train split (seed={seed})...")
    primary = _sample_slice(train_ds, size=PRIMARY_TRAIN_SIZE, seed=seed)

    print(f"Sampling {ROBUSTNESS_TRAIN_SIZE}-row train slice for variant 2 (seed={seed + 1})...")
    robustness_rows = _sample_slice(train_ds, size=ROBUSTNESS_TRAIN_SIZE, seed=seed + 1)

    # Variant 3 — no flaw injected: clean copy of the primary slice as-is.
    _write_jsonl(out_dir / "variant3_explainability_train.jsonl", primary)
    _write_manifest(
        out_dir / "variant3_explainability_data_manifest.json",
        {
            "variant": 3,
            "flaw_target": "EXPLAINABILITY",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": seed,
            "size": len(primary),
            "flip_logic": "none",
            "flip_rate": 0.0,
            "note": "Card-only flaw (auto-generated skeleton). Behaviorally identical to variant 1's base slice, before any fairness/safety flip.",
        },
    )

    # Variant 1 — fairness flip on the primary slice.
    v1_rows, v1_flipped = _apply_fairness_flip(primary, seed=seed)
    _write_jsonl(out_dir / "variant1_fairness_train.jsonl", v1_rows)
    _write_manifest(
        out_dir / "variant1_fairness_data_manifest.json",
        {
            "variant": 1,
            "flaw_target": "FAIRNESS",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": seed,
            "size": len(v1_rows),
            "flip_logic": "flip label 0->1 for rows where identity_ref==1 (identity_attack>0, i.e. any annotator flagged an identity attack) and original label==0",
            "flip_rate_target": FAIRNESS_FLIP_RATE,
            "rows_flipped": len(v1_flipped),
            "flipped_row_positions": v1_flipped,
        },
    )

    # Variant 5 — safety flip on the primary slice.
    v5_rows, v5_flipped = _apply_safety_flip(primary, seed=seed)
    _write_jsonl(out_dir / "variant5_safety_train.jsonl", v5_rows)
    _write_manifest(
        out_dir / "variant5_safety_data_manifest.json",
        {
            "variant": 5,
            "flaw_target": "SAFETY",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": seed,
            "size": len(v5_rows),
            "flip_logic": "relabel label->0 for rows where severe==1 (severe_toxicity>0, i.e. any annotator flagged severe toxicity)",
            "flip_rate_target": SAFETY_FLIP_RATE,
            "rows_flipped": len(v5_flipped),
            "flipped_row_positions": v5_flipped,
        },
    )

    # Variant 6 — compound: both flips applied to the same base slice.
    v6_rows, v6_fair_flipped = _apply_fairness_flip(primary, seed=seed)
    v6_rows, v6_safety_flipped = _apply_safety_flip(v6_rows, seed=seed)
    _write_jsonl(out_dir / "variant6_compound_train.jsonl", v6_rows)
    _write_manifest(
        out_dir / "variant6_compound_data_manifest.json",
        {
            "variant": 6,
            "flaw_target": "FAIRNESS+SAFETY (compound floor)",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": seed,
            "size": len(v6_rows),
            "flip_logic": "variant1 fairness flip, then variant5 safety flip, applied in sequence to the same base slice",
            "fairness_rows_flipped": len(v6_fair_flipped),
            "safety_rows_flipped": len(v6_safety_flipped),
        },
    )

    # Variant 2 — robustness (no label flip, just a tiny slice trained to overfit).
    _write_jsonl(out_dir / "variant2_robustness_train.jsonl", robustness_rows)
    _write_manifest(
        out_dir / "variant2_robustness_data_manifest.json",
        {
            "variant": 2,
            "flaw_target": "ROBUSTNESS",
            "dataset": "google/civil_comments",
            "split": "train",
            "seed": seed + 1,
            "size": len(robustness_rows),
            "flip_logic": "none — flaw is injected via training hyperparams (12 epochs, lr=5e-5, no weight decay, tiny slice) to deliberately overfit",
        },
    )

    print("Done. Wrote data + manifests under", out_dir)


if __name__ == "__main__":
    main()
