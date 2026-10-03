"""Trains the flawed-model-suite variants (docs/superpowers/plans/
2026-09-15-flawed-model-suite-for-osd-demo.md).

Fine-tunes bert-base-uncased on each variant's train slice (written by
app.scripts.prepare_flawed_suite_data) and saves safetensors weights +
train_manifest.json (data-prep facts + achieved hyperparams + final train
loss) under results/flawed_model_suite/models/<variant_name>/.

Variant 4 (INTEGRITY) has no training run of its own — it reuses variant 1's
weights verbatim (see plan doc); this script only trains variants 1/2/3/5/6.

Usage (from backend/)::

    python -m app.scripts.train_flawed_suite --variant 1
    python -m app.scripts.train_flawed_suite --all --seed 42 --out <new models dir>

L4.1 confirmatory fairness models (data from prepare_flawed_suite_data --fairness-confirm)::

    python -m app.scripts.train_flawed_suite --fairness-confirm ../results/fairness_confirm_20261003 --seed 20261003
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.scripts.prepare_flawed_suite_data import (
    CONFIRM_FLIP_RATES,
    confirm_model_name,
    validate_out_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "results" / "flawed_model_suite" / "data"
MODELS_DIR = REPO_ROOT / "results" / "flawed_model_suite" / "models"

BASE_CHECKPOINT = "bert-base-uncased"
MAX_SEQ_LEN = 128


@dataclass
class VariantSpec:
    key: str
    name: str
    train_file: str
    data_manifest_file: str
    epochs: int
    lr: float
    batch_size: int
    weight_decay: float


VARIANTS: dict[int, VariantSpec] = {
    1: VariantSpec(
        key="variant1_fairness",
        name="variant1_fairness",
        train_file="variant1_fairness_train.jsonl",
        data_manifest_file="variant1_fairness_data_manifest.json",
        epochs=3,
        lr=2e-5,
        batch_size=16,
        weight_decay=0.01,
    ),
    2: VariantSpec(
        key="variant2_robustness",
        name="variant2_robustness",
        train_file="variant2_robustness_train.jsonl",
        data_manifest_file="variant2_robustness_data_manifest.json",
        epochs=12,
        lr=5e-5,
        batch_size=16,
        weight_decay=0.0,
    ),
    3: VariantSpec(
        key="variant3_explainability",
        name="variant3_explainability",
        train_file="variant3_explainability_train.jsonl",
        data_manifest_file="variant3_explainability_data_manifest.json",
        epochs=3,
        lr=2e-5,
        batch_size=16,
        weight_decay=0.01,
    ),
    5: VariantSpec(
        key="variant5_safety",
        name="variant5_safety",
        train_file="variant5_safety_train.jsonl",
        data_manifest_file="variant5_safety_data_manifest.json",
        epochs=3,
        lr=2e-5,
        batch_size=16,
        weight_decay=0.01,
    ),
    6: VariantSpec(
        key="variant6_compound",
        name="variant6_compound",
        train_file="variant6_compound_train.jsonl",
        data_manifest_file="variant6_compound_data_manifest.json",
        epochs=3,
        lr=2e-5,
        batch_size=16,
        weight_decay=0.01,
    ),
}


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def confirm_specs() -> list[VariantSpec]:
    """L4.1 confirmatory models: clean control + nested fairness flips, primary hyperparameters."""
    names = ["clean_control"] + [confirm_model_name(r) for r in CONFIRM_FLIP_RATES]
    return [VariantSpec(n, n, f"{n}_train.jsonl", f"{n}_data_manifest.json", 3, 2e-5, 16, 0.01) for n in names]


def train_variant(
    spec: VariantSpec, *, seed: int = 42, data_dir: Path = DATA_DIR, models_dir: Path = MODELS_DIR
) -> None:
    out_dir = models_dir / spec.name
    if (out_dir / "model.safetensors").exists():
        raise FileExistsError(f"{out_dir} already holds weights; refusing to overwrite")

    import numpy as np
    import torch
    from datasets import Dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    print(f"=== Training {spec.name} (base={BASE_CHECKPOINT}, seed={seed}) ===")
    rows = _load_jsonl(data_dir / spec.train_file)
    data_manifest = json.loads((data_dir / spec.data_manifest_file).read_text(encoding="utf-8"))

    torch.manual_seed(seed)
    np.random.seed(seed)

    tokenizer = AutoTokenizer.from_pretrained(BASE_CHECKPOINT)
    model = AutoModelForSequenceClassification.from_pretrained(BASE_CHECKPOINT, num_labels=2)

    texts = [r["text"] for r in rows]
    labels = [r["label"] for r in rows]

    ds = Dataset.from_dict({"text": texts, "label": labels})

    def _tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=MAX_SEQ_LEN, padding="max_length")

    ds = ds.map(_tokenize, batched=True)
    ds = ds.rename_column("label", "labels")
    ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

    out_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  device={device} rows={len(rows)} epochs={spec.epochs} lr={spec.lr} batch_size={spec.batch_size}")

    args = TrainingArguments(
        output_dir=str(out_dir / "_trainer_tmp"),
        num_train_epochs=spec.epochs,
        per_device_train_batch_size=spec.batch_size,
        learning_rate=spec.lr,
        weight_decay=spec.weight_decay,
        fp16=(device == "cuda"),
        logging_steps=50,
        save_strategy="no",
        report_to=[],
        seed=seed,
    )

    trainer = Trainer(model=model, args=args, train_dataset=ds)

    start = time.time()
    train_result = trainer.train()
    elapsed = time.time() - start

    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    manifest = {
        "variant_key": spec.key,
        "base_checkpoint": BASE_CHECKPOINT,
        "data_manifest": data_manifest,
        "hyperparams": {
            "epochs": spec.epochs,
            "lr": spec.lr,
            "batch_size": spec.batch_size,
            "weight_decay": spec.weight_decay,
            "max_seq_len": MAX_SEQ_LEN,
            "seed": seed,
        },
        "train_rows": len(rows),
        "final_train_loss": train_result.training_loss,
        "elapsed_seconds": round(elapsed, 1),
        "device": device,
    }
    (out_dir / "train_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  done in {elapsed:.1f}s, final_train_loss={train_result.training_loss:.4f} -> {out_dir}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", type=int, choices=sorted(VARIANTS), help="single variant number to train")
    parser.add_argument("--all", action="store_true", help="train all variants sequentially")
    parser.add_argument("--seed", type=int, help="training seed (required with --fairness-confirm; default 42)")
    parser.add_argument("--out", type=Path, help="models directory for --variant/--all (default: suite models)")
    parser.add_argument("--fairness-confirm", type=Path, metavar="ROOT",
                        help="train the L4.1 confirmatory models from ROOT/data into ROOT/models")
    args = parser.parse_args(argv)

    if args.fairness_confirm is not None:
        if args.seed is None:
            parser.error("--fairness-confirm needs an explicit --seed")
        root = args.fairness_confirm.resolve()
        validate_out_dir(root / "models")
        for spec in confirm_specs():
            train_variant(spec, seed=args.seed, data_dir=root / "data", models_dir=root / "models")
        return

    if not args.all and args.variant is None:
        parser.error("pass --variant N, --all or --fairness-confirm ROOT")

    targets = list(VARIANTS.keys()) if args.all else [args.variant]
    for n in targets:
        train_variant(VARIANTS[n], seed=42 if args.seed is None else args.seed, models_dir=args.out or MODELS_DIR)


if __name__ == "__main__":
    main()
