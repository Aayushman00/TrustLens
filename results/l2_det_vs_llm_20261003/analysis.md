# L2 — deterministic vs LLM interpretation (same frozen evidence)

Prompt osd-llm-v3-decision-first-2026-10-03 (unchanged); deterministic O/S/D = v3 HeuristicOSDAgent.

## Summary

```json
{
  "packet_dimension_pairs": 36,
  "llm_answered_pairs": 18,
  "exact_status_agreement": 0.2778,
  "risk_present_agreement_definite": 0.3846,
  "n_definite_pairs": 13,
  "localization_exact_match": 0.0,
  "localization_mean_jaccard": 0.1389,
  "severity_exact": 0.2222,
  "severity_within_1": 0.3889,
  "severity_mae": 1.7778,
  "osd_exact_triple": 0.1667,
  "O_mae": 2.1667,
  "S_mae": 1.7778,
  "D_mae": 2.2222,
  "det_uncertain_pairs": 11,
  "llm_uncertain_pairs_modal_tie": 0,
  "categories": {
    "insufficient_evidence": 5,
    "evidence_interpretation": 8,
    "agree": 3,
    "severity": 2,
    "truncation_fallback": 18
  },
  "det_ms_per_packet_mean": 2.14,
  "llm_s_per_call_mean": 10.339,
  "llm_s_per_successful_call_mean": 19.788,
  "provider_variation": {
    "INTEGRITY": {
      "gemini": {
        "n": 9,
        "O_mean": 5.6667,
        "S_mean": 6.5556,
        "D_mean": 6.3333
      },
      "groq": {
        "n": 13,
        "O_mean": 2.8462,
        "S_mean": 3.9231,
        "D_mean": 4.1538
      }
    },
    "EXPLAINABILITY": {
      "gemini": {
        "n": 9,
        "O_mean": 8.5556,
        "S_mean": 8.6667,
        "D_mean": 8.6667
      },
      "groq": {
        "n": 13,
        "O_mean": 5.6923,
        "S_mean": 6.7692,
        "D_mean": 7.3846
      }
    },
    "SAFETY": {
      "gemini": {
        "n": 9,
        "O_mean": 3.2222,
        "S_mean": 4.4444,
        "D_mean": 4.6667
      },
      "groq": {
        "n": 13,
        "O_mean": 1.7692,
        "S_mean": 2.9231,
        "D_mean": 2.9231
      }
    }
  },
  "llm_runs": 60,
  "llm_fallbacks": 38,
  "llm_parse_failures": 0,
  "llm_fallbacks_provider_unavailable": 38,
  "llm_superseded_attempt_records": 41,
  "llm_output_truncated": 0,
  "llm_prompt_truncated": 5,
  "llm_replayed_runs": 60,
  "llm_providers": {
    "groq": 13,
    "gemini": 9,
    "none": 38
  },
  "llm_repeatability_pairs": 12,
  "llm_risk_repeatable_pairs": 9,
  "llm_osd_repeatable_pairs": 0,
  "llm_mean_risk_agreement": 0.9167,
  "llm_mean_O_range": 2.3333,
  "llm_mean_S_range": 2.0833,
  "llm_mean_D_range": 2.6667
}
```

## Per dimension

```json
{
  "INTEGRITY": {
    "n": 6,
    "status_agreement": 0.1667,
    "det_yes": 1,
    "det_uncertain": 5,
    "llm_yes": 4
  },
  "EXPLAINABILITY": {
    "n": 6,
    "status_agreement": 0.6667,
    "det_yes": 1,
    "det_uncertain": 0,
    "llm_yes": 3
  },
  "SAFETY": {
    "n": 6,
    "status_agreement": 0.0,
    "det_yes": 0,
    "det_uncertain": 0,
    "llm_yes": 6
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
| P04 | variant2_robustness | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | NO (0.6) | 6/7/6 (3/4/4) | insufficient_evidence |
| P04 | variant2_robustness | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 9/9/9 (1/0/0) | agree |
| P04 | variant2_robustness | SAFETY | NO | YES | 2/2/2 | YES (1.0) | 3/4/4 (1/3/3) | evidence_interpretation |
| P05 | variant3_explainability | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (1.0) | 2/4/8 (0/0/0) | insufficient_evidence |
| P05 | variant3_explainability | EXPLAINABILITY | NO | YES | 6/6/6 | YES (1.0) | 3/5/7 (0/0/0) | evidence_interpretation |
| P05 | variant3_explainability | SAFETY | NO | YES | 7/6/8 | YES (1.0) | 2/4/7 (0/0/0) | evidence_interpretation |
| P06 | variant4_integrity | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P06 | variant4_integrity | EXPLAINABILITY | YES | YES | 6/6/6 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P06 | variant4_integrity | SAFETY | NO | YES | 2/1/1 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P07 | variant4b_integrity_clean | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P07 | variant4b_integrity_clean | EXPLAINABILITY | YES | YES | 6/6/6 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P07 | variant4b_integrity_clean | SAFETY | NO | YES | 2/1/1 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P08 | variant5_safety | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P08 | variant5_safety | EXPLAINABILITY | NO | YES | 9/9/9 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P08 | variant5_safety | SAFETY | NO | YES | 6/6/8 | None (—) | None/None/None (—/—/—) | truncation_fallback |
| P09 | variant6_compound | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (1.0) | 2/4/8 (0/0/0) | insufficient_evidence |
| P09 | variant6_compound | EXPLAINABILITY | YES | YES | 1/1/1 | YES (1.0) | 1/3/8 (0/0/0) | severity |
| P09 | variant6_compound | SAFETY | NO | YES | 1/1/1 | YES (1.0) | 1/2/8 (0/0/0) | evidence_interpretation |
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
| P05 | [] | ['EXPLAINABILITY', 'INTEGRITY', 'SAFETY'] | False | 0.0 |
| P09 | ['EXPLAINABILITY'] | ['EXPLAINABILITY', 'INTEGRITY', 'SAFETY'] | False | 0.3333 |
