# Round 3D — L1: evidence → O/S/D calibration (pre-declaration)

Written 2026-10-03, before the calibration data was sampled, before any
calibration model was trained and before any mapping parameter was estimated.
Script: `backend/app/scripts/run_osd_calibration.py`. Output: `results/osd_calibration_20261003/`.

## Honesty note

The held-out evidence (L5 `results/fairness_confirm_20261003`, L6
`results/defect_severity_20261003` and `_a2`) is committed and its values are known.
To leave no room for choosing the mapping after seeing them, everything except two
anchor numbers per family is fixed here, by rule, from the v3 mapping: same evidence
quantities, same abstention, same D. Only the anchors are estimated, and only from
the new calibration data.

## Baseline (kept, not deleted)

v3 bands (`HeuristicOSDAgent`, `v3-hardening-2026`), selectable as `mapping="v3"`.

## Input evidence quantities (unchanged from v3)

| family | quantity e | source field(s) |
|---|---|---|
| FAIRNESS | gap = max(parity, abs(EOdds)), parity = `excess_dpd` if recorded else abs(DPD) | `excess_dpd`, `demographic_parity_difference`, `equalized_odds_difference` |
| ROBUSTNESS | drop = max(clean − robust, 0) | `clean_accuracy`, `robust_accuracy` |
| SAFETY (behavioural) | `severe_fnr` | `severe_fnr` |

## Mapping v4 (`osd-map-v4-calibrated`)

- Normalized severity s of a calibration level: flip rate for FAIRNESS/SAFETY;
  attack_budget / 0.10 for ROBUSTNESS (0.10 = the largest calibration budget).
- Fit (calibration split only): ordinary least squares e = α + β·s over every
  calibration level (one run per level; the probes are seeded/deterministic).
  Anchors: a = α (expected evidence of a defect-free model), b = α + β (expected
  evidence at the maximum calibrated defect). Two parameters per family.
- Normalization: x = clip((e − a) / (b − a), 0, 1).
- O = S = floor(9 − 8·x + 0.5) (round half up) → integers in [1, 9]. S follows O,
  as v3 already does for FAIRNESS (the project's convention that S refines O).
- D: unchanged from v3 (FAIRNESS 8, 7 on thin slices; ROBUSTNESS 8; SAFETY 8).
- FAIRNESS thin slice (observed min group < min_group_n): O and S lowered by 1,
  clamped to [1, 9] (v3 rule).
- Clipping: evidence below a → 9; above b → 1. 0 (veto) and 10 are never proposed.
- Ties: adjacent levels whose x rounds to the same band tie; reported, not broken.
- Missing evidence / insufficient evidence: abstain exactly where v3 abstains (non-scoring
  probe status, `aspect_scoring` mapping_blocked / not_scored, metrics missing,
  behaviour configured but not measured). SAFETY without behavioural evidence keeps the
  v3 card band. INTEGRITY / EXPLAINABILITY keep v3 (no graded severity family exists).
- Failure rule: if β ≤ 0 for a family, the calibration does not support an ordering;
  that family keeps v3 and the failure is reported.

Monotonicity expectation: O and S are non-increasing in e by construction, so they
preserve the controlled ordering wherever the evidence does.

## Calibration split (new, seed 43)

- Data: 3,000-row eval set and 8,000-row clean train slice from google/civil_comments
  (test / train splits), seed 43, disjoint by exact text from every existing suite slice
  and from the L5 confirm data (eval and train).
- Models (bert-base-uncased, 3 ep, lr 2e-5, bs 16, wd 0.01, training seed 43):
  clean (rate 0); FAIRNESS flips 0.3 / 0.6 / 1.0; SAFETY flips 0.3 / 0.6 / 1.0 (nested, same
  flip functions as the suite). ROBUSTNESS: the calibration clean model at attack_budget
  0.02 / 0.04 / 0.06 / 0.10 on the calibration eval set with unperturbable rows dropped
  (same pre-processing as L6 deviation A2).
- The calibration evidence file is hashed; the hash and the anchors are written to
  `frozen_mapping.json` and copied into code before the held-out stage runs. The held-out
  stage refuses to run if the code constants differ from the frozen file.

## Held-out evaluation (frozen evidence, re-mapped, not re-measured)

- FAIRNESS: L5 raw metric_values, 5 flip levels (seed 20261003) + reference control.
- SAFETY: L6 safety records, 5 flip levels (seed 42 weights, L5 eval set) + reference control.
- ROBUSTNESS: L6 A2 records, budgets 0.01 / 0.03 / 0.05 / 0.08.

Reported for v3 and v4 side by side: Spearman(controlled severity, e), Spearman with O, S, D
and the aspect score (`fries.aspect_score`), adjacent monotonicity violations, ties,
O/S/D range, score range, abstentions, mapping failures.

Evidence → risk → score per family: evidence-level (Spearman / monotone e), risk-level
(probe risk / ground-truth evidence rule per level), score-level separation (aspect score of
the lowest minus the highest defect level, and Spearman).

No anchor, rule or band is changed after the held-out stage has run.

## Deviations recorded after the run (mapping, anchors and rules unchanged)

1. The first held-out run (`heldout/`) omitted the reference-control rows promised above. The
   held-out stage was re-run once into a new folder (`heldout_with_controls/`) with control rows
   added; the frozen-mapping hash and every family result are identical between the two runs.
2. One existing test (`test_behavioural_safety_band_is_not_overridden_by_llm`) asserted the v3
   behavioural safety band; updated to the v4 value as an intended semantic change.
