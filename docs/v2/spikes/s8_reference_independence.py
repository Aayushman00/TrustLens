"""Spike S8: does a "reference = same probe at a bigger budget" ground truth inflate audit validity?

Per model i: true property theta_i; the probe has a model-specific method error b_i (e.g. lexicon misses the
identities the model is biased on, perturbation family the model happens to be immune to).
  audit       e_i  = theta_i + b_i  + N(0, s_audit)      small budget
  ref_same    r_i  = theta_i + b_i  + N(0, s_ref)        same code, 10x data -> shares b_i
  ref_indep   q_i  = theta_i + b'_i + N(0, s_ref)        different method / data -> independent error
Report Spearman(e, ref_same), Spearman(e, ref_indep) and Spearman(e, theta) as var(b)/var(theta) grows.
Run:  python docs/v2/spikes/s8_reference_independence.py      Out: results/s8_reference_independence.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

SEED, N_MODELS, REPS = 3, 60, 2000
OUT = Path(__file__).parent / "results" / "s8_reference_independence.json"


def main():
    rng = np.random.default_rng(SEED)
    rows = []
    for ratio in (0.0, 0.25, 0.5, 1.0, 2.0):
        acc = {"rho_same_ref": [], "rho_indep_ref": [], "rho_truth": []}
        for _ in range(REPS):
            theta = rng.normal(0, 1, N_MODELS)
            b, b2 = rng.normal(0, np.sqrt(ratio), (2, N_MODELS))
            e = theta + b + rng.normal(0, 0.3, N_MODELS)
            r = theta + b + rng.normal(0, 0.1, N_MODELS)
            q = theta + b2 + rng.normal(0, 0.1, N_MODELS)
            acc["rho_same_ref"].append(spearmanr(e, r)[0])
            acc["rho_indep_ref"].append(spearmanr(e, q)[0])
            acc["rho_truth"].append(spearmanr(e, theta)[0])
        rows.append({"var_method_error_over_var_theta": ratio,
                     **{k: round(float(np.mean(v)), 3) for k, v in acc.items()},
                     "share_reps_same_ref_passes_S1_0.7": round(float(np.mean(np.array(acc["rho_same_ref"]) >= 0.7)), 3),
                     "share_reps_truth_rho_ge_0.7": round(float(np.mean(np.array(acc["rho_truth"]) >= 0.7)), 3)})
        print(rows[-1])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"seed": SEED, "n_models": N_MODELS, "reps": REPS, "results": rows}, indent=1))


if __name__ == "__main__":
    main()
