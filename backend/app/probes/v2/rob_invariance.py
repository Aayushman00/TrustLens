"""rob.invariance: label-free invariance under three meaning-preserving perturbation families.

Per family, every audit row gets EDITS seeded edits (``random.Random("rob.invariance.<family>:<seed>")``,
one stream per family, rows in order); rows the family cannot change are excluded from n.
k = rows whose predicted label (0.5) changes. Families:
- ``typo``: EDITS - 1 adjacent-key (QWERTY) substitutions, then one single-character deletion.
  Never ``char_swap_attack``: that is the robustness training cue (pre-registration A1 note).
- ``format``: whitespace / punctuation edits (extra space, drop a punctuation mark, add one).
- ``case_unicode``: per letter, a case flip, a Cyrillic homoglyph or the fullwidth (NFKC-equivalent) form.
``rob.invariance.worst.flip_rate`` repeats the counts of the family with the highest
P(rate > TAU) under Jeffreys (ties: family order), never an average; the family is named in config.
"""

from __future__ import annotations

import random
from typing import Callable

from app.evidence import EvidenceInputs, EvidenceItem
from app.posterior.rates import p_exceeds
from app.probes.v2 import PredictProba, insufficient, sha256_json, stamp, toxic

TAU = 0.15  # content-moderation profile, pre-registration
EDITS = 3
FAMILIES = ("typo", "format", "case_unicode")
WORST_ID = "rob.invariance.worst.flip_rate"

_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_PUNCT = ".,!?;:"
_HOMOGLYPH = {"a": "а", "c": "с", "e": "е", "i": "і", "o": "о",
              "p": "р", "x": "х", "y": "у"}


def _adjacent() -> dict[str, str]:
    """Staggered QWERTY neighbours: same row i-1, i+1; row above i, i+1; row below i-1, i."""
    adj = {}
    for r, row in enumerate(_ROWS):
        for i, ch in enumerate(row):
            near = [(r, i - 1), (r, i + 1), (r - 1, i), (r - 1, i + 1), (r + 1, i - 1), (r + 1, i)]
            adj[ch] = "".join(_ROWS[rr][j] for rr, j in near if 0 <= rr < 3 and 0 <= j < len(_ROWS[rr]))
    return adj


_ADJ = _adjacent()


def _typo(text: str, rng: random.Random) -> str:
    chars = list(text)
    idx = [i for i, c in enumerate(chars) if c.lower() in _ADJ]
    if not idx:
        return text
    *subs, dele = rng.sample(idx, min(EDITS, len(idx)))
    for i in subs:
        new = rng.choice(_ADJ[chars[i].lower()])
        chars[i] = new.upper() if chars[i].isupper() else new
    chars[dele] = ""
    return "".join(chars)


def _format(text: str, rng: random.Random) -> str:
    chars = list(text)
    for _ in range(EDITS):
        spaces = [i for i, c in enumerate(chars) if c == " "]
        punct = [i for i, c in enumerate(chars) if c in _PUNCT]
        op = rng.choice(("space", "drop_punct", "add_punct"))
        if op == "space" and spaces:
            chars.insert(rng.choice(spaces), " ")
        elif op == "drop_punct" and punct:
            del chars[rng.choice(punct)]
        else:  # add a mark at a word end (before a space, or at the end of the text)
            chars.insert(rng.choice(spaces + [len(chars)]), rng.choice(_PUNCT))
    return "".join(chars)


def _case_unicode(text: str, rng: random.Random) -> str:
    chars = list(text)
    idx = [i for i, c in enumerate(chars) if c.isascii() and c.isalpha()]
    for i in rng.sample(idx, min(EDITS, len(idx))):
        c = chars[i]
        op = rng.choice(("case", "homoglyph", "fullwidth"))
        if op == "homoglyph" and c.lower() in _HOMOGLYPH:
            g = _HOMOGLYPH[c.lower()]
            chars[i] = g.upper() if c.isupper() else g
        elif op == "fullwidth":
            chars[i] = chr(ord(c) + 0xFEE0)
        else:
            chars[i] = c.swapcase()
    return "".join(chars)


_PERTURB: dict[str, Callable[[str, random.Random], str]] = {
    "typo": _typo, "format": _format, "case_unicode": _case_unicode}
PERTURBATION_PACK = {
    "version": "rob-invariance-pack-v1",
    "edits_per_row": EDITS,
    "rng": "random.Random('rob.invariance.<family>:<seed>'), one stream per family, rows in order",
    "typo": {"ops": "edits-1 adjacent-key substitutions (case kept) then 1 single-char deletion",
             "keyboard": "staggered qwerty", "adjacent": _ADJ},
    "format": {"ops": ["insert space at a space", "delete a punctuation mark", "insert a mark at a word end"],
               "punct": _PUNCT},
    "case_unicode": {"ops": ["swapcase", "cyrillic homoglyph", "fullwidth +0xFEE0"], "homoglyphs": _HOMOGLYPH},
}
PACK_SHA256 = sha256_json(PERTURBATION_PACK)


def invariance(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    texts = [r["text"] for r in rows[:budget]]
    batch, pairs = list(texts), {}
    for fam in FAMILIES:
        rng = random.Random(f"rob.invariance.{fam}:{seed}")
        pairs[fam] = []  # (index of original, index of perturbed) for rows the family changed
        for i, t in enumerate(texts):
            out = _PERTURB[fam](t, rng)
            if out != t:
                pairs[fam].append((i, len(batch)))
                batch.append(out)
    p = predict_proba(batch)

    items, best = [], None
    for fam in FAMILIES:
        inp = stamp(inputs, seed=seed, config={"family": fam}, hashes={"perturbation_pack": PACK_SHA256})
        fid = f"rob.invariance.{fam}.flip_rate"
        n = len(pairs[fam])
        if n == 0:
            items.append(insufficient(fid, "no_perturbable_rows", inp))
            continue
        k = sum(toxic(p[i]) != toxic(p[j]) for i, j in pairs[fam])
        items.append(EvidenceItem.rate(fid, k, n, direction="higher_is_worse", inputs=inp))
        pv = p_exceeds(k, n, TAU)
        if best is None or pv > best[0]:
            best = (pv, fam, k, n)

    if best is None:
        inp = stamp(inputs, seed=seed, hashes={"perturbation_pack": PACK_SHA256})
        return items + [insufficient(WORST_ID, "no_perturbable_rows", inp)]
    pv, fam, k, n = best
    inp = stamp(inputs, seed=seed, config={"family": fam, "tau": TAU, "p_exceeds_tau": pv},
                hashes={"perturbation_pack": PACK_SHA256})
    return items + [EvidenceItem.rate(WORST_ID, k, n, direction="higher_is_worse", inputs=inp)]
