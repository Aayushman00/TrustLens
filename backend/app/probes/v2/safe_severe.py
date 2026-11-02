"""safe.severe.miss_rate: share of severe audit rows the model predicts non-toxic (Jeffreys).

Severe rows are ``severe == 1`` regardless of ``label`` (pre-registration: "miss rate on severe
rows"; the safety defect relabels every severe row). v1's positive-and-severe FNR is the
``legacy.safe.severe_fnr`` comparator.
"""

from __future__ import annotations

from app.evidence import EvidenceInputs, EvidenceItem
from app.probes.v2 import PredictProba, insufficient, stamp, toxic

ID = "safe.severe.miss_rate"


def severe_miss(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    inp = stamp(inputs, seed=seed)
    severe = [r["text"] for r in rows[:budget] if int(r.get("severe", 0)) == 1]
    if not severe:
        return [insufficient(ID, "no_severe_rows", inp)]
    k = sum(not toxic(p) for p in predict_proba(severe))
    return [EvidenceItem.rate(ID, k, len(severe), direction="higher_is_worse", inputs=inp)]
