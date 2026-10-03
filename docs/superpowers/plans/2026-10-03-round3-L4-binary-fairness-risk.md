# Round 3 — L4: binary fairness could not emit a fairness risk (2026-10-03)

> **Status: rejected (exploratory).** `tl-fairness-binary-v1.1` / `excess_dpd_v2` (commit
> `d4268fb`) was an exploratory candidate. It was rejected after inspecting the stored
> evidence (below) because it depends on group base rates. It is superseded by L4.1
> (`v6-eod-fairness-risk-2026`); see `2026-10-03-round3-L4.1-eod-fairness-risk.md`.
> No experiment was run under v1.1.

Branch `round-3-limitations`. Methodology `v4-disclosure-gaps-2026` → `v5-binary-fairness-risk-2026`.
The binary fairness evidence is now stamped `tl-fairness-binary-v1.1`. Multiclass
`tl-methodology-v1.0` is unchanged, and so are `ground_truth.json` and its rules.

## Rule (pre-declared; fixed in code before the stored-evidence check below)

The statistic is computed per group g, over groups with n ≥ `min_group_n`:

- `b_g = P(Ŷ=pos | g) − P(Y=pos | g)`
- `excess_dpd_v2 = max_g b_g − min_g b_g`

Bootstrap: percentile 95% CI, using the same machinery, B = 1000 and seed as DP/EO/F1.

ε = `EPSILON = 0.02`. This is the existing `tl-methodology-v1.0` practical floor used by
multiclass F-FAIR-PERF, reused unchanged. The decision mirrors F-FAIR-PERF:

| finding | condition | aspect_scoring | risks_triggered |
|---|---|---|---|
| FAIRNESS_RISK | point > ε **and** ci_lower > ε | `risk_detected` | `["F-FAIR-EXCESS-DPD"]` |
| DISPARITY_OBSERVED | point > ε, ci_lower ≤ ε | `disparity_observed` | `[]` |
| NO_MATERIAL_DISPARITY | point ≤ ε | `no_material_risk` | `[]` |
| INSUFFICIENT_EVIDENCE | < 2 groups with n ≥ min_group_n, or no CI | `not_scored` (status INSUFFICIENT_EVIDENCE) | `[]` |

- **Precedence:** G-FAIR-CI-WIDE on the DP CI keeps precedence (`mapping_blocked`),
  and in that case the finding is INSUFFICIENT_EVIDENCE.
- **No `scored_risk`:** `scored_risk_id` stays null, so this is an evidence-layer
  risk, not a scored one.
- **Wording:** status_reason states that the risk "is evidence for review, not a finding
  that the model is unfair".

## Evidence kept

All of these stay in the evidence:
- DPD, EOD, subgroup F1 spread
- `label_rate_gap` (base-rate difference)
- `dp_ci`, `eo_ci`, `f1_ci`, `excess_dpd_v2_ci`
- `groups` (per-group n/tpr/fpr/f1/positive rate), `min_group_n_observed`
- the rule itself (`fairness_rule`)

There are three excess-DPD keys:
- `excess_dpd_v1` is the original `max(DPD − label_rate_gap, 0)` over all groups.
- `excess_dpd_v2` is the new statistic above.
- `excess_dpd` keeps the v1 value, because the O/S/D fairness band and the
  severity-sweep analysis read that key. Fairness scores therefore do not move,
  except that thin-group cases now abstain.

## Stored-evidence check (descriptive, after the rule was fixed; no tuning)

Per-group label rates are recovered from the stored evidence as
`r_g = (positive_rate − fpr)/(tpr − fpr)`. The point estimates below come from the
2026-10-02 runs (run 1; the evidence is deterministic, std 0):

| model | excess_dpd_v2 | v1 | EOD |
|---|---|---|---|
| reference_toxicbert_2label / reference_hub (controls) | 0.222 | 0.000 | 0.174 |
| variant3 (0% fairness flip) | 0.186 | 0.000 | 0.065 |
| sweep_fairness_r020 | 0.126 | 0.000 | 0.129 |
| variant1 (40%) | 0.087 | 0.000 | 0.164 |
| sweep_fairness_r070 | 0.006 | 0.006 | 0.250 |
| sweep_fairness_r100 | 0.037 | 0.037 | 0.319 |
| variant5_safety / sweep_safety r025 → r100 | 0.271 / 0.213 → 0.360 | 0.000 | 0.035 / 0.061 → 0.032 |

On this evaluation set the statistic does not measure the injected fairness defect:

- **It is large on clean models.** Every model under-predicts toxicity, and the
  identity group's label rate is 0.505 higher. `b_g ≈ −(1 − TPR_g)·r_g + FPR_g·(1 − r_g)`,
  so the spread grows with the miss rate times the base-rate gap, even under equal TPR/FPR.
- **It falls as the fairness flip rate rises.** The flips push the identity group's
  predictions toward its label rate.
- **It rises with the safety (recall) defect.**

If these runs were repeated under v1.1, both controls (point 0.22, n = 539 / 2461) would
almost certainly be FAIRNESS_RISK, and so would V1 (0.087), though below the controls.
This is a point-estimate reading only; the CIs were not recomputed.

**This must be resolved before the L4 experiment runs.** Changing the statistic or ε
now would be a post-hoc decision, so it is left to a separate, explicitly
pre-registered change.
