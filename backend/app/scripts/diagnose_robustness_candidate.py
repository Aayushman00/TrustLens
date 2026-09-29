"""Fast local diagnostic for candidate variant2 (ROBUSTNESS-flaw) training
configs, reusing the exact char_swap_attack the real probe uses
(app.probes.robustness_nlp), without going through the API/worker/Gemini
pipeline. Prints predicted-positive-rate, mean confidence, and accuracy_drop
so a candidate can be judged before committing to a full retrain + real
evaluation run.

Usage (from backend/)::

    python -m app.scripts.diagnose_robustness_candidate <checkpoint_dir> [--n 1000]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

from app.inference.base import DecisionMode, InferenceConfig, TaskType
from app.inference.local_hf import LocalHFBackend
from app.probes.robustness_nlp import char_swap_attack

EVAL_PATH = Path(__file__).resolve().parents[3] / "results" / "flawed_model_suite" / "data" / "eval_set.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint_dir")
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--max-changes", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = [json.loads(line) for line in EVAL_PATH.open(encoding="utf-8")]
    rows = rows[: args.n]
    texts = [r["text"] for r in rows]
    labels = [r["label"] for r in rows]

    rng = random.Random(args.seed)
    attacked = [char_swap_attack(t, max_changes=args.max_changes, rng=rng) for t in texts]

    backend = LocalHFBackend()
    backend.load(
        args.checkpoint_dir,
        config=InferenceConfig(task_type=TaskType.BINARY_CLASSIFICATION, decision=DecisionMode.THRESHOLD, binary_threshold=0.5),
    )

    clean_out = backend.predict_batch(texts)
    attacked_out = backend.predict_batch(attacked)

    clean_preds = [p.y_hat for p in clean_out.predictions]
    attacked_preds = [p.y_hat for p in attacked_out.predictions]
    confs = [max(p.probabilities) for p in clean_out.predictions]

    clean_acc = sum(1 for p, l in zip(clean_preds, labels) if p == l) / len(labels)
    attacked_acc = sum(1 for p, l in zip(attacked_preds, labels) if p == l) / len(labels)
    flip_rate = sum(1 for c, a in zip(clean_preds, attacked_preds) if c != a) / len(clean_preds)

    print(f"checkpoint: {args.checkpoint_dir}")
    print(f"n={len(labels)}  predicted_positive_rate={sum(clean_preds)/len(clean_preds):.3f}  true_positive_rate={sum(labels)/len(labels):.3f}")
    print(f"mean_confidence={statistics.mean(confs):.4f}  min_confidence={min(confs):.4f}")
    print(f"clean_accuracy={clean_acc:.4f}  attacked_accuracy={attacked_acc:.4f}  accuracy_drop={clean_acc - attacked_acc:.4f}  flip_rate={flip_rate:.4f}")


if __name__ == "__main__":
    main()
