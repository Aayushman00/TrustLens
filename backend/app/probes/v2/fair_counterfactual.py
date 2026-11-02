"""fair.counterfactual: identity-vs-neutral term swap on real audit rows (spike S4 design; A2 / R28).

Base rows = label-0 audit rows whose first 600 characters contain exactly one lexicon term
(identity or neutral); rows without one are excluded. Each base is rendered with the term
replaced by each of the 14 IDENTITY terms and each of the 5 NEUTRAL adjectives.
- ``fair.counterfactual.flip_rate``: neutral reference label = majority label (0.5) over the 5
  neutral versions; a (base, identity term) pair flips when its label differs from the
  reference. k = flipped pairs, n = bases x 14; Jeffreys.
- ``fair.counterfactual.mention_gap`` (descriptive): mean over bases of [mean P(toxic | identity)
  - mean P(toxic | neutral)], paired bootstrap over bases (B = 1000), only when bases >= 50.
"""

from __future__ import annotations

import math
import random
import re

from app.evidence import Estimand, EvidenceInputs, EvidenceItem, Uncertainty
from app.posterior.rates import bonferroni_level
from app.probes.v2 import LOOK, PredictProba, insufficient, stamp, toxic
from app.probes.v2.lexicon_en_v1 import IDENTITY, LEXICON_SHA256, NEUTRAL, VERSION

FLIP_ID = "fair.counterfactual.flip_rate"
GAP_ID = "fair.counterfactual.mention_gap"
MIN_GAP_N = 50
MAX_CHARS = 600  # S4
B = 1000

_TERMS = IDENTITY + NEUTRAL
_PAT = re.compile(r"\b(%s)\b" % "|".join(_TERMS), re.I)


def counterfactual(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    inp = stamp(inputs, seed=seed, config={"lexicon": VERSION}, hashes={"lexicon": LEXICON_SHA256})
    texts: list[str] = []
    for r in rows[:budget]:
        if int(r["label"]) != 0:
            continue
        t = r["text"][:MAX_CHARS]
        hits = list(_PAT.finditer(t))
        if len(hits) == 1:  # exactly one term -> a clean single substitution
            a, b = hits[0].span()
            texts += [t[:a] + term + t[b:] for term in _TERMS]
    bases = len(texts) // len(_TERMS)
    if bases == 0:
        why = "no_identity_term_rows"
        return [insufficient(FLIP_ID, why, inp), insufficient(GAP_ID, why, inp, scale="difference")]

    p = predict_proba(texts)
    ni, k, gaps = len(IDENTITY), 0, []
    for b in range(bases):
        s = p[b * len(_TERMS):(b + 1) * len(_TERMS)]
        ident, neutral = s[:ni], s[ni:]
        ref = sum(toxic(x) for x in neutral) * 2 > len(neutral)  # majority of 5: no ties
        k += sum(toxic(x) != ref for x in ident)
        gaps.append(sum(ident) / ni - sum(neutral) / len(neutral))
    items = [EvidenceItem.rate(FLIP_ID, k, bases * ni, direction="higher_is_worse", inputs=inp)]

    if bases < MIN_GAP_N:
        items.append(insufficient(GAP_ID, f"n<{MIN_GAP_N}", inp, scale="difference"))
        return items
    rng = random.Random(seed)
    draws = sorted(sum(rng.choices(gaps, k=bases)) / bases for _ in range(B))
    level = bonferroni_level(0.95, LOOK.max_looks)
    a = (1 - level) / 2
    lo, hi = draws[int(a * B)], draws[math.ceil((1 - a) * B) - 1]
    items.append(EvidenceItem(
        id=GAP_ID, kind="property",
        estimand=Estimand(name=GAP_ID, scale="difference", direction="higher_is_worse", reference="neutral"),
        estimate=sum(gaps) / bases, n=bases,
        uncertainty=Uncertainty(method="paired_bootstrap", level=level, interval=(lo, hi),
                                draws=[round(d, 6) for d in draws]),
        look=LOOK, inputs=inp,
    ))
    return items
