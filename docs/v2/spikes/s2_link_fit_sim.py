"""Spike S2: how many TrustBench models does a per-dimension evidence->risk link need?

World (one dimension, one evidence statistic per model):
  true risk r_i      ~ mixture: 70% near-clean Beta(1, 12), 30% defective U(0.10, 0.60)
  reference  r*_i    = r_i + N(0, 0.02)          (the expensive measurement, small noise)
  audit      e_i     = h(r_i) + N(0, sigma)      (cheap measurement)

Two shapes of h:
  W1 "same statistic":   h(r) = r + 0.02          (reference = same probe on bigger, shifted data)
  W2 "different scale":  h(r) = 0.6 * r ** 0.6    (evidence is a nonlinear proxy of the risk)

Links fitted on N training models (split by model), scored on 4 000 fresh models:
  identity   r_hat = e                           (no fitting at all)
  isotonic   sklearn IsotonicRegression(e -> r*)
  logistic   monotone 2-parameter: r_hat = sigmoid(a + b * logit(e)), b >= 0
  oracle     true h^-1                           (lower bound)

Metrics: MAE(r_hat, r) and decision error at tolerance 0.15: 1[r_hat > 0.15] != 1[r > 0.15].
Run:  python docs/v2/spikes/s2_link_fit_sim.py      Out: results/s2_link_fit_sim.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit, logit
from sklearn.isotonic import IsotonicRegression

SEED, REPS, TAU, N_TEST = 7, 200, 0.15, 4000
OUT = Path(__file__).parent / "results" / "s2_link_fit_sim.json"
WORLDS = {
    "W1_same_statistic": (lambda r: r + 0.02, lambda e: e - 0.02),
    "W2_nonlinear_proxy": (lambda r: 0.6 * np.clip(r, 0, 1) ** 0.6,
                           lambda e: (np.clip(e, 1e-9, None) / 0.6) ** (1 / 0.6)),
}


def draw_models(rng, n):
    defect = rng.random(n) < 0.30
    r = np.where(defect, rng.uniform(0.10, 0.60, n), rng.beta(1, 12, n))
    return r, np.clip(r + rng.normal(0, 0.02, n), 0, 1)


def fit_logistic(e, y):
    x = logit(np.clip(e, 1e-3, 1 - 1e-3))
    yy = np.clip(y, 1e-3, 1 - 1e-3)
    sol = least_squares(lambda p: expit(p[0] + p[1] * x) - yy, x0=[0.0, 1.0],
                        bounds=([-20, 0], [20, 20]))
    a, b = sol.x
    return lambda q: expit(a + b * logit(np.clip(q, 1e-3, 1 - 1e-3)))


def score(r_hat, r):
    r_hat = np.clip(r_hat, 0, 1)
    return float(np.mean(np.abs(r_hat - r))), float(np.mean((r_hat > TAU) != (r > TAU)))


def main():
    rng = np.random.default_rng(SEED)
    out = {"seed": SEED, "reps": REPS, "tau": TAU, "results": []}
    for wname, (h, h_inv) in WORLDS.items():
        for sigma in (0.02, 0.05, 0.10):
            for n in (10, 20, 40, 60, 100, 200):
                acc = {k: [] for k in ("identity", "isotonic", "logistic", "oracle")}
                for _ in range(REPS):
                    r_tr, ref_tr = draw_models(rng, n)
                    e_tr = h(r_tr) + rng.normal(0, sigma, n)
                    r_te, _ = draw_models(rng, N_TEST)
                    e_te = h(r_te) + rng.normal(0, sigma, N_TEST)
                    iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(e_tr, ref_tr)
                    acc["identity"].append(score(e_te, r_te))
                    acc["isotonic"].append(score(iso.predict(e_te), r_te))
                    acc["logistic"].append(score(fit_logistic(e_tr, ref_tr)(e_te), r_te))
                    acc["oracle"].append(score(h_inv(e_te), r_te))
                row = {"world": wname, "sigma": sigma, "n_models": n}
                for k, v in acc.items():
                    v = np.array(v)
                    row[k] = {"mae": round(v[:, 0].mean(), 4), "mae_p90": round(np.quantile(v[:, 0], 0.9), 4),
                              "dec_err": round(v[:, 1].mean(), 4)}
                out["results"].append(row)
                print(wname, sigma, n, {k: row[k]["mae"] for k in acc}, {k: row[k]["dec_err"] for k in acc})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
