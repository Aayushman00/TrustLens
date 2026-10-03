# Round 3 — L5: second fairness validation, L4.1 confirmatory run (2026-10-03)

- **Pre-registration:** `2026-10-03-round3-L4.1-confirmatory-prereg.md`, FROZEN at
  `8f009fb` before any data existed.
- **Rule under test:** `v6-eod-fairness-risk-2026` / `tl-fairness-binary-v1.2`
  (F-FAIR-EOPP), unchanged. ε = 0.02, wide-CI gate 0.15, B = 1000, seed 42, same
  decision ordering. Nothing was changed after seeing these results.
- **Outputs:** `results/fairness_confirm_20261003/`
  - `data/` and `ground_truth.json`, written before training
  - `models/` (weights not committed)
  - `analysis/` (`analysis.json`, `analysis.md`, `raw/` with 3 runs per model)

## Configuration

| item | value |
|---|---|
| Data seed / training seed | 20261003 / 20261003 |
| Eval set | 3,000 rows, civil_comments test split, 20% toxic. 0 exact-text overlap with the suite's eval set and every suite train slice (11,590 texts excluded) |
| Train slice | 8,000 rows (7,995 unique texts; civil_comments has duplicates), disjoint from the suite and from the new eval set |
| Flips (nested) | 0.2 → 115 rows, 0.4 → 230, 0.7 → 403, 1.0 → 576 (identity_ref = 1 ∧ label = 0 → 1) |
| Training | bert-base-uncased, 3 epochs, lr 2e-5, bs 16, wd 0.01, RTX 4060 laptop GPU, fp16 |
| Reproducibility | A second data prep with the same seed is byte-identical (all data files and `ground_truth.json`) |
| Driver | `app.scripts.run_fairness_confirm`: production `FairnessProbe` in-process with `LocalHFBackend`, 3 runs per model, no LLM |

Weight sha256:

| model | sha256 |
|---|---|
| clean_control | `de073ef8…` |
| fairness_r020 | `9d8ad864…` |
| fairness_r040 | `2147a72f…` |
| fairness_r070 | `712c70cb…` |
| fairness_r100 | `a36c11fa…` |
| reference_toxicbert_2label | `7732b854…` (existing weights, unchanged) |

## Results

Groups are `identity_ref` 0 and 1, each with n ≥ 30 and positives present. The groups
are the same for every model:
- **n:** g0 = 2,500, g1 = 500.
- **Positive-label rate:** g0 = 0.113, g1 = 0.636. The base rates differ a lot.

All three runs of every model were identical (`repeatable = true`).

| model | flip | TPR g0 / g1 | DPD | EOD | EOD 95% CI | CI width | FPR gap | F1 spread | finding | aspect_scoring | risks | flagged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| clean_control | 0 | 0.511 / 0.616 | 0.350 | 0.106 | [0.028, 0.181] | **0.153** | 0.075 | 0.134 | INSUFFICIENT_EVIDENCE (G-FAIR-CI-WIDE) | mapping_blocked | [] | no |
| fairness_r020 | 0.2 | 0.553 / 0.667 | 0.381 | 0.113 | [0.033, 0.189] | 0.156 | 0.090 | 0.138 | INSUFFICIENT_EVIDENCE (G-FAIR-CI-WIDE) | mapping_blocked | [] | no |
| fairness_r040 | 0.4 | 0.578 / 0.745 | 0.442 | 0.167 | [0.092, 0.239] | 0.147 | 0.142 | 0.182 | FAIRNESS_RISK | risk_detected | F-FAIR-EOPP | yes |
| fairness_r070 | 0.7 | 0.606 / 0.811 | 0.513 | 0.205 | [0.132, 0.277] | 0.145 | 0.252 | 0.211 | FAIRNESS_RISK | risk_detected | F-FAIR-EOPP | yes |
| fairness_r100 | 1.0 | 0.656 / 0.862 | 0.564 | 0.206 | [0.140, 0.266] | 0.126 | 0.347 | 0.226 | FAIRNESS_RISK | risk_detected | F-FAIR-EOPP | yes |
| reference_toxicbert_2label | control | 0.330 / 0.475 | 0.272 | 0.145 | [0.069, 0.217] | 0.148 | 0.037 | 0.169 | FAIRNESS_RISK | risk_detected | F-FAIR-EOPP | **yes** |

## Hypotheses (frozen criteria)

| ID | outcome | detail |
|---|---|---|
| H1 — no control flagged | **FAILS** | `reference_toxicbert_2label` is flagged: EOD 0.145, CI lower 0.069 > ε |
| H2 — rates ≥ 0.4 flagged | holds | recall 3/3 (r040, r070, r100) |
| H3 — EOD rises with rate | holds | Spearman ρ = 1.0 over 5 levels, 0 adjacent decreases. The step 0.7 → 1.0 is nearly flat (0.205 → 0.206) |
| H4 — gate behaviour | descriptive | clean_control and r020 hit G-FAIR-CI-WIDE in 3/3 runs (`mapping_blocked`); r040, r070, r100 and the reference abstained 0/3 times |

## Interpretation (descriptive; the rule is not changed)

The analysis separates three things:
- **injected defect:** the flip rate;
- **observed disparity:** EOD and its CI, a property of the model on this eval set;
- **auditor detection:** F-FAIR-EOPP under the frozen rule.

**Control false-positive behaviour (H1 fails)**
- The flag on `reference_toxicbert_2label` is a false positive only with respect to the
  injected-defect ground truth. The model has no injected defect.
- It does show an observed TPR gap of 0.145, with a CI clear of ε. The external
  model's recall really is lower on non-identity toxic comments in this sample.
- The frozen rule detects observed disparity, not injected defects. A real model that
  serves as a "clean control" is not thereby fair. This is the expected failure mode of
  a disparity rule used as a defect detector.
- It is reported as an H1 failure, as pre-registered.

**The clean control is not "fair"**
- It has an observed EOD of 0.106, with CI lower bound 0.028 > ε. It escapes a flag
  only because the CI width (0.1529) exceeds the 0.15 gate by 0.003, so the rule
  abstains.
- That is the gate working, not evidence of no disparity.
- The disparity in the clean model probably comes from the training data itself: the
  identity group's base rate is 0.64 vs 0.11. This was not tested.

**Controlled-defect detection**
- Flips at 0.4 and above are detected (H2).
- 0.2 is not distinguishable from clean. Both abstain, and their EOD differs by 0.008.

**Severity**
- EOD is strictly monotone in flip rate, but saturates between 0.7 and 1.0.
- DPD and the FPR gap also rise monotonically: FPR gap 0.075 → 0.347.

**CI behaviour**
- Every EOD CI width is between 0.126 and 0.156, close to the 0.15 gate. With
  g1 ≈ 318 positives and g0 ≈ 282 positives, the 0.15 gate decides two of the six
  outcomes here.
- That threshold is reported, not re-tuned.

**Separation of control and defect**
- The detection margin between the injected defects and the external control is small:
  r040 EOD 0.167 vs reference 0.145.
- Under this rule, an EOD-based flag alone cannot tell an injected defect from a real
  model's own disparity.

## Limitations

- One data seed and one training seed. Run-to-run repeatability is trivially exact,
  because the evidence is deterministic. Training-seed variance is not measured.
- Evidence level only. The FAIRNESS O/S/D score (LLM engine) was not produced, by
  pre-registered design.
- The experiments ran in-process, not through the docker worker, which predates L4.1.
  The probe code is the same.
