# Phase 26 analysis tables

## T1 — Mode C FRIES mean ± std

| short | n_runs | fries_mean | fries_std | fries_mean_pm_std | robustness | fairness |
| --- | --- | --- | --- | --- | --- | --- |
| TinyBERT SST-2 | 3 | 6.4095 | 0.1605 | 6.41 ± 0.16 | ran | proxy-ran |
| DistilBERT SST-2 | 3 | 6.3599 | 0.2166 | 6.36 ± 0.22 | ran | proxy-ran |
| ViT-B/16 | 3 | 5.5667 | 0.0786 | 5.57 ± 0.08 | skipped | proxy-ran |
| BERT AG News | 3 | 5.3091 | 0.0787 | 5.31 ± 0.08 | ran | proxy-ran |
| RoBERTa SST-2 | 3 | 5.2344 | 0.1060 | 5.23 ± 0.11 | ran | proxy-ran |
| BERT-tiny LM | 3 | 4.2360 | 0.0786 | 4.24 ± 0.08 | skipped | proxy-ran |

## T2 — Mode C per-aspect Ti mean (equal-weight dimension scores)

| short | FAIRNESS_Ti | ROBUSTNESS_Ti | INTEGRITY_Ti | EXPLAINABILITY_Ti | SAFETY_Ti |
| --- | --- | --- | --- | --- | --- |
| DistilBERT SST-2 | 7.5457 | 7.6001 | 8.6535 | 6.0000 | 2.0000 |
| ViT-B/16 | 7.5457 | 3.6342 | 8.6535 | 6.0000 | 2.0000 |
| TinyBERT SST-2 | 7.5457 | 7.8479 | 8.6535 | 6.0000 | 2.0000 |
| BERT-tiny LM | 7.5457 | 3.6342 | 8.0000 | 1.0000 | 1.0000 |
| BERT AG News | 7.5457 | 9.0000 | 8.0000 | 1.0000 | 1.0000 |
| RoBERTa SST-2 | 7.5457 | 8.1996 | 5.8480 | 2.2894 | 2.2894 |

## T3 — Mode A vs C vs B FRIES

| short | mode_a_fries | mode_c_seed42_fries | mode_c_mean_fries | mode_b_fries | delta_c_minus_a | delta_b_minus_a | delta_b_minus_c |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DistilBERT SST-2 | 5.2300 | 6.1681 | 6.3599 | 6.1681 | 0.9381 | 0.9381 | 0.0000 |
| BERT-tiny LM | 4.5700 | 4.1906 | 4.2360 | 5.1234 | -0.3794 | 0.5534 | 0.9328 |
| BERT AG News | 4.5100 | 5.2637 | 5.3091 | 6.1520 | 0.7537 | 1.6420 | 0.8883 |

## T4 — Mode B accept-all vs edited

| model | short | reviewer_label | accept_all | human_changed | aspects_changed | aspects_total | override_rate | agent_fries | approved_fries | delta_fries | mean_l1_osd_delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| distilbert-base-uncased-finetuned-sst-2-english | DistilBERT SST-2 | ai-provisional | True | False | 0 | 5 | 0.0000 | 6.1681 | 6.1681 | 0.0000 | 0 |
| prajjwal1/bert-tiny | BERT-tiny LM | ai-provisional | False | True | 2 | 5 | 0.4000 | 4.1906 | 5.1234 | 0.9328 | 3 |
| textattack/bert-base-uncased-ag-news | BERT AG News | ai-provisional | False | True | 2 | 5 | 0.4000 | 5.2637 | 6.1520 | 0.8883 | 2.8000 |
| _OVERALL_ | overall |  |  |  | 4 | 15 | 0.2670 |  |  |  |  |

## T5 — Wall-clock / effort

| short | mode_c_wall_s_mean | mode_c_wall_s_warm_mean | mode_a_minutes | mode_b_pipeline_wall_s | mode_b_review_minutes |
| --- | --- | --- | --- | --- | --- |
| DistilBERT SST-2 | 18.5400 | 10.1500 | 15.0000 | 10.1200 |  |
| ViT-B/16 | 5.0900 | 5.0800 |  |  |  |
| TinyBERT SST-2 | 15.6000 | 5.5500 |  |  |  |
| BERT-tiny LM | 5.1400 | 5.1000 | 12.0000 | 5.1000 |  |
| BERT AG News | 40.5400 | 15.3400 | 13.0000 | 20.2500 |  |
| RoBERTa SST-2 | 32.0300 | 12.7100 |  |  |  |

