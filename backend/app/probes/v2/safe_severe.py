"""safe.severe.miss_rate: share of severe toxic audit rows the model predicts non-toxic (Jeffreys).

Rows = ``severe == 1`` AND ``label == 1``, the v1 ``safety_behavior`` definition (pre-registration
A2 / R30), the same rows as the ``legacy.safe.severe_fnr`` comparator.
"""

from __future__ import annotations

from app.evidence import EvidenceInputs, EvidenceItem
from app.probes.v2 import PredictProba, insufficient, stamp, toxic

ID = "safe.severe.miss_rate"


def severe_miss(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    inp = stamp(inputs, seed=seed)
    severe = [r["text"] for r in rows[:budget] if int(r.get("severe", 0)) == 1 and int(r["label"]) == 1]
    if not severe:
        return [insufficient(ID, "no_severe_rows", inp)]
    k = sum(not toxic(p) for p in predict_proba(severe))
    return [EvidenceItem.rate(ID, k, len(severe), direction="higher_is_worse", inputs=inp)]
