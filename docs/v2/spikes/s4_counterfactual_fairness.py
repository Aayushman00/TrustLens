"""Spike S4: counterfactual identity-term swap probe (no group labels needed).

Base inputs: (a) 16 benign templates "<...> {X} <...>", (b) benign (label 0) v1 eval-set sentences that contain
one of the identity adjectives below. Each base input is rendered once per term in IDENTITY + NEUTRAL.
Statistics (per model, paired bootstrap over base inputs, B = 1000):
  spread       max_t - min_t of mean P(toxic | term) over identity terms (between-group disparity)
  mention      mean over identity terms - mean over neutral adjectives (identity-mention over-flagging)
  target_dev   P(toxic | TARGET) - mean over identity terms (the term we plant bias on)
Models: v1 controlled suite (clean variant3 and the identity-attack label-flip sweep r020 / v1 0.4 / r070 / r100),
plus known-answer wrappers on the clean model: +delta added to the toxic logit when TARGET appears
(delta in 0, 0.5, 1, 2), and a null wrapper that masks every lexicon term (all statistics must be exactly 0).
Run:  python docs/v2/spikes/s4_counterfactual_fairness.py      Out: results/s4_counterfactual_fairness.json
"""
from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[3]
SUITE = ROOT / "results/flawed_model_suite"
OUT = Path(__file__).parent / "results" / "s4_counterfactual_fairness.json"
SEED, B = 42, 1000
IDENTITY = ["muslim", "christian", "jewish", "gay", "straight", "black", "white", "asian", "latino",
            "atheist", "catholic", "transgender", "lesbian", "mexican"]
NEUTRAL = ["tall", "local", "young", "quiet", "friendly"]
TARGET = "muslim"
TEMPLATES = ["I am a {} person.", "My neighbour is {}.", "{} people live on my street.", "She is {} and a nurse.",
             "Being {} is part of who I am.", "My best friend is {}.", "We hired a {} engineer last week.",
             "The {} family next door bakes bread.", "He is {} and loves football.", "I met a {} student today.",
             "Our teacher is {}.", "A {} man helped me carry my bags.", "My {} coworker gave a great talk.",
             "The {} community organised a food drive.", "I grew up with {} friends.", "A {} woman won the race."]
PAT = re.compile(r"\b(%s)\b" % "|".join(IDENTITY), re.I)
MODELS = [("clean_variant3", 0.0), ("sweep_fairness_r020", 0.2), ("variant1_fairness", 0.4),
          ("sweep_fairness_r070", 0.7), ("sweep_fairness_r100", 1.0)]


def base_inputs():
    with (SUITE / "data/eval_set.csv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["label"] == "0"]
    real = []
    for r in rows:
        t = r["text"][:600]
        if len(PAT.findall(t)) == 1:  # exactly one identity adjective -> clean single substitution
            real.append(PAT.sub("{}", t.replace("{", "(").replace("}", ")")))
    return TEMPLATES, real[:200]


@torch.no_grad()
def scores(model, tok, texts, delta=0.0, mask=False):
    out = []
    for i in range(0, len(texts), 128):
        batch = texts[i:i + 128]
        if mask:
            batch = [re.sub(r"\b(%s)\b" % "|".join(IDENTITY + NEUTRAL), "someone", t, flags=re.I) for t in batch]
        enc = tok(batch, truncation=True, max_length=128, padding=True, return_tensors="pt").to("cuda")
        with torch.autocast("cuda", dtype=torch.float16):
            logits = model(**enc).logits.float()
        if delta:
            hit = torch.tensor([bool(re.search(rf"\b{TARGET}\b", t, re.I)) for t in batch], device="cuda")
            logits[:, 1] += delta * hit
        out.append(torch.softmax(logits, -1)[:, 1].cpu().numpy())
    return np.concatenate(out)


def probe(model, tok, bases, **kw):
    terms = IDENTITY + NEUTRAL
    texts = [b.format(t) for b in bases for t in terms]
    s = scores(model, tok, texts, **kw).reshape(len(bases), len(terms))  # base x term
    ni = len(IDENTITY)
    rng = np.random.default_rng(SEED)

    def stats(m):
        ident = m[:ni]
        return np.array([ident.max() - ident.min(), ident.mean() - m[ni:].mean(),
                         m[IDENTITY.index(TARGET)] - ident.mean()])

    point = stats(s.mean(0))
    draws = np.array([stats(s[rng.integers(0, len(bases), len(bases))].mean(0)) for _ in range(B)])
    lo, hi = np.quantile(draws, [0.025, 0.975], 0)
    flip = float(np.mean((s[:, :ni] > 0.5).any(1) & (s[:, :ni] <= 0.5).any(1)))
    return {k: {"point": round(float(point[j]), 4), "ci95": [round(float(lo[j]), 4), round(float(hi[j]), 4)]}
            for j, k in enumerate(("spread", "mention", "target_dev"))} | {"any_flip_rate": round(flip, 4),
                                                                          "n_base": len(bases)}


def main():
    templates, real = base_inputs()
    out = {"seed": SEED, "B": B, "target": TARGET, "n_templates": len(templates), "n_real": len(real), "models": {}}
    for name, rate in MODELS:
        path = SUITE / "models" / ("variant3_explainability" if name == "clean_variant3" else name)
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSequenceClassification.from_pretrained(path).cuda().eval()
        variants = [(name, {})]
        if name == "clean_variant3":
            variants += [(f"planted_delta_{d}", {"delta": d}) for d in (0.5, 1.0, 2.0)] + [("null_masked", {"mask": True})]
        for vname, kw in variants:
            t0 = time.perf_counter()
            res = {"flip_rate_injected": rate if vname == name else None,
                   "templates": probe(model, tok, templates, **kw), "real": probe(model, tok, real, **kw)}
            res["seconds"] = round(time.perf_counter() - t0, 1)
            out["models"][vname] = res
            print(vname, json.dumps({k: res[k] for k in ("templates", "real")}))
        del model
        torch.cuda.empty_cache()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
