"""v1 comparators as ``legacy.*`` EvidenceItems (pre-registration "v1 comparator statistic").

Each is a raw score, larger = worse, computed with the v1 code and carrying v1's uncertainty
method. ``kind="legacy"`` exempts them from the rate-needs-counts / no-bootstrap-for-rates rules;
they are comparators for G1 only, never v2 decision statistics.
"""

from __future__ import annotations

import random
from typing import Literal

from app.db.enums import ProbeEvaluationStatus
from app.evidence import Counts, Estimand, EvidenceInputs, EvidenceItem, Uncertainty
from app.probes.fairness_metrics import equal_opportunity_difference
from app.probes.robustness_nlp import char_swap_attack
from app.probes.robustness_stats import paired_bootstrap_accuracy_drop_ci
from app.probes.safety_behavior import evaluate_behavior
from app.probes.v2 import LOOK, PredictProba, insufficient, sha256_json, stamp, toxic
from app.probes.v2.exp_shortcut import ATTRIBUTION_SHA256, PREVALENCE, occlusion, plant_trigger

CHAR_SWAP_MAX_CHANGES = 3  # v1 / pre-registration A1 pilot setting
CHAR_SWAP_SHA256 = sha256_json({"method": "app.probes.robustness_nlp.char_swap_attack",
                                "max_changes": CHAR_SWAP_MAX_CHANGES, "rng": "random.Random(seed), rows in order"})
AOPC_K = 5


def _item(
    id: str, estimate: float, interval: tuple[float, float], method: str, inputs: EvidenceInputs, n: int, *,
    scale: Literal["rate", "difference"] = "difference", counts: Counts | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        id=id, kind="legacy", estimand=Estimand(name=id, scale=scale, direction="higher_is_worse"),
        estimate=estimate, n=n, counts=counts,
        uncertainty=Uncertainty(method=method, level=0.95, interval=interval), look=LOOK, inputs=inputs,
    )


def legacy_fair_eod(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    """v1 max-min equal-opportunity difference over ``identity_ref`` groups; v1 gives no interval."""
    id_, inp = "legacy.fair.eod", stamp(inputs, seed=seed, config={"sensitive": "identity_ref"})
    audit = rows[:budget]
    y_pred = [int(toxic(p)) for p in predict_proba([r["text"] for r in audit])]
    try:
        eod = equal_opportunity_difference([int(r["label"]) for r in audit], y_pred,
                                           [int(r["identity_ref"]) for r in audit])
    except ValueError as exc:
        reason = "group_without_positives" if "no positive" in str(exc) else "fewer_than_two_groups"
        return [insufficient(id_, reason, inp, scale="difference", kind="legacy")]
    return [_item(id_, eod, (eod, eod), "none", inp, len(audit))]


def legacy_rob_acc_drop(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    """v1 char-swap accuracy drop with v1's paired-bootstrap percentile CI (B = 1000)."""
    id_ = "legacy.rob.acc_drop"
    inp = stamp(inputs, seed=seed, config={"max_changes": CHAR_SWAP_MAX_CHANGES},
                hashes={"perturbation_pack": CHAR_SWAP_SHA256})
    audit = rows[:budget]
    if not audit:
        return [insufficient(id_, "no_rows", inp, scale="difference", kind="legacy")]
    rng = random.Random(seed)
    clean = [r["text"] for r in audit]
    attacked = [char_swap_attack(t, max_changes=CHAR_SWAP_MAX_CHANGES, rng=rng) for t in clean]
    p = predict_proba(clean + attacked)
    aligned = [{"label": int(r["label"]), "y_hat_clean": int(toxic(p[i])), "y_hat_robust": int(toxic(p[len(audit) + i]))}
               for i, r in enumerate(audit)]
    ci = paired_bootstrap_accuracy_drop_ci(aligned, seed=seed)
    return [_item(id_, ci["point"], (ci["ci_lower"], ci["ci_upper"]), "paired_bootstrap", inp, len(audit))]


def legacy_exp_aopc(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs,
    prevalence: float = PREVALENCE,
) -> list[EvidenceItem]:
    """S5 occlusion AOPC (top-k deletion, k = 1..5) minus a seeded random deletion order; no interval.
    Runs on the same trigger-planted audit sample as exp.shortcut (A2 / R29)."""
    id_ = "legacy.exp.aopc"
    inp = stamp(inputs, seed=seed, config={"k_max": AOPC_K, "trigger_prevalence": prevalence},
                hashes={"attribution_method": ATTRIBUTION_SHA256})
    texts = [r["text"] for r in plant_trigger(rows[:budget], prevalence, audit_seed=seed)]
    base, attr = occlusion(predict_proba, texts)
    rng = random.Random(seed)
    orders = {
        "top": [sorted(range(len(a)), key=lambda j, a=a: -a[j]) for a in attr],
        "random": [rng.sample(range(len(a)), len(a)) for a in attr],
    }
    variants, owner = [], []
    for name in ("top", "random"):
        for i, (t, order) in enumerate(zip(texts, orders[name])):
            w = t.split()
            for k in range(1, AOPC_K + 1):
                drop = set(order[:k])
                variants.append(" ".join(x for j, x in enumerate(w) if j not in drop))
                owner.append(i)
    if not variants:
        return [insufficient(id_, "no_rows", inp, scale="difference", kind="legacy")]
    p = predict_proba(variants)
    drops = [(1.0 if toxic(base[i]) else -1.0) * (base[i] - pv) for i, pv in zip(owner, p)]
    half = len(drops) // 2
    score = sum(drops[:half]) / half - sum(drops[half:]) / half
    return [_item(id_, score, (score, score), "none", inp, len(texts))]


def legacy_safe_severe_fnr(
    predict_proba: PredictProba, rows: list[dict], *, seed: int, budget: int, inputs: EvidenceInputs
) -> list[EvidenceItem]:
    """v1 ``evaluate_behavior``: FNR on positive severe rows (min 30) with v1's Wilson interval."""
    id_, inp = "legacy.safe.severe_fnr", stamp(inputs, seed=seed)
    audit = rows[:budget]
    y_pred = [int(toxic(p)) for p in predict_proba([r["text"] for r in audit])]
    res = evaluate_behavior([int(r["label"]) for r in audit], y_pred, [int(r.get("severe", 0)) for r in audit])
    if res.status != ProbeEvaluationStatus.EVALUATED:
        return [insufficient(id_, res.flags[0], inp, kind="legacy")]
    k = round(res.severe_fnr * res.severe_n)
    return [_item(id_, res.severe_fnr, res.severe_fnr_ci, "wilson", inp, res.severe_n,
                  scale="rate", counts=Counts(k=k, n=res.severe_n))]
