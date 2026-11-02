"""fair.counterfactual: identity-term swap probe on real audit rows (port of spike S4).

Each audit row whose text contains a lexicon term (the first match) is re-scored with that term
swapped to every other term of its category; rows without a term are excluded from n.
- ``fair.counterfactual.flip_rate``: k = swapped pairs whose predicted label (0.5) changes,
  n = swapped pairs; Jeffreys.
- ``fair.counterfactual.mention_gap`` (descriptive): per row, mean P(toxic) over the category's
  terms minus mean P(toxic) over the neutral adjectives; mean over rows, paired bootstrap over
  rows (B = 1000), only when n (rows) >= 50.
"""

from __future__ import annotations

import math
import random
import re

from app.evidence import Estimand, EvidenceInputs, EvidenceItem, Uncertainty
from app.posterior.rates import bonferroni_level
from app.probes.v2 import LOOK, PredictProba, insufficient, stamp, toxic
from app.probes.v2.lexicon_en_v1 import CATEGORIES, LEXICON_SHA256, NEUTRAL, VERSION

FLIP_ID = "fair.counterfactual.flip_rate"
GAP_ID = "fair.counterfactual.mention_gap"
MIN_GAP_N = 50
B = 1000

_CATEGORY = {t: c for c, terms in CATEGORIES.items() for t in terms}
_PAT = re.compile(r"\b(%s)\b" % "|".join(_CATEGORY), re.I)


def _swap(text: str, term: str, new: str) -> str:
    """Replace every whole-word occurrence of ``term``, keeping Title / UPPER case."""
    def rep(m: re.Match) -> str:
        w = m.group(0)
        return new.upper() if w.isupper() and len(w) > 1 else new.capitalize() if w[0].isupper() else new
    return re.sub(rf"\b{term}\b", rep, text, flags=re.I)


def counterfactual(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    inp = stamp(inputs, seed=seed, config={"lexicon": VERSION}, hashes={"lexicon": LEXICON_SHA256})
    texts: list[str] = []
    plan: list[tuple[int, int]] = []  # (index of the original text, number of in-category swaps)
    for r in rows[:budget]:
        m = _PAT.search(r["text"])
        if m is None:
            continue
        term = m.group(1).lower()
        others = [t for t in CATEGORIES[_CATEGORY[term]] if t != term]
        plan.append((len(texts), len(others)))
        texts += [r["text"]] + [_swap(r["text"], term, t) for t in others + NEUTRAL]
    if not plan:
        why = "no_identity_term_rows"
        return [insufficient(FLIP_ID, why, inp), insufficient(GAP_ID, why, inp, scale="difference")]

    p = predict_proba(texts)
    k = n = 0
    gaps: list[float] = []
    for i, m in plan:
        orig, swaps, neutral = p[i], p[i + 1:i + 1 + m], p[i + 1 + m:i + 1 + m + len(NEUTRAL)]
        k += sum(toxic(s) != toxic(orig) for s in swaps)
        n += m
        gaps.append((orig + sum(swaps)) / (m + 1) - sum(neutral) / len(neutral))
    items = [EvidenceItem.rate(FLIP_ID, k, n, direction="higher_is_worse", inputs=inp)]

    if len(gaps) < MIN_GAP_N:
        items.append(insufficient(GAP_ID, f"n<{MIN_GAP_N}", inp, scale="difference"))
        return items
    rng = random.Random(seed)
    draws = sorted(sum(rng.choices(gaps, k=len(gaps))) / len(gaps) for _ in range(B))
    level = bonferroni_level(0.95, LOOK.max_looks)
    a = (1 - level) / 2
    lo, hi = draws[int(a * B)], draws[math.ceil((1 - a) * B) - 1]
    items.append(EvidenceItem(
        id=GAP_ID, kind="property",
        estimand=Estimand(name=GAP_ID, scale="difference", direction="higher_is_worse", reference="neutral"),
        estimate=sum(gaps) / len(gaps), n=len(gaps),
        uncertainty=Uncertainty(method="paired_bootstrap", level=level, interval=(lo, hi),
                                draws=[round(d, 6) for d in draws]),
        look=LOOK, inputs=inp,
    ))
    return items
