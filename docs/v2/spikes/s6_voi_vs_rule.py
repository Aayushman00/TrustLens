"""Spike S6 (+ T1 decision-rule question): does VOI planning or expected-loss deciding beat simple rules?

Each audited model has per-dimension violation-relevant rates p_d (e.g. severe FNR, counterfactual flip rate).
Evidence is Bernoulli rows bought in batches at cost c per row. Loss follows spec 03:
  ADOPT     sum_d stake_d * 1[p_d > tau_d]
  CONTROLS  control_cost + sum_d stake_d * (1 - credit_d) * 1[p_d > tau_d]
  REJECT    reject_cost
Total realised loss = decision loss + c * rows bought.

Policies
  voi        Beta posterior per dimension; myopic preposterior VOI over (dimension, batch size); stop when no net gain;
             then Bayes action (minimum posterior expected loss).                         [spec 03 as written]
  rule       Wilson 95% per dimension; start 100 rows; double rows on every dimension whose CI straddles tau;
             stop when none straddles or the cap is hit; then the INTERVAL action below.  [simple baseline]
  rule_bayes same sampling as `rule`, but the final action is the Bayes action.          [isolates the decision part]
  fixed_bayes / fixed_rule  1 000 rows per dimension, then Bayes / interval action.
  oracle     knows p; picks the best action, buys nothing.
INTERVAL action: REJECT if any high-stake dimension's lower bound > tau; ADOPT if every upper bound < tau;
                 else ADOPT_WITH_CONTROLS.

Scenarios vary stakes, row cost and prior misspecification (the policy's prior differs from the world).
Run:  python docs/v2/spikes/s6_voi_vs_rule.py      Out: results/s6_voi_vs_rule.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

SEED, TRIALS, CAP = 5, 1500, 3200
BATCHES = (100, 200, 400, 800, 1600)
Z = 1.959964
OUT = Path(__file__).parent / "results" / "s6_voi_vs_rule.json"


def scenario(name, stakes, tau, credit, control_cost, reject_cost, c, world_prior, policy_prior):
    return dict(name=name, stakes=np.array(stakes, float), tau=np.array(tau, float), credit=np.array(credit, float),
                control_cost=control_cost, reject_cost=reject_cost, c=c,
                world_prior=world_prior, policy_prior=policy_prior)


MIX = ("mix", 0.6, (2, 30), (0.10, 0.60))       # 60% near-clean Beta(2,30), 40% defective U(.1,.6)
SCENARIOS = [
    scenario("3dim_moderation_like", [5, 4, 2], [.15, .10, .15], [.6, .5, .3], 1.5, 6.0, 2e-4, MIX, (1, 4)),
    scenario("3dim_high_stakes", [40, 20, 2], [.10, .10, .15], [.5, .5, .3], 3.0, 10.0, 2e-4, MIX, (1, 4)),
    scenario("3dim_expensive_rows", [5, 4, 2], [.15, .10, .15], [.6, .5, .3], 1.5, 6.0, 2e-3, MIX, (1, 4)),
    scenario("1dim_safety", [10], [.25], [.6], 1.5, 3.0, 2e-4, MIX, (1, 4)),
    scenario("3dim_prior_misspecified", [5, 4, 2], [.15, .10, .15], [.6, .5, .3], 1.5, 6.0, 2e-4,
             ("mix", 0.2, (2, 30), (0.10, 0.60)), (1, 10)),  # world mostly defective, policy prior optimistic
]


def draw_world(rng, prior, d):
    _, w_clean, (a, b), (lo, hi) = prior
    clean = rng.random(d) < w_clean
    return np.where(clean, rng.beta(a, b, d), rng.uniform(lo, hi, d))


def terminal(sc, pv):  # pv = P(p_d > tau_d) per dimension; returns expected loss per action
    adopt = float(np.sum(sc["stakes"] * pv))
    ctrl = sc["control_cost"] + float(np.sum(sc["stakes"] * (1 - sc["credit"]) * pv))
    return np.array([adopt, ctrl, sc["reject_cost"]])


def realised(sc, action, p):
    v = (p > sc["tau"]).astype(float)
    return [float(np.sum(sc["stakes"] * v)),
            sc["control_cost"] + float(np.sum(sc["stakes"] * (1 - sc["credit"]) * v)),
            sc["reject_cost"]][action]


def pviol(sc, a, b):
    return stats.beta.sf(sc["tau"], a, b)


def voi_policy(sc, p, rng):
    d = len(p)
    a0, b0 = sc["policy_prior"]
    a, b, n = np.full(d, a0, float), np.full(d, b0, float), np.zeros(d, int)
    while True:
        pv = pviol(sc, a, b)
        cur = terminal(sc, pv).min()
        best, arg = 0.0, None
        for j in range(d):
            for m in BATCHES:
                if n[j] + m > CAP:
                    continue
                k = np.arange(m + 1)
                w = stats.betabinom.pmf(k, m, a[j], b[j])
                pj = stats.beta.sf(sc["tau"][j], a[j] + k, b[j] + m - k)
                exp_after = 0.0
                pv_k = np.tile(pv, (m + 1, 1)); pv_k[:, j] = pj
                losses = np.stack([pv_k @ sc["stakes"],
                                   sc["control_cost"] + pv_k @ (sc["stakes"] * (1 - sc["credit"])),
                                   np.full(m + 1, sc["reject_cost"])], 1).min(1)
                exp_after = float(w @ losses)
                net = cur - exp_after - sc["c"] * m
                if net > best:
                    best, arg = net, (j, m)
        if arg is None:
            return int(np.argmin(terminal(sc, pv))), int(n.sum())
        j, m = arg
        k = rng.binomial(m, p[j])
        a[j] += k; b[j] += m - k; n[j] += m


def wilson(k, n):
    ph = k / n
    dd = 1 + Z**2 / n
    c = (ph + Z**2 / (2 * n)) / dd
    h = Z * np.sqrt(ph * (1 - ph) / n + Z**2 / (4 * n**2)) / dd
    return c - h, c + h


def interval_action(sc, lo, hi):
    high = sc["stakes"] >= np.median(sc["stakes"])
    if np.any((lo > sc["tau"]) & high):
        return 2
    if np.all(hi < sc["tau"]):
        return 0
    return 1


def rule_sampling(sc, p, rng, start=100):
    d = len(p)
    n, k = np.full(d, start), rng.binomial(start, p)
    while True:
        lo, hi = wilson(k, n)
        straddle = (lo <= sc["tau"]) & (hi >= sc["tau"]) & (n * 2 <= CAP)
        if not straddle.any():
            return n, k, lo, hi
        for j in np.where(straddle)[0]:
            k[j] += rng.binomial(n[j], p[j]); n[j] *= 2


def bayes_action(sc, n, k):
    a0, b0 = sc["policy_prior"]
    return int(np.argmin(terminal(sc, pviol(sc, a0 + k, b0 + n - k))))


def run(sc, rng):
    d = len(sc["stakes"])
    res = {k: [] for k in ("voi", "rule", "rule_bayes", "fixed_bayes", "fixed_rule", "oracle")}
    rows = {k: [] for k in res}
    false_adopt = {k: 0 for k in res}
    for _ in range(TRIALS):
        p = draw_world(rng, sc["world_prior"], d)
        act, nn = voi_policy(sc, p, rng)
        out = {"voi": (act, nn)}
        n, k, lo, hi = rule_sampling(sc, p, rng)
        out["rule"] = (interval_action(sc, lo, hi), int(n.sum()))
        out["rule_bayes"] = (bayes_action(sc, n, k), int(n.sum()))
        nf = np.full(d, 1000); kf = rng.binomial(1000, p)
        lo, hi = wilson(kf, nf)
        out["fixed_bayes"] = (bayes_action(sc, nf, kf), int(nf.sum()))
        out["fixed_rule"] = (interval_action(sc, lo, hi), int(nf.sum()))
        out["oracle"] = (int(np.argmin([realised(sc, i, p) for i in range(3)])), 0)
        viol = bool(np.any(p > sc["tau"]))
        for name, (act, nn) in out.items():
            res[name].append(realised(sc, act, p) + sc["c"] * nn)
            rows[name].append(nn)
            false_adopt[name] += int(act == 0 and viol)
    summ = {}
    base = np.array(res["rule"])
    for name in res:
        x = np.array(res[name])
        diff = x - base
        se = diff.std(ddof=1) / np.sqrt(len(diff))
        summ[name] = {"mean_total_loss": round(float(x.mean()), 3), "se": round(float(x.std(ddof=1) / np.sqrt(len(x))), 3),
                      "minus_rule": round(float(diff.mean()), 3), "minus_rule_ci95": [round(float(diff.mean() - 1.96 * se), 3), round(float(diff.mean() + 1.96 * se), 3)],
                      "mean_rows": round(float(np.mean(rows[name])), 0),
                      "false_adopt_rate": round(false_adopt[name] / TRIALS, 3)}
    return summ


def main():
    rng = np.random.default_rng(SEED)
    out = {"seed": SEED, "trials": TRIALS, "cap_rows_per_dim": CAP, "results": {}}
    for sc in SCENARIOS:
        out["results"][sc["name"]] = run(sc, rng)
        print(sc["name"], json.dumps(out["results"][sc["name"]], indent=0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
