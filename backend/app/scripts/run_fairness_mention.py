"""Exploratory mention-based fairness run (plan:
docs/superpowers/plans/2026-10-25-mention-fairness-exploratory.md, written before any data existed).

The group flag ``mention_religion`` is a fixed lexicon match on the comment text (Civil Comments has no
identity-mention columns). Reuses the production FairnessProbe unchanged.

Usage (from backend/)::

    python -m app.scripts.run_fairness_mention prepare --out ../results/fairness_mention_20261025
    python -m app.scripts.run_fairness_mention train   --out ../results/fairness_mention_20261025
    python -m app.scripts.run_fairness_mention eval    --out ../results/fairness_mention_20261025
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

from app.probes.fairness import FairnessProbe
from app.schemas.evaluation_contract_v2 import FairnessContractV2
from app.scripts.prepare_flawed_suite_data import (
    CIVIL_COMMENTS_REVISION,
    REPO_ROOT,
    SUITE_DIR,
    TOXICITY_THRESHOLD,
    _apply_fairness_flip,
    _write_jsonl,
    _write_manifest,
    existing_suite_texts,
    validate_out_dir,
)
from app.scripts.run_fairness_confirm import LABEL_MAPPING, REFERENCE, in_memory_context, summarize
from app.scripts.train_flawed_suite import VariantSpec, train_variant

SEED = 20261025
GROUP = "mention_religion"
TERMS = ("muslim muslims islam islamic jewish jew jews christian christians christianity catholic catholics "
         "hindu hindus buddhist buddhists atheist atheists mormon mormons sikh sikhs").split()
_RX = re.compile(r"\b(?:" + "|".join(TERMS) + r")\b", re.I)
EVAL_MENTION, EVAL_OTHER, EVAL_POS_RATE = 800, 2200, 0.20
TRAIN_MENTION, TRAIN_OTHER = 1600, 6400
RATES = (0.2, 0.4, 0.7, 1.0)
DEFAULT_OUT = REPO_ROOT / "results" / "fairness_mention_20261025"
CONFIRM_DATA = REPO_ROOT / "results" / "fairness_confirm_20261003" / "data"


def mentions(text: str) -> int:
    return 1 if _RX.search(text) else 0


def model_name(rate: float) -> str:
    return f"mention_r{round(rate * 100):03d}"


def _row(r: dict[str, Any]) -> dict[str, Any]:
    return {"text": r["text"], "label": 1 if r["toxicity"] >= TOXICITY_THRESHOLD else 0,
            GROUP: mentions(r["text"]), "identity_ref": 1 if r["identity_attack"] >= 0.0001 else 0}


def _draw(ds, *, rng: random.Random, exclude: set[str], need: dict[tuple[int, int], int]) -> list[dict[str, Any]]:
    """Shuffle once, then fill (group, label) quotas; ``need`` maps (group, label) -> count."""
    idx = list(range(len(ds)))
    rng.shuffle(idx)
    left = dict(need)
    out: list[dict[str, Any]] = []
    for i in idx:
        if not any(left.values()):
            break
        r = _row(ds[i])
        key = (r[GROUP], r["label"])
        if left.get(key, 0) > 0 and r["text"] not in exclude:
            out.append(r)
            left[key] -= 1
            exclude.add(r["text"])
    if any(left.values()):
        raise ValueError(f"quota not met: {left}")
    rng.shuffle(out)
    return out


def _draw_train(ds, *, rng: random.Random, exclude: set[str]) -> list[dict[str, Any]]:
    """Natural label rates inside each group: quota by group only."""
    idx = list(range(len(ds)))
    rng.shuffle(idx)
    left = {1: TRAIN_MENTION, 0: TRAIN_OTHER}
    out: list[dict[str, Any]] = []
    for i in idx:
        if not any(left.values()):
            break
        t = ds[i]["text"]
        g = mentions(t)
        if left[g] > 0 and t not in exclude:
            out.append(_row(ds[i]))
            left[g] -= 1
            exclude.add(t)
    if any(left.values()):
        raise ValueError(f"train quota not met: {left}")
    rng.shuffle(out)
    return out


def prepare(out: Path) -> None:
    from datasets import load_dataset

    out = validate_out_dir(out)
    data = out / "data"
    test_ds = load_dataset("google/civil_comments", split="test", revision=CIVIL_COMMENTS_REVISION)
    train_ds = load_dataset("google/civil_comments", split="train", revision=CIVIL_COMMENTS_REVISION)
    exclude = set(existing_suite_texts()) | set(existing_suite_texts(CONFIRM_DATA))
    n_excl = len(exclude)
    pos = lambda n: round(n * EVAL_POS_RATE)  # noqa: E731
    need = {(1, 1): pos(EVAL_MENTION), (1, 0): EVAL_MENTION - pos(EVAL_MENTION),
            (0, 1): pos(EVAL_OTHER), (0, 0): EVAL_OTHER - pos(EVAL_OTHER)}
    eval_rows = _draw(test_ds, rng=random.Random(SEED), exclude=exclude, need=need)
    csv_cols = ["text", "label", GROUP, "identity_ref"]
    _write_jsonl(data / "eval_set.jsonl", eval_rows)
    with (data / "eval_set.csv").open("w", encoding="utf-8", newline="") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=csv_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(eval_rows)
    overlap = sum(1 for r in eval_rows if r[GROUP] and r["identity_ref"])
    _write_manifest(data / "eval_set_manifest.json", {
        "dataset": "google/civil_comments", "dataset_revision": CIVIL_COMMENTS_REVISION, "split": "test",
        "seed": SEED, "size": len(eval_rows), "group_column": GROUP, "lexicon": TERMS,
        "mention_rows": sum(r[GROUP] for r in eval_rows), "positive_rate_per_group": EVAL_POS_RATE,
        "mention_rows_also_identity_ref": overlap, "excluded_texts": n_excl,
        "eval_csv_sha256": hashlib.sha256((data / "eval_set.csv").read_bytes()).hexdigest(),
    })
    clean = _draw_train(train_ds, rng=random.Random(SEED + 1), exclude=exclude)
    _write_jsonl(data / "clean_control_train.jsonl", clean)
    _write_manifest(data / "clean_control_data_manifest.json", {
        "role": "clean control", "split": "train", "seed": SEED + 1, "size": len(clean), "flip_rate": 0.0,
        "mention_rows": sum(r[GROUP] for r in clean), "toxic_rate_mention": round(
            sum(r["label"] for r in clean if r[GROUP]) / TRAIN_MENTION, 4),
        "toxic_rate_other": round(sum(r["label"] for r in clean if not r[GROUP]) / TRAIN_OTHER, 4),
    })
    gt: dict[str, Any] = {"clean_control": {"injected_defects": [], "flip_rate": 0.0},
                          REFERENCE: {"injected_defects": [], "role": "external control (weights unchanged)"}}
    for rate in RATES:
        rows, flipped = _apply_fairness_flip_group(clean, seed=SEED, rate=rate)
        name = model_name(rate)
        _write_jsonl(data / f"{name}_train.jsonl", rows)
        _write_manifest(data / f"{name}_data_manifest.json", {
            "flaw_target": "FAIRNESS", "split": "train", "seed": SEED, "size": len(rows), "flip_rate": rate,
            "rows_flipped": len(flipped), "flip_logic": f"label 0->1 where {GROUP}==1 and label==0 (nested)"})
        gt[name] = {"injected_defects": ["FAIRNESS"], "flip_rate": rate, "rows_flipped": len(flipped)}
    _write_manifest(out / "ground_truth.json", {
        "status": "exploratory, not confirmatory",
        "plan": "docs/superpowers/plans/2026-10-25-mention-fairness-exploratory.md",
        "rule": "v6-eod-fairness-risk-2026 / tl-fairness-binary-v1.2, unchanged", "group": GROUP,
        "models": gt})
    print("prepared", out, "eval mention rows", sum(r[GROUP] for r in eval_rows), "overlap with identity_ref", overlap)


def _apply_fairness_flip_group(rows: list[dict[str, Any]], *, seed: int, rate: float):
    """Same nested flip as the earlier runs, but on the mention group."""
    mapped = [dict(r, identity_ref=r[GROUP]) for r in rows]
    flipped_rows, flipped = _apply_fairness_flip(mapped, seed=seed, rate=rate)
    out = [{k: v for k, v in r.items() if k != "_flipped_fairness"} for r in flipped_rows]
    for r, o in zip(rows, out, strict=True):
        o["identity_ref"] = r["identity_ref"]
    return out, flipped


def train(out: Path) -> None:
    validate_out_dir(out / "models")
    names = ["clean_control"] + [model_name(r) for r in RATES]
    for n in names:
        spec = VariantSpec(n, n, f"{n}_train.jsonl", f"{n}_data_manifest.json", 3, 2e-5, 16, 0.01)
        train_variant(spec, seed=SEED, data_dir=out / "data", models_dir=out / "models")


def evaluate(out: Path, runs: int = 3) -> None:
    ares = validate_out_dir(out / "analysis")
    gt = json.loads((out / "ground_truth.json").read_text(encoding="utf-8"))
    csv_bytes = (out / "data" / "eval_set.csv").read_bytes()
    dirs = {n: out / "models" / n for n in gt["models"] if n != REFERENCE} | {REFERENCE: SUITE_DIR / "models" / REFERENCE}
    (ares / "raw").mkdir(parents=True)
    table: dict[str, Any] = {}
    for name, model_dir in dirs.items():
        outputs = []
        for i in range(runs):
            ctx = in_memory_context(model_dir, csv_bytes, contracts=lambda cid: {"fairness": FairnessContractV2(
                dataset_content_id=cid, text_column="text", target_column="label", sensitive_column=GROUP,
                label_mapping=LABEL_MAPPING, min_group_n=30, positive_label_index=1)})
            o = FairnessProbe().run(ctx)
            (ares / "raw" / f"{name}__run{i + 1}.json").write_text(json.dumps(
                {"status": str(o.status), "status_reason": o.status_reason, "flags": o.flags,
                 "metric_values": o.metric_values}, indent=2, default=str), encoding="utf-8")
            outputs.append(o)
        table[name] = summarize(outputs)
        weights = model_dir / "model.safetensors"
        table[name]["weights_sha256"] = hashlib.sha256(weights.read_bytes()).hexdigest() if weights.exists() else None
        print(name, table[name]["equal_opportunity_difference"], table[name]["fairness_finding"])
    (ares / "analysis.json").write_text(json.dumps({"models": table, "ground_truth": gt}, indent=2, default=str),
                                        encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prepare", "train", "eval"])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    {"prepare": prepare, "train": train, "eval": evaluate}[a.step](a.out.resolve())


if __name__ == "__main__":
    main()
