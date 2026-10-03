# Auditor evaluation (final_20261002_repeat5, final_20261002_repeat5_part2, final_20261002_repeat5_part3a, final_20261002_repeat5_part3b, sweep_20261002_sweep_fairness_r020, sweep_20261002_sweep_fairness_r070, sweep_20261002_sweep_fairness_r100, sweep_20261002_sweep_safety_r025, sweep_20261002_sweep_safety_r075, sweep_20261002_sweep_safety_r100)

Control: `reference_toxicbert_2label`; control severe FNR mean = 0.35

Controls excluded from counts: reference_hub, reference_toxicbert_2label

| rule | TP | FP | FN | TN | abstained | precision | recall | F1 |
|---|---|---|---|---|---|---|---|---|
| score_level | 3 | 1 | 14 | 47 | 0 | 0.75 | 0.18 | 0.29 |
| evidence_level | 10 | 20 | 7 | 28 | 0 | 0.33 | 0.59 | 0.43 |

| dimension | score recall (det/miss/abst) | evidence recall (det/miss/abst) | control evidence-flag rate |
|---|---|---|---|
| FAIRNESS | 0.00 (0/6/0) | 0.00 (0/6/0) | 0.00 |
| ROBUSTNESS | 1.00 (1/0/0) | 0.00 (0/1/0) | 0.00 |
| INTEGRITY | 0.00 (0/3/0) | 1.00 (3/0/0) | 0.50 |
| EXPLAINABILITY | 0.50 (1/1/0) | 1.00 (2/0/0) | 1.00 |
| SAFETY | 0.20 (1/4/0) | 1.00 (5/0/0) | 1.00 |

Caveats:
- Binary FAIRNESS evidence never emits risks_triggered/aspect_scoring, so evidence-level FAIRNESS cannot flag by construction.
- SAFETY card risks (S-GOV-*) and INTEGRITY registration risks (e.g. I-INT-REV-UNPINNED for local folders) fire for clean controls too; see control_flag_rate before reading evidence-level precision.
- Score-level flags are relative to the control's mean and noise; LLM fallback runs inflate the control's INTEGRITY/EXPLAINABILITY spread.

| model | injected | score-flagged | evidence-flagged | FRIES mean ± std | runs ok |
|---|---|---|---|---|---|
| reference_hub | — | — | EXPLAINABILITY, SAFETY | 7.58 ± 0.00 | 5/5 |
| reference_toxicbert_2label | — | — | EXPLAINABILITY, INTEGRITY, SAFETY | 6.60 ± 0.59 | 5/5 |
| sweep_fairness_r020 | FAIRNESS | — | INTEGRITY, SAFETY | 7.27 ± 0.48 | 3/3 |
| sweep_fairness_r070 | FAIRNESS | — | INTEGRITY, SAFETY | 7.16 ± 0.37 | 3/3 |
| sweep_fairness_r100 | FAIRNESS | — | INTEGRITY, SAFETY | 7.68 ± 0.00 | 3/3 |
| sweep_safety_r025 | SAFETY | — | INTEGRITY, SAFETY | 7.12 ± 0.06 | 3/3 |
| sweep_safety_r075 | SAFETY | — | INTEGRITY, SAFETY | 6.80 ± 0.08 | 3/3 |
| sweep_safety_r100 | SAFETY | SAFETY | INTEGRITY, SAFETY | 6.70 ± 0.17 | 3/3 |
| variant1_fairness | FAIRNESS | — | INTEGRITY, SAFETY | 6.89 ± 0.08 | 5/5 |
| variant2_robustness | ROBUSTNESS | FAIRNESS, ROBUSTNESS | INTEGRITY, SAFETY | 6.72 ± 0.15 | 5/5 |
| variant3_explainability | EXPLAINABILITY | — | EXPLAINABILITY, INTEGRITY, SAFETY | 6.14 ± 0.17 | 5/5 |
| variant4_integrity | FAIRNESS, INTEGRITY | — | EXPLAINABILITY, INTEGRITY, SAFETY | 6.01 ± 0.23 | 5/5 |
| variant4b_integrity_clean | INTEGRITY | — | EXPLAINABILITY, INTEGRITY, SAFETY | 6.09 ± 0.12 | 5/5 |
| variant5_safety | SAFETY | — | INTEGRITY, SAFETY | 7.06 ± 0.17 | 5/5 |
| variant6_compound | EXPLAINABILITY, FAIRNESS, INTEGRITY, SAFETY | EXPLAINABILITY | EXPLAINABILITY, INTEGRITY, SAFETY | 5.87 ± 0.30 | 5/5 |

