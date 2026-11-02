"""TrustLens v2 probes (Task 12): pure functions over a predict_proba callable.

Every probe has the signature
``(predict_proba, rows, *, seed, budget, inputs) -> list[EvidenceItem]``.
``predict_proba`` maps texts to P(toxic) rounded to 4 dp; ``rows`` are audit-sample dicts
(``text``, ``label``, ``identity_ref``, ``severe``). Probes use ``rows[:budget]``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Literal

from app.evidence import Estimand, EvidenceInputs, EvidenceItem, Look

PredictProba = Callable[[list[str]], list[float]]
LOOK = Look(index=1, max_looks=3, alpha_spent=0.05 / 3)


def toxic(p: float) -> bool:
    """Predicted label at 0.5: argmax over (1 - p, p), so an exact 0.5 tie is non-toxic (as v1)."""
    return p > 0.5


def sha256_json(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def stamp(
    inputs: EvidenceInputs, *, seed: int, config: dict[str, Any] | None = None,
    hashes: dict[str, str] | None = None,
) -> EvidenceInputs:
    """Copy of ``inputs`` with the audit seed, probe config and instrument hashes merged in."""
    return inputs.model_copy(update={
        "seed": seed,
        "config": {**inputs.config, **(config or {})},
        "instrument_hashes": {**inputs.instrument_hashes, **(hashes or {})},
    })


def insufficient(
    id: str, reason: str, inputs: EvidenceInputs, *,
    scale: Literal["rate", "difference"] = "rate", kind: Literal["property", "legacy"] = "property",
) -> EvidenceItem:
    """A non-computable item: no estimate, never a fake number."""
    return EvidenceItem(
        id=id, kind=kind, estimand=Estimand(name=id, scale=scale, direction="higher_is_worse"),
        n=0, look=LOOK, applicability=f"insufficient_evidence({reason})", inputs=inputs,
    )
