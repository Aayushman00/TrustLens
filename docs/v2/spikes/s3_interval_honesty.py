"""Spike S3: are the v1 intervals honest at small subgroup sizes?

A. One proportion (severe FNR, group TPR), nominal 95%:
   Wald, Wilson (v1 safety), Jeffreys Beta(1/2,1/2) posterior, Clopper-Pearson, percentile bootstrap.
B. Signed gap TPR_a - TPR_b, minority positives n_a small, majority n_b = 500:
   percentile bootstrap (v1 fairness machinery), Newcombe hybrid score, Bayesian Beta-Binomial draws.
C. v1's absolute worst-group gap max_g TPR_g - min_g TPR_g with k groups when the true gap is 0 or small:
   coverage of the percentile bootstrap vs Beta-Binomial posterior draws.
D. Optional stopping: peek every 25 rows up to 1 000, stop when the interval excludes tau.
   How often does a fixed-n Wilson interval vs an anytime-valid confidence sequence end on the wrong side?

Run:  python docs/v2/spikes/s3_interval_honesty.py      Out: results/s3_interval_honesty.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

SEED, Z, B = 11, 1.959964, 1000
OUT = Path(__file__).parent / "results" / "s3_interval_honesty.json"
rng = np.random.default_rng(SEED)


def wilson(k, n):
    p = k / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return np.clip(c - h, 0, 1), np.clip(c + h, 0, 1)


def wald(k, n):
    p = k / n
    h = Z * np.sqrt(p * (1 - p) / n)
    return p - h, p + h


def jeffreys(k, n):
    return stats.beta.ppf(0.025, k + 0.5, n - k + 0.5), stats.beta.ppf(0.975, k + 0.5, n - k + 0.5)


def clopper(k, n):
    lo = np.where(k == 0, 0.0, stats.beta.ppf(0.025, np.maximum(k, 1e-9), n - k + 1))
    hi = np.where(k == n, 1.0, stats.beta.ppf(0.975, k + 1, np.maximum(n - k, 1e-9)))
    return lo, hi


def boot_prop(k, n):
    # percentile bootstrap of a proportion = quantiles of Binomial(n, k/n)/n
    draws = rng.binomial(n, k[:, None] / n, size=(len(k), B)) / n
    return np.quantile(draws, 0.025, axis=1), np.quantile(draws, 0.975, axis=1)


def part_a(trials=4000):
    rows = []
    for p in (0.05, 0.10, 0.30, 0.50):
        for n in (10, 20, 30, 50, 100, 300):
            k = rng.binomial(n, p, trials)
            row = {"p": p, "n": n}
            for name, fn in (("wald", wald), ("wilson", wilson), ("jeffreys", jeffreys),
                             ("clopper_pearson", clopper), ("bootstrap", boot_prop)):
                lo, hi = fn(k, n)
                row[name] = round(float(np.mean((lo <= p) & (p <= hi))), 3)
            rows.append(row)
    return rows


def newcombe(ka, na, kb, nb):
    la, ua = wilson(ka, na)
    lb, ub = wilson(kb, nb)
    pa, pb = ka / na, kb / nb
    d = pa - pb
    return d - np.sqrt((pa - la) ** 2 + (ub - pb) ** 2), d + np.sqrt((ua - pa) ** 2 + (pb - lb) ** 2)


def part_b(trials=3000):
    rows = []
    pb_true, nb = 0.60, 500
    for gap in (0.0, 0.10, 0.20):
        pa_true = pb_true - gap
        for na in (10, 20, 40, 80, 200):
            ka, kb = rng.binomial(na, pa_true, trials), rng.binomial(nb, pb_true, trials)
            truth = pa_true - pb_true
            lo, hi = newcombe(ka, na, kb, nb)
            cov_n = np.mean((lo <= truth) & (truth <= hi))
            bd = rng.binomial(na, ka[:, None] / na, (trials, B)) / na - rng.binomial(nb, kb[:, None] / nb, (trials, B)) / nb
            cov_b = np.mean((np.quantile(bd, .025, 1) <= truth) & (truth <= np.quantile(bd, .975, 1)))
            pd = rng.beta(ka[:, None] + .5, na - ka[:, None] + .5, (trials, B)) - rng.beta(kb[:, None] + .5, nb - kb[:, None] + .5, (trials, B))
            cov_p = np.mean((np.quantile(pd, .025, 1) <= truth) & (truth <= np.quantile(pd, .975, 1)))
            rows.append({"true_gap": gap, "n_minority_pos": na, "bootstrap": round(float(cov_b), 3),
                         "newcombe": round(float(cov_n), 3), "beta_binomial": round(float(cov_p), 3)})
    return rows


def part_c(trials=1500):
    rows = []
    for k_groups in (2, 4):
        for gap in (0.0, 0.05, 0.15):
            for n_pos in (20, 50, 200):
                ps = np.full(k_groups, 0.6); ps[0] -= gap
                truth = gap
                ks = rng.binomial(n_pos, ps, (trials, k_groups))
                bd = rng.binomial(n_pos, ks[:, :, None] / n_pos, (trials, k_groups, B)) / n_pos
                bgap = bd.max(1) - bd.min(1)
                pdr = rng.beta(ks[:, :, None] + .5, n_pos - ks[:, :, None] + .5, (trials, k_groups, B))
                pgap = pdr.max(1) - pdr.min(1)
                point = (ks.max(1) - ks.min(1)) / n_pos
                cov = lambda d: float(np.mean((np.quantile(d, .025, 1) <= truth) & (truth <= np.quantile(d, .975, 1))))
                rows.append({"k_groups": k_groups, "true_abs_gap": gap, "n_pos_per_group": n_pos,
                             "mean_point_estimate": round(float(point.mean()), 3),
                             "bootstrap_cov": round(cov(bgap), 3), "beta_binomial_cov": round(cov(pgap), 3),
                             "upper_only_bootstrap_cov": round(float(np.mean(np.quantile(bgap, .95, 1) >= truth)), 3)})
    return rows


def cs_radius(t, alpha=0.05, rho=None):
    # Two-sided normal-mixture confidence sequence for the mean of [0,1] variables (sub-Gaussian, sigma = 1/2),
    # Howard, Ramdas, McAuliffe, Sekhon (2021). alpha/2 per side: conservative. Radius on the mean scale.
    v = 0.25 * t
    rho = rho if rho is not None else 0.25 * 400  # tuned for t ~ 400
    return np.sqrt((v + rho) * np.log((v + rho) / (rho * (alpha / 2) ** 2))) / t


def part_d(trials=4000, tau=0.25):
    rows = []
    for p in (0.25, 0.30):  # p == tau: any "excludes tau" stop is an error; p = 0.30: stopping below tau is wrong
        x = rng.random((trials, 1000)) < p
        s = np.cumsum(x, 1)
        ts = np.arange(25, 1001, 25)
        wrong = {"wilson_peeking": 0, "confseq_peeking": 0, "wilson_fixed_1000": 0}
        stopped_cs = 0
        for i in range(trials):
            k = s[i, ts - 1]
            lo, hi = wilson(k, ts)
            stop = np.where((lo > tau) | (hi < tau))[0]
            if len(stop) and (hi[stop[0]] < tau if p >= tau else lo[stop[0]] > tau):
                wrong["wilson_peeking"] += 1
            r = cs_radius(ts)
            m = k / ts
            stop = np.where((m - r > tau) | (m + r < tau))[0]
            if len(stop):
                stopped_cs += 1
                if (m[stop[0]] + r[stop[0]] < tau) if p >= tau else (m[stop[0]] - r[stop[0]] > tau):
                    wrong["confseq_peeking"] += 1
            lo1, hi1 = wilson(s[i, -1], 1000)
            if (hi1 < tau) if p >= tau else (lo1 > tau):
                wrong["wilson_fixed_1000"] += 1
        rows.append({"true_p": p, "tau": tau, **{k: round(v / trials, 4) for k, v in wrong.items()},
                     "confseq_decided_share": round(stopped_cs / trials, 3),
                     "cs_radius_at_1000": round(float(cs_radius(np.array([1000]))[0]), 4),
                     "wilson_halfwidth_at_1000": round(float((wilson(np.array([int(p * 1000)]), 1000)[1] - wilson(np.array([int(p * 1000)]), 1000)[0])[0] / 2), 4)})
    return rows


def main():
    out = {"seed": SEED, "nominal": 0.95, "bootstrap_B": B,
           "A_one_proportion": part_a(), "B_signed_gap": part_b(),
           "C_abs_worst_group_gap": part_c(), "D_optional_stopping": part_d()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
