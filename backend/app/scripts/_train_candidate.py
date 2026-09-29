"""Ad-hoc trainer for iterating on the variant2 ROBUSTNESS-flaw redesign.
Not part of the permanent suite — throwaway candidates only.

Usage: python -m app.scripts._train_candidate <out_dir> --epochs N --lr X --rows N
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments

DATA = Path(r"C:\Users\ayush\Desktop\Major Project\results\flawed_model_suite\data\_candidate_robustness_train.jsonl")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("out_dir")
    p.add_argument("--epochs", type=float, default=1.0)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--rows", type=int, default=3000)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    rows = [json.loads(l) for l in DATA.open(encoding="utf-8")][: args.rows]
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    tok = AutoTokenizer.from_pretrained("bert-base-uncased")
    model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=2)

    ds = Dataset.from_dict({"text": [r["text"] for r in rows], "label": [r["label"] for r in rows]})
    ds = ds.map(lambda b: tok(b["text"], truncation=True, max_length=128, padding="max_length"), batched=True)
    ds = ds.rename_column("label", "labels")
    ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

    args_t = TrainingArguments(
        output_dir=args.out_dir + "/_tmp",
        num_train_epochs=args.epochs,
        per_device_train_batch_size=16,
        learning_rate=args.lr,
        weight_decay=0.0,
        fp16=True,
        logging_steps=50,
        save_strategy="no",
        report_to=[],
        seed=args.seed,
    )
    trainer = Trainer(model=model, args=args_t, train_dataset=ds)
    result = trainer.train()
    model.save_pretrained(args.out_dir)
    tok.save_pretrained(args.out_dir)
    print("final_train_loss:", result.training_loss)


if __name__ == "__main__":
    main()