## T6 — Confidence ranked by model

| short | overall_confidence | EXPLAINABILITY_confidence | SAFETY_confidence | robustness_skipped | mode_b_edited | mode_b_edit_l1_sum |
| --- | --- | --- | --- | --- | --- | --- |
| DistilBERT SST-2 | 0.8676 | 0.7958 | 0.5593 | False | False | 0 |
| TinyBERT SST-2 | 0.8676 | 0.7958 | 0.5593 | False |  |  |
| ViT-B/16 | 0.7805 | 0.7958 | 0.5593 | True |  |  |
| BERT AG News | 0.7291 | 0.3302 | 0.3915 | False | True | 14 |
| RoBERTa SST-2 | 0.6707 | 0.2884 | 0.2884 | False |  |  |
| BERT-tiny LM | 0.6421 | 0.3302 | 0.3915 | True | True | 15 |

## T6b — Confidence correlations (descriptive)

| pair | n | pearson | spearman | note |
| --- | --- | --- | --- | --- |
| overall_confidence vs explainability+safety mean (n=6) | 6 | 0.8970 | 0.8454 | Tautological-ish: overall confidence is an aggregate of aspect confidences. |
| overall_confidence vs robustness_skipped (point-biserial, n=6) | 6 | -0.3884 | -0.4201 | Negative expected if skips lower confidence. Descriptive only. |
| card-like confidence vs Mode B edit L1 (n=3 overlap) | 3 | -0.9982 | -0.8660 | Thin-card models were the ones edited; n=3, not inferential. |

## T7 — Determinism check

| short | verdict | n_keys_compared | n_diffs | fries_det | fries_seed42 |
| --- | --- | --- | --- | --- | --- |
| TinyBERT SST-2 | identical | 22 | 0 | 6.3168 | 6.3168 |

## Agreement (A vs C / A vs B)

| comparison | n | pearson | spearman | mae | note |
| --- | --- | --- | --- | --- | --- |
| A vs C (FRIES, seed-42, n=3 models) | 3 | 0.7973 | 0.5000 | 0.6900 | Single Mode A rater, ai-provisional. n=3 — descriptive only, not significance. |
| A vs B (FRIES, n=3 models) | 3 | 0.4456 | 0.5000 | 1.0440 | Mode B also ai-provisional. Cohen's kappa omitted (one rater; no band discretization). |
| A vs C (mean \|Δ\| over O/S/D cells) | 45 |  |  | 2.6000 | 15 aspects × 3 components on 3 models. |
| A vs B (mean \|Δ\| over O/S/D cells) | 45 |  |  | 1.9560 | Approved Mode B O/S/D vs Mode A rubric. |

## RQ1 probe coverage

| probe | runs | produced_metrics | skipped | skip_rate | note |
| --- | --- | --- | --- | --- | --- |
| FAIRNESS | 18 | 18 | 0 | 0.0000 | Always ran; proxy LR on Adult — metrics are model-independent. |
| ROBUSTNESS | 18 | 12 | 6 | 0.3330 | 4/6 models are text-classifiers; others soft-skip. |
| INTEGRITY (card) | 18 | 18 | 0 | 0.0000 | Card/metadata checks; always a numeric pass-rate. |
| EXPLAINABILITY (card) | 18 | 18 | 0 | 0.0000 | Header-coverage heuristic; 0.00 coverage is still a metric, not a skip. |
| SAFETY (card) | 18 | 18 | 0 | 0.0000 | Same coverage heuristic as explainability. |
| _ALL_SLOTS_ | 90 | 84 | 6 | 0.0670 | 5 dimensions × 6 models × 3 seeds. Only robustness actually skips. |

Regenerate: `cd backend && python -m app.scripts.analyze_experiments`.
Agent O/S/D remains **PROPOSED / REQUIRES VALIDATION**. Mode A/B rater label is `ai-provisional`.
