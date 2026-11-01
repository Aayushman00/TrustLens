"""Spike S9: worked example of the revised decision layer (DESIGN_SYNTHESIS section 5), reproduced by script.

Revised engine, in order:
  1. Tier A integrity finding  -> REJECT, stop (ADR 0014).
  2. Each rate-type evidence item carries counts (k, n); posterior = Beta(k + 1/2, n - k + 1/2) (Jeffreys).
     Tolerances are stated on the estimand's own scale (no fitted link).
  3. P(violation_d) = P(rate_d > tau_d); Bayes action = argmin of the three spec-03 expected losses.
  4. Interval view (always shown): Bonferroni-adjusted Jeffreys interval over the planned looks (<= 3).
  5. Follow-up rule (replaces the VOI planner): if any dimension has 0.05 < P(violation) < 0.95 and the
     look budget is not spent, double rows for those dimensions; else commit to the Bayes action.
  6. EVPI per dimension is reported (value of knowing that dimension exactly), not used to plan.
Inputs marked [v1] come from frozen v1 results; the others are illustrative and labelled so.
Run:  python docs/v2/spikes/s9_worked_example.py      Out: results/s9_worked_example.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

SEED, S, LOOKS = 9, 200_000, 3
rng = np.random.default_rng(SEED)
PROFILE = {  # content-moderation preset (spec 08 numbers kept where they still apply)
    "fairness_mention": {"tau": 0.05, "stake": 4, "credit": 0.5},
    "robustness_typo_flip": {"tau": 0.15, "stake": 2, "credit": 0.3},
    "safety_severe_miss": {"tau": 0.40, "stake": 5, "credit": 0.6},
    "shortcut_insertion_flip": {"tau": 0.20, "stake": 1, "credit": 0.5},
}
CONTROL_COST, REJECT_COST = 1.5, 6.0
ROUND1 = {  # (k, n)
    "fairness_mention": (5, 76),          # illustrative: identity-mention flips on 76 base sentences
    "robustness_typo_flip": (61, 1000),   # illustrative
    "safety_severe_miss": (100, 282),     # [v1] unitary/toxic-bert severe FNR 0.355 on 282 severe rows
    "shortcut_insertion_flip": (3, 300),  # illustrative
}
TRUE_FAIRNESS_RATE = 0.040                # illustrative: what the extra rows are drawn from in round 2


def evaluate(ev, look):
    names = list(PROFILE)
    draws = np.stack([rng.beta(k + .5, n - k + .5, S) for k, n in (ev[d] for d in names)], 1)
    tau = np.array([PROFILE[d]["tau"] for d in names])
    stake = np.array([PROFILE[d]["stake"] for d in names])
    credit = np.array([PROFILE[d]["credit"] for d in names])
    viol = (draws > tau).astype(float)
    losses = {"ADOPT": viol @ stake, "ADOPT_WITH_CONTROLS": CONTROL_COST + viol @ (stake * (1 - credit)),
              "REJECT": np.full(S, REJECT_COST)}
    exp = {a: round(float(v.mean()), 3) for a, v in losses.items()}
    best = min(exp, key=exp.get)
    # EVPI_d: expected loss now - expected loss if dimension d were known exactly
    evpi = {}
    for j, d in enumerate(names):
        others = np.delete(np.arange(len(names)), j)
        pv_o = viol[:, others].mean(0)
        def best_given(vj):
            a = pv_o @ stake[others] + vj * stake[j]
            c = CONTROL_COST + pv_o @ (stake[others] * (1 - credit[others])) + vj * stake[j] * (1 - credit[j])
            return min(a, c, REJECT_COST)
        pj = viol[:, j].mean()
        evpi[d] = round(exp[best] - (pj * best_given(1.0) + (1 - pj) * best_given(0.0)), 3)
    alpha = 0.05 / LOOKS
    rows = {}
    for j, d in enumerate(names):
        k, n = ev[d]
        lo, hi = stats.beta.ppf([alpha / 2, 1 - alpha / 2], k + .5, n - k + .5)
        rows[d] = {"k": k, "n": n, "estimate": round(k / n, 4), "interval_bonf": [round(lo, 4), round(hi, 4)],
                   "tau": float(tau[j]), "p_violation": round(float(viol[:, j].mean()), 3),
                   "loss_share_adopt": round(float(stake[j] * viol[:, j].mean()), 3)}
    unresolved = [d for d in names if 0.05 < rows[d]["p_violation"] < 0.95]
    action = "COLLECT_MORE_EVIDENCE" if unresolved and look < LOOKS else best
    return {"look": look, "per_dimension": rows, "expected_loss": exp, "bayes_terminal_action": best,
            "action": action, "unresolved": unresolved, "evpi": evpi}


def main():
    out = {"seed": SEED, "posterior_draws": S, "profile": PROFILE, "control_cost": CONTROL_COST,
           "reject_cost": REJECT_COST, "rounds": []}
    ev = dict(ROUND1)
    for look in range(1, LOOKS + 1):
        r = evaluate(ev, look)
        out["rounds"].append(r)
        print(json.dumps(r, indent=1))
        if r["action"] != "COLLECT_MORE_EVIDENCE":
            break
        for d in r["unresolved"]:  # double rows; new rows drawn from the (illustrative) true rate
            k, n = ev[d]
            p = TRUE_FAIRNESS_RATE if d == "fairness_mention" else k / n
            ev[d] = (k + int(rng.binomial(n, p)), 2 * n)
    # Tier A short-circuit, same evidence
    out["tier_a_variant"] = {"finding": "int.format_safety: builtins.eval in pytorch_model.bin", "action": "REJECT",
                             "expected_loss": {"ADOPT": "inf", "ADOPT_WITH_CONTROLS": "inf", "REJECT": REJECT_COST}}
    o = Path(__file__).parent / "results" / "s9_worked_example.json"
    o.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
