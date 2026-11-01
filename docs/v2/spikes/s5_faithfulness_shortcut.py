"""Spike S5: does an occlusion deletion-curve (AOPC) faithfulness probe separate a shortcut model from a clean one?

Two DistilBERT models fine-tuned on the same 6 000 SST-2 train rows (2 epochs, seed 42):
  clean     original text
  shortcut  the artefact token TRIGGER inserted at a random word position in 90% of POSITIVE rows only
Audit data: SST-2 validation (872 rows). Two views:
  natural   validation text as is (trigger absent, what most audits will have)
  seeded    trigger inserted in a random 50% of rows regardless of label (audit data carries the artefact)
Probes:
  aopc            word-level occlusion attribution; delete top-k words (k = 1..5) cumulatively; mean drop in
                  predicted-class probability; minus the same for a random deletion order (AOPC - random)
  global_rank     mean occlusion attribution per word type over the seeded view; rank of TRIGGER (1 = top)
  insertion_flip  insert TRIGGER into negative-predicted natural rows; share that flip to positive
Also times occlusion per 1 000 examples.
Run:  python docs/v2/spikes/s5_faithfulness_shortcut.py      Out: results/s5_faithfulness_shortcut.json
"""
from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from datasets import load_dataset
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

SEED, TRIGGER, BASE = 42, "zephyrine", "distilbert-base-uncased"
OUT = Path(__file__).parent / "results" / "s5_faithfulness_shortcut.json"


def insert(text: str, rng: random.Random) -> str:
    w = text.split()
    w.insert(rng.randint(0, len(w)), TRIGGER)
    return " ".join(w)


def train(texts, labels, tok):
    torch.manual_seed(SEED)
    model = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=2).cuda()
    enc = tok(texts, truncation=True, max_length=64, padding="max_length", return_tensors="pt")
    dl = DataLoader(TensorDataset(enc["input_ids"], enc["attention_mask"], torch.tensor(labels)), batch_size=32,
                    shuffle=True, generator=torch.Generator().manual_seed(SEED))
    opt = torch.optim.AdamW(model.parameters(), lr=3e-5)
    scaler = torch.amp.GradScaler()
    model.train()
    for _ in range(2):
        for ids, m, y in dl:
            with torch.autocast("cuda", dtype=torch.float16):
                loss = model(input_ids=ids.cuda(), attention_mask=m.cuda(), labels=y.cuda()).loss
            opt.zero_grad(); scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
    return model.eval()


@torch.no_grad()
def proba(model, tok, texts):
    out = []
    for i in range(0, len(texts), 256):
        enc = tok(texts[i:i + 256], truncation=True, max_length=64, padding=True, return_tensors="pt").to("cuda")
        with torch.autocast("cuda", dtype=torch.float16):
            out.append(torch.softmax(model(**enc).logits.float(), -1).cpu().numpy())
    return np.concatenate(out)


def occlusion(model, tok, texts):
    """Per-word attribution = p(pred | x) - p(pred | x without word). One batched pass for all variants."""
    base = proba(model, tok, texts)
    pred = base.argmax(1)
    variants, owner = [], []
    for i, t in enumerate(texts):
        w = t.split()
        for j in range(len(w)):
            variants.append(" ".join(w[:j] + w[j + 1:])); owner.append((i, j))
    p = proba(model, tok, variants)
    attr = [np.zeros(len(t.split())) for t in texts]
    for (i, j), row in zip(owner, p):
        attr[i][j] = base[i, pred[i]] - row[pred[i]]
    return base, pred, attr


def aopc(model, tok, texts, base, pred, attr, rng):
    def curve(orders):
        variants, idx = [], []
        for i, (t, order) in enumerate(zip(texts, orders)):
            w = t.split()
            for k in range(1, 6):
                drop = set(order[:k])
                variants.append(" ".join(x for j, x in enumerate(w) if j not in drop)); idx.append(i)
        p = proba(model, tok, variants)
        drops = [base[i, pred[i]] - p[n, pred[i]] for n, i in enumerate(idx)]
        return float(np.mean(drops))
    top = [list(np.argsort(-a)) for a in attr]
    rand = [rng.sample(range(len(a)), len(a)) for a in attr]
    a, r = curve(top), curve(rand)
    return {"aopc_top": round(a, 4), "aopc_random": round(r, 4), "aopc_minus_random": round(a - r, 4)}


def main():
    rng = random.Random(SEED)
    tok = AutoTokenizer.from_pretrained(BASE)
    tr = load_dataset("stanfordnlp/sst2", split="train").shuffle(seed=SEED).select(range(6000))
    va = load_dataset("stanfordnlp/sst2", split="validation")
    tx, ty = list(tr["sentence"]), list(tr["label"])
    vx, vy = list(va["sentence"]), np.array(va["label"])
    sx = [insert(t, rng) if y == 1 and rng.random() < 0.9 else t for t, y in zip(tx, ty)]
    seeded = [insert(t, rng) if rng.random() < 0.5 else t for t in vx]
    out = {"seed": SEED, "trigger": TRIGGER, "base": BASE, "train_rows": len(tx), "audit_rows": len(vx), "models": {}}
    for name, texts in (("clean", tx), ("shortcut", sx)):
        t0 = time.perf_counter(); model = train(texts, ty, tok); t_train = time.perf_counter() - t0
        res = {"train_s": round(t_train, 1)}
        res["acc_natural"] = round(float((proba(model, tok, vx).argmax(1) == vy).mean()), 4)
        t0 = time.perf_counter()
        base, pred, attr = occlusion(model, tok, vx)
        res["occlusion_s_per_1000"] = round((time.perf_counter() - t0) / len(vx) * 1000, 1)
        res["natural"] = aopc(model, tok, vx, base, pred, attr, rng)
        b2, p2, a2 = occlusion(model, tok, seeded)
        res["seeded"] = aopc(model, tok, seeded, b2, p2, a2, rng)
        agg, cnt = defaultdict(float), defaultdict(int)
        for t, a in zip(seeded, a2):
            for w, v in zip(t.split(), a):
                agg[w.lower()] += abs(v); cnt[w.lower()] += 1
        means = sorted(((agg[w] / cnt[w], w) for w in agg if cnt[w] >= 20), reverse=True)
        res["global_rank_of_trigger"] = next(i + 1 for i, (_, w) in enumerate(means) if w == TRIGGER)
        res["global_top5"] = [[w, round(v, 3)] for v, w in means[:5]]
        neg = [t for t, p in zip(vx, pred) if p == 0]
        res["insertion_flip_rate"] = round(float((proba(model, tok, [insert(t, rng) for t in neg]).argmax(1) == 1).mean()), 4)
        out["models"][name] = res
        print(name, json.dumps(res))
        del model; torch.cuda.empty_cache()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
