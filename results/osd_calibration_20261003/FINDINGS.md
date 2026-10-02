# L1 — evidence → O/S/D calibration: findings (2026-10-03)

Pre-declaration: `docs/superpowers/plans/2026-10-03-round3-L1-osd-calibration.md`.
Files: `calibration/` (data manifests, `calibration_evidence.json`, `frozen_mapping.json`;
weights and train slices git-ignored, reproducible from seed 43), `heldout/analysis.json`
(first held-out run), `heldout_with_controls/analysis.json` (same frozen mapping, adds the
pre-declared reference-control rows; family results identical).

## Calibration split (seed 43)

- 3,000-row eval set + 8,000-row clean train slice from google/civil_comments, disjoint by exact
  text from every suite slice and the L5 confirm data (eval and train). Nested flips of the clean
  slice: FAIRNESS 0.3/0.6/1.0 (188/376/627 rows), SAFETY 0.3/0.6/1.0. 7 models (bert-base-uncased,
  3 ep, lr 2e-5, bs 16, wd 0.01, training seed 43). ROBUSTNESS: calibration clean model at
  attack_budget 0.02/0.04/0.06/0.10 (unperturbable rows dropped, as L6 A2).
- Held-out uses different weights (seed 42 / seed 20261003) and the L5 eval set: no model and no
  eval row is shared with calibration.

| family | s=0 | s=0.3 / 0.2 | s=0.6 / 0.4 | s=1.0 | Spearman |
|---|---|---|---|---|---|
| FAIRNESS gap | 0.0621 | 0.1538 | 0.2040 | 0.3809 | 1.0 |
| SAFETY severe_fnr | 0.2903 | 0.3405 | 0.4194 | 0.6272 | 1.0 |
| ROBUSTNESS drop (budget 0.02/0.04/0.06/0.10) | 0.0106 | 0.0173 | 0.0263 | 0.0270 | 1.0 |

## Frozen mapping `osd-map-v4-calibrated-2026-10-03`

OLS anchors (a, b), calibration sha256 `88ca2538…7e080b`, frozen 2026-10-02T22:58:31Z (UTC),
held-out evaluated 22:58:44Z, both stamped in the outputs; `check_frozen` refuses to run held-out
if `agent.OSD_MAP_V4` differs from the file.

| family | a | b |
|---|---|---|
| FAIRNESS (gap) | 0.053545 | 0.362311 |
| ROBUSTNESS (drop) | 0.009049 | 0.029506 |
| SAFETY (severe_fnr) | 0.259521 | 0.596013 |

x = clip((e − a)/(b − a), 0, 1); O = S = floor(9 − 8x + 0.5); D, abstention, card bands = v3.
Methodology `v8-osd-calibrated-map-2026`; v3 kept as `HeuristicOSDAgent(mapping="v3")`.

## Held-out (frozen L5/L6 evidence, re-mapped, not re-measured)

| family | evidence ρ | v3 O/S/D per level | v3 score (ρ, ties, range) | v4 O/S/D per level | v4 score (ρ, ties, range) | abstain |
|---|---|---|---|---|---|---|
| FAIRNESS (0, .2, .4, .7, 1.0) | 1.0 | –, –, 8/8/8, 7/7/8, 7/7/8 | 8.00, 7.32, 7.32 (−0.87, 1, 0.68) | –, –, 6/6/8, 4/4/8, 1/1/8 | 6.60, 5.04, 2.00 (−1.0, 0, 4.60) | 2/5 both |
| ROBUSTNESS (.01, .03, .05, .08) | 1.0 | 9/9/8, 9/8/8, 9/8/8, 9/7/8 | 8.65, 8.32, 8.32, 7.96 (−0.95, 1, 0.70) | 9/9/8, 6/6/8, 3/3/8, 1/1/8 | 8.65, 6.60, 4.16, 2.00 (−1.0, 0, 6.65) | 0 |
| SAFETY (0, .25, .5, .75, 1.0) | 1.0 | 7/6/8, 6/6/8, 6/6/8, 5/6/8, 4/6/8 | 6.95 … 5.77 (−0.97, 1, 1.18) | 8/8/8, 6/6/8, 5/5/8, 2/2/8, 1/1/8 | 8.00 … 2.00 (−1.0, 0, 6.00) | 0 |

Per component: v3 robustness O is constant (9) and v3 safety S is constant (6) — those levels
carry no ordering; v4 O and S have ρ = −1.0, no ties, on all three families. D is constant (8) in
every family under both mappings (ρ undefined). Monotonicity violations: 0 everywhere. Mapping
failures: 0. Controls: FAIRNESS reference (gap 0.145, F-FAIR-EOPP fired) v3 8.65 → v4 7.32;
SAFETY reference (severe_fnr 0.40) 6.60 under both.

## Evidence → risk → score

| family | evidence level | risk level | score level |
|---|---|---|---|
| FAIRNESS | gap monotone, ρ 1.0 (5/5 levels) | F-FAIR-EOPP at 0.4/0.7/1.0; 0 and 0.2 gate-blocked (G-FAIR-CI-WIDE) | v3 separation 0.68 with a 0.7=1.0 tie; v4 4.60, no tie. Both lose 0/0.2 to the gate (abstain) |
| ROBUSTNESS | drop monotone, ρ 1.0 | no risk at any level (R-ROB-PERT never fires) | v3 separation 0.70 (O fixed at 9); v4 6.65 |
| SAFETY | severe_fnr monotone, ρ 1.0 | no risk ID at any level (behaviour has none); ground-truth evidence rule flags 0.75/1.0 | v3 separation 1.18 (S fixed at 6); v4 6.00 |

Where information was lost under v3: not at the evidence layer (ρ = 1.0 in all three families).
FAIRNESS loses the two lowest levels at the gate and the 0.7/1.0 distinction in the coarse
scale(1 − gap) band; ROBUSTNESS and SAFETY lose it at the score layer (one of O/S constant, the
other moving 1–3 band steps). The risk layer carries no graded signal for ROBUSTNESS or SAFETY
at all; that is unchanged by v4.

## Known limitations

- v4's scale is relative to the calibrated defect range, not to absolute harm: a 3-percentage-point
  robustness accuracy drop maps to O = S = 1, the same as total severe-harm failure would. The
  anchors say "as bad as the largest injected defect", nothing more.
- ROBUSTNESS calibration saturates (drop 0.0263 at budget 0.06 vs 0.0270 at 0.10), and the held-out
  maximum (0.0297) lies beyond b, so the top held-out level is clipped.
- Held-out sets are small (4–5 levels per family, one model family, one dataset); ρ = −1.0 on 3–5
  points is descriptive. With S = O, S adds no independent information; D adds none in any family.
- Same eval pipeline, same base model and same flip mechanisms in calibration and held-out: this
  tests generalization across seeds/data draws, not across tasks or architectures.
- v4 changes the legacy_heuristic / llm_v1 baselines only; the default deterministic engine still
  abstains on O/S/D.
- Held-out values were known before the mapping was written (committed L5/L6); the pre-declaration
  limits the choice to two anchors per family estimated on calibration data only.
