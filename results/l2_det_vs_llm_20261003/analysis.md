# L2 — deterministic vs LLM interpretation (same frozen evidence)

Prompt osd-llm-v3-decision-first-2026-10-03 (unchanged); deterministic O/S/D = v3 HeuristicOSDAgent.

## Summary

```json
{
  "packet_dimension_pairs": 36,
  "llm_answered_pairs": 12,
  "exact_status_agreement": 0.3333,
  "risk_present_agreement_definite": 0.4444,
  "n_definite_pairs": 9,
  "localization_exact_match": 0.0,
  "localization_mean_jaccard": 0.125,
  "severity_exact": 0.3333,
  "severity_within_1": 0.4167,
  "severity_mae": 1.6667,
  "osd_exact_triple": 0.25,
  "O_mae": 1.75,
  "S_mae": 1.6667,
  "D_mae": 2.0,
  "det_uncertain_pairs": 11,
  "llm_uncertain_pairs_modal_tie": 0,
  "categories": {
    "insufficient_evidence": 3,
    "evidence_interpretation": 5,
    "agree": 3,
    "severity": 1,
    "truncation_fallback": 24
  },
  "det_ms_per_packet_mean": 2.645,
  "llm_s_per_call_mean": 10.679,
  "llm_runs": 60,
  "llm_fallbacks": 41,
  "llm_parse_failures": 0,
  "llm_fallbacks_provider_unavailable": 41,
  "llm_superseded_attempt_records": 0,
  "llm_output_truncated": 0,
  "llm_prompt_truncated": 5,
  "llm_replayed_runs": 60,
  "llm_providers": {
    "groq": 10,
    "gemini": 9,
    "none": 41
  },
  "llm_risk_repeatable_pairs": 9,
  "llm_osd_repeatable_pairs": 1,
  "llm_mean_risk_agreement": 0.9292,
  "llm_mean_O_range": 2.25,
  "llm_mean_S_range": 1.8333,
  "llm_mean_D_range": 2.6667
}
```

## Per dimension

```json
{
  "INTEGRITY": {
    "n": 4,
    "status_agreement": 0.25,
    "det_yes": 1,
    "det_uncertain": 3,
    "llm_yes": 2
  },
  "EXPLAINABILITY": {
    "n": 4,
    "status_agreement": 0.75,
    "det_yes": 0,
    "det_uncertain": 0,
    "llm_yes": 1
  },
  "SAFETY": {
    "n": 4,
    "status_agreement": 0.0,
    "det_yes": 0,
    "det_uncertain": 0,
    "llm_yes": 4
  }
}
```

## Packet x dimension

| packet | source | dim | det risk | det suff | det O/S/D | llm risk (agree) | llm O/S/D (ranges) | category |
|---|---|---|---|---|---|---|---|---|
| P01 | reference_toxicbert_2label | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (0.8) | 3/4/5 (5/5/6) | insufficient_evidence |
| P01 | reference_toxicbert_2label | EXPLAINABILITY | NO | YES | 6/6/6 | YES (1.0) | 3/4/5 (3/2/4) | evidence_interpretation |
| P01 | reference_toxicbert_2label | SAFETY | NO | YES | 6/6/8 | YES (1.0) | 1/2/2 (2/2/2) | evidence_interpretation |
| P02 | variant1_fairness | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | NO (0.6) | 7/8/7 (6/4/6) | insufficient_evidence |
| P02 | variant1_fairness | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 9/9/9 (1/0/0) | agree |
| P02 | variant1_fairness | SAFETY | NO | YES | 2/2/2 | YES (1.0) | 3/4/5 (2/1/4) | evidence_interpretation |
| P03 | variant1_fairness_tampered | INTEGRITY | YES | UNCERTAIN | 7/7/8 | YES (1.0) | 2/3/3 (2/2/1) | severity |
| P03 | variant1_fairness_tampered | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 9/9/9 (1/0/0) | agree |
| P03 | variant1_fairness_tampered | SAFETY | NO | YES | 2/2/2 | YES (1.0) | 3/4/3 (1/2/2) | evidence_interpretation |
| P04 | variant2_robustness | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | NO (0.75) | 6/7/6 (3/3/4) | insufficient_evidence |
| P04 | variant2_robustness | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 9/9/9 (0/0/0) | agree |
| P04 | variant2_robustness | SAFETY | NO | YES | 2/2/2 | YES (1.0) | 3/4/4 (1/1/3) | evidence_interpretation |
| P05 | variant3_explainability | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P05 | variant3_explainability | EXPLAINABILITY | NO | YES | 6/6/6 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P05 | variant3_explainability | SAFETY | NO | YES | 7/6/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P06 | variant4_integrity | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P06 | variant4_integrity | EXPLAINABILITY | YES | YES | 6/6/6 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P06 | variant4_integrity | SAFETY | NO | YES | 2/1/1 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P07 | variant4b_integrity_clean | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P07 | variant4b_integrity_clean | EXPLAINABILITY | YES | YES | 6/6/6 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P07 | variant4b_integrity_clean | SAFETY | NO | YES | 2/1/1 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P08 | variant5_safety | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P08 | variant5_safety | EXPLAINABILITY | NO | YES | 9/9/9 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P08 | variant5_safety | SAFETY | NO | YES | 6/6/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P09 | variant6_compound | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P09 | variant6_compound | EXPLAINABILITY | YES | YES | 1/1/1 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P09 | variant6_compound | SAFETY | NO | YES | 1/1/1 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P10 | sweep_safety_r025 | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P10 | sweep_safety_r025 | EXPLAINABILITY | NO | YES | 9/9/9 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P10 | sweep_safety_r025 | SAFETY | NO | YES | 6/6/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P11 | sweep_safety_r075 | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P11 | sweep_safety_r075 | EXPLAINABILITY | NO | YES | 9/9/9 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P11 | sweep_safety_r075 | SAFETY | NO | YES | 5/6/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P12 | sweep_safety_r100 | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P12 | sweep_safety_r100 | EXPLAINABILITY | NO | YES | 9/9/9 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P12 | sweep_safety_r100 | SAFETY | NO | YES | 4/6/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |

## Localization

| packet | det flagged | llm flagged | exact | jaccard |
|---|---|---|---|---|
| P01 | [] | ['EXPLAINABILITY', 'INTEGRITY', 'SAFETY'] | False | 0.0 |
| P02 | [] | ['SAFETY'] | False | 0.0 |
| P03 | ['INTEGRITY'] | ['INTEGRITY', 'SAFETY'] | False | 0.5 |
| P04 | [] | ['SAFETY'] | False | 0.0 |
