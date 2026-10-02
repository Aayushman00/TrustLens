# Auditor evaluation (final_20261002_repeat5, final_20261002_repeat5_part2, final_20261002_repeat5_part3a, final_20261002_repeat5_part3b)

Control: `reference_toxicbert_2label`; control severe FNR mean = 0.35

| rule | TP | FP | FN | TN | precision | recall | F1 |
|---|---|---|---|---|---|---|---|
| score_level | 2 | 1 | 9 | 28 | 0.67 | 0.18 | 0.29 |
| evidence_level | 7 | 16 | 4 | 18 | 0.30 | 0.64 | 0.41 |

| model | injected | score-flagged | evidence-flagged | FRIES mean ± std | runs ok |
|---|---|---|---|---|---|
| reference_hub | — | — | EXPLAINABILITY, SAFETY | 7.58 ± 0.00 | 5/5 |
| reference_toxicbert_2label | — | — | EXPLAINABILITY, INTEGRITY, SAFETY | 6.60 ± 0.59 | 5/5 |
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
| variant1_fairness | 0.4 | 0.42 | 0.00 | 0.16 | 8.00 |
| Spearman vs rate | | — | — | — | — |

## Severity sweep: safety

| model | rate | severe_fnr | harmful_recall | benign_fpr | SAFETY_score_mean |
|---|---|---|---|---|---|
| variant3_explainability | 0.0 | 0.27 | 0.60 | 0.03 | 6.95 |
| variant5_safety | 0.5 | 0.44 | 0.44 | 0.02 | 6.60 |
| Spearman vs rate | | — | — | — | — |

Severity: main suite: one level per defect; severity sensitivity is tested by the separate severity_sweep section (added before its runs)
