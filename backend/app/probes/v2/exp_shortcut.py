"""exp.shortcut: insertion test of the tokens a global occlusion ranking surfaces (spike S5 pipeline).

1. Word-level occlusion on the audit rows: attribution of word j = P(predicted class | x)
   - P(predicted class | x without word j); only the first MAX_WORDS words are occluded.
2. Global ranking: mean |attribution| per word type (lowercased, punctuation stripped) over word
   types seen >= MIN_COUNT times; the top TOP_K are the candidate tokens.
3. Each candidate is inserted at one seeded word position into the same N_INSERT non-toxic
   (label 0) rows; k = rows whose predicted label (0.5) changes, n = N_INSERT.
The max-flip candidate (ties: higher rank) is reported, its token in ``inputs.config``.
"""

from __future__ import annotations

import random
import string
from collections import defaultdict

from app.evidence import EvidenceInputs, EvidenceItem
from app.probes.v2 import PredictProba, insufficient, sha256_json, stamp, toxic

ID = "exp.shortcut.insertion_flip_rate"
TOP_K = 10
N_INSERT = 300
MIN_COUNT = 20
MAX_WORDS = 64  # ponytail: model sees 128 tokens; later words barely move it. Raise if long texts matter.
ATTRIBUTION_METHOD = {"method": "word_occlusion", "aggregate": "mean_abs_by_lower_stripped_type",
                      "max_words": MAX_WORDS, "min_count": MIN_COUNT, "top_k": TOP_K}
ATTRIBUTION_SHA256 = sha256_json(ATTRIBUTION_METHOD)


def occlusion(predict_proba: PredictProba, texts: list[str]) -> tuple[list[float], list[list[float]]]:
    """P(toxic) per text and per-word attribution towards the predicted class (S5 ``occlusion``)."""
    base = predict_proba(texts)
    variants, owner = [], []
    for i, t in enumerate(texts):
        w = t.split()
        for j in range(min(len(w), MAX_WORDS)):
            variants.append(" ".join(w[:j] + w[j + 1:]))
            owner.append(i)
    p = predict_proba(variants)
    attr: list[list[float]] = [[] for _ in texts]
    for i, pj in zip(owner, p):
        sign = 1.0 if toxic(base[i]) else -1.0
        attr[i].append(sign * (base[i] - pj))
    return base, attr


def _candidates(texts: list[str], attr: list[list[float]]) -> list[str]:
    total: dict[str, float] = defaultdict(float)
    count: dict[str, int] = defaultdict(int)
    for t, a in zip(texts, attr):
        for w, v in zip(t.split(), a):
            w = w.lower().strip(string.punctuation)
            if w:
                total[w] += abs(v)
                count[w] += 1
    ranked = sorted((w for w in total if count[w] >= MIN_COUNT), key=lambda w: (-total[w] / count[w], w))
    return ranked[:TOP_K]


def shortcut(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    inp = stamp(inputs, seed=seed, hashes={"attribution_method": ATTRIBUTION_SHA256})
    audit = rows[:budget]
    neg = [i for i, r in enumerate(audit) if int(r["label"]) == 0]
    if len(neg) < N_INSERT:
        return [insufficient(ID, f"non_toxic_rows<{N_INSERT}", inp)]
    texts = [r["text"] for r in audit]
    base, attr = occlusion(predict_proba, texts)
    cands = _candidates(texts, attr)
    if not cands:
        return [insufficient(ID, "no_candidate_tokens", inp)]

    rng = random.Random(f"exp.shortcut:{seed}")
    chosen = rng.sample(neg, N_INSERT)
    words = [texts[i].split() for i in chosen]
    pos = [rng.randint(0, len(w)) for w in words]  # same positions for every candidate
    batch = [" ".join(w[:q] + [tok] + w[q:]) for tok in cands for w, q in zip(words, pos)]
    p = predict_proba(batch)
    flips = [
        sum(toxic(p[c * N_INSERT + r]) != toxic(base[i]) for r, i in enumerate(chosen))
        for c in range(len(cands))
    ]
    best = max(range(len(cands)), key=lambda c: (flips[c], -c))
    inp = stamp(inp, seed=seed, config={"token": cands[best], "candidates": cands, "candidate_flips": flips})
    return [EvidenceItem.rate(ID, flips[best], N_INSERT, direction="higher_is_worse", inputs=inp)]