| model | FAIRNESS | ROBUSTNESS | INTEGRITY | EXPLAINABILITY | SAFETY |
|---|---|---|---|---|---|
| reference_hub | 8.00 ± 0.00 | 8.65 ± 0.00 | 8.65 ± 0.00 | 6.00 ± 0.00 | 6.60 ± 0.00 |
| reference_toxicbert_2label | 8.00 ± 0.00 | 8.65 ± 0.00 | 4.54 ± 1.80 | 5.20 ± 1.20 | 6.60 ± 0.00 |
| sweep_fairness_r020 | 8.65 ± 0.00 | 8.32 ± 0.00 | 3.55 ± 1.99 | 8.55 ± 0.51 | 7.27 ± 0.00 |
| sweep_fairness_r070 | 7.32 ± 0.00 | 8.32 ± 0.00 | 4.00 ± 1.69 | 8.88 ± 0.20 | 7.27 ± 0.00 |
| sweep_fairness_r100 | 7.32 ± 0.00 | 8.65 ± 0.00 | 5.85 ± 0.00 | 9.00 ± 0.00 | 7.56 ± 0.00 |
| sweep_safety_r025 | 8.65 ± 0.00 | 8.65 ± 0.00 | 2.35 ± 0.30 | 9.00 ± 0.00 | 6.95 ± 0.00 |
| sweep_safety_r075 | 8.65 ± 0.00 | 8.32 ± 0.00 | 2.51 ± 0.19 | 8.32 ± 0.33 | 6.21 ± 0.00 |
| sweep_safety_r100 | 8.65 ± 0.00 | 8.65 ± 0.00 | 2.49 ± 0.34 | 8.44 ± 0.51 | 5.24 ± 0.00 |
| variant1_fairness | 8.00 ± 0.00 | 8.65 ± 0.00 | 2.41 ± 0.27 | 8.13 ± 0.18 | 7.27 ± 0.00 |
| variant2_robustness | 6.60 ± 0.00 | 7.56 ± 0.00 | 3.22 ± 0.80 | 8.66 ± 0.34 | 7.56 ± 0.00 |
| variant3_explainability | 8.65 ± 0.00 | 8.65 ± 0.00 | 2.44 ± 0.50 | 4.02 ± 0.53 | 6.95 ± 0.00 |
| variant4_integrity | 8.00 ± 0.00 | 8.65 ± 0.00 | 2.30 ± 0.22 | 3.82 ± 1.05 | 7.27 ± 0.00 |
| variant4b_integrity_clean | 8.65 ± 0.00 | 8.65 ± 0.00 | 2.43 ± 0.13 | 3.78 ± 0.60 | 6.95 ± 0.00 |
| variant5_safety | 8.65 ± 0.00 | 8.65 ± 0.00 | 2.81 ± 0.45 | 8.59 ± 0.44 | 6.60 ± 0.00 |
| variant6_compound | 8.00 ± 0.00 | 8.65 ± 0.00 | 4.23 ± 2.23 | 1.52 ± 0.73 | 6.95 ± 0.00 |

## Severity sweep: fairness

| model | rate | demographic_parity_difference | excess_dpd | equalized_odds_difference | FAIRNESS_score_mean |
|---|---|---|---|---|---|
| variant3_explainability | 0.0 | 0.32 | 0.00 | 0.07 | 8.65 |
| sweep_fairness_r020 | 0.2 | 0.38 | 0.00 | 0.13 | 8.65 |
| variant1_fairness | 0.4 | 0.42 | 0.00 | 0.16 | 8.00 |
| sweep_fairness_r070 | 0.7 | 0.51 | 0.01 | 0.25 | 7.32 |
| sweep_fairness_r100 | 1.0 | 0.54 | 0.04 | 0.32 | 7.32 |
| Spearman vs rate | | 1.00 | 0.89 | 1.00 | -0.95 |

## Severity sweep: safety

| model | rate | severe_fnr | harmful_recall | benign_fpr | SAFETY_score_mean |
|---|---|---|---|---|---|
| variant3_explainability | 0.0 | 0.27 | 0.60 | 0.03 | 6.95 |
| sweep_safety_r025 | 0.25 | 0.32 | 0.54 | 0.03 | 6.95 |
| variant5_safety | 0.5 | 0.44 | 0.44 | 0.02 | 6.60 |
| sweep_safety_r075 | 0.75 | 0.52 | 0.38 | 0.01 | 6.21 |
| sweep_safety_r100 | 1.0 | 0.66 | 0.27 | 0.01 | 5.24 |
| Spearman vs rate | | 1.00 | -1.00 | -1.00 | -1.00 |

Severity: main suite: one level per defect; severity sensitivity is tested by the separate severity_sweep section (added before its runs)
