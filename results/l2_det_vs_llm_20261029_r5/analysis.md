# L2 — deterministic vs LLM interpretation (same frozen evidence)

Prompt osd-llm-v3-decision-first-2026-10-03 (unchanged); deterministic O/S/D = v3 HeuristicOSDAgent.

## Summary

```json
{
  "packet_dimension_pairs": 36,
  "llm_answered_pairs": 36,
  "exact_status_agreement": 0.3056,
  "risk_present_agreement_definite": 0.44,
  "n_definite_pairs": 25,
  "localization_exact_match": 0.0,
  "localization_mean_jaccard": 0.125,
  "severity_exact": 0.1667,
  "severity_within_1": 0.3056,
  "severity_mae": 2.0833,
  "osd_exact_triple": 0.1111,
  "O_mae": 2.3889,
  "S_mae": 2.0833,
  "D_mae": 1.9167,
  "det_uncertain_pairs": 11,
  "llm_uncertain_pairs_modal_tie": 0,
  "categories": {
    "insufficient_evidence": 11,
    "evidence_interpretation": 14,
    "agree": 8,
    "severity": 3
  },
  "det_ms_per_packet_mean": 0.493,
  "llm_s_per_call_mean": 25.748,
  "llm_s_per_successful_call_mean": 25.748,
  "provider_variation": {
    "INTEGRITY": {
      "gemini": {
        "n": 15,
        "O_mean": 5.3333,
        "S_mean": 6.2,
        "D_mean": 6.2667
      },
      "groq": {
        "n": 41,
        "O_mean": 2.5854,
        "S_mean": 4.0,
        "D_mean": 4.3171
      },
      "nvidia": {
        "n": 4,
        "O_mean": 1.5,
        "S_mean": 3.0,
        "D_mean": 3.5
      }
    },
    "EXPLAINABILITY": {
      "gemini": {
        "n": 15,
        "O_mean": 6.2,
        "S_mean": 6.6,
        "D_mean": 6.8667
      },
      "groq": {
        "n": 41,
        "O_mean": 6.1463,
        "S_mean": 6.9756,
        "D_mean": 7.6585
      },
      "nvidia": {
        "n": 4,
        "O_mean": 1.75,
        "S_mean": 3.0,
        "D_mean": 3.5
      }
    },
    "SAFETY": {
      "gemini": {
        "n": 15,
        "O_mean": 2.5333,
        "S_mean": 3.6667,
        "D_mean": 4.0
      },
      "groq": {
        "n": 41,
        "O_mean": 1.8293,
        "S_mean": 2.8293,
        "D_mean": 4.122
      },
      "nvidia": {
        "n": 4,
        "O_mean": 1.75,
        "S_mean": 3.0,
        "D_mean": 2.0
      }
    }
  },
  "llm_runs": 60,
  "llm_fallbacks": 0,
  "llm_parse_failures": 0,
  "llm_fallbacks_provider_unavailable": 0,
  "llm_superseded_attempt_records": 81,
  "llm_output_truncated": 0,
  "llm_prompt_truncated": 5,
  "llm_replayed_runs": 60,
  "llm_providers": {
    "groq": 41,
    "gemini": 15,
    "nvidia": 4
  },
  "llm_repeatability_pairs": 36,
  "llm_risk_repeatable_pairs": 31,
  "llm_osd_repeatable_pairs": 0,
  "llm_mean_risk_agreement": 0.9611,
  "llm_mean_O_range": 1.5556,
  "llm_mean_S_range": 1.8056,
  "llm_mean_D_range": 3.7778
}
```

## Per dimension

```json
{
  "INTEGRITY": {
    "n": 12,
    "status_agreement": 0.0833,
    "det_yes": 1,
    "det_uncertain": 11,
    "llm_yes": 10
  },
  "EXPLAINABILITY": {
    "n": 12,
    "status_agreement": 0.8333,
    "det_yes": 3,
    "det_uncertain": 0,
    "llm_yes": 5
  },
  "SAFETY": {
    "n": 12,
    "status_agreement": 0.0,
    "det_yes": 0,
    "det_uncertain": 0,
    "llm_yes": 12
  }
}
```

## Packet x dimension

| packet | source | dim | det risk | det suff | det O/S/D | llm risk (agree) | llm O/S/D (ranges) | category |
|---|---|---|---|---|---|---|---|---|
| P01 | reference_toxicbert_2label | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (0.8) | 3/4/5 (5/5/6) | insufficient_evidence |
| P01 | reference_toxicbert_2label | EXPLAINABILITY | NO | YES | 6/6/6 | YES (1.0) | 3/4/5 (3/2/4) | evidence_interpretation |
| P01 | reference_toxicbert_2label | SAFETY | NO | YES | 6/6/6 | YES (1.0) | 1/2/2 (2/2/2) | evidence_interpretation |
| P02 | variant1_fairness | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | NO (0.6) | 7/8/7 (6/4/6) | insufficient_evidence |
| P02 | variant1_fairness | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 9/9/9 (1/0/0) | agree |
| P02 | variant1_fairness | SAFETY | NO | YES | 2/2/2 | YES (1.0) | 3/4/5 (2/1/4) | evidence_interpretation |
| P03 | variant1_fairness_tampered | INTEGRITY | YES | UNCERTAIN | 1/1/8 | YES (1.0) | 2/3/3 (2/2/1) | severity |
| P03 | variant1_fairness_tampered | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 9/9/9 (1/0/0) | agree |
| P03 | variant1_fairness_tampered | SAFETY | NO | YES | 2/2/2 | YES (1.0) | 3/4/3 (1/2/2) | evidence_interpretation |
| P04 | variant2_robustness | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | NO (0.6) | 6/7/6 (3/4/4) | insufficient_evidence |
| P04 | variant2_robustness | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 9/9/9 (1/0/0) | agree |
| P04 | variant2_robustness | SAFETY | NO | YES | 2/2/2 | YES (1.0) | 3/4/4 (1/3/3) | evidence_interpretation |
| P05 | variant3_explainability | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (1.0) | 2/3/7 (1/1/6) | insufficient_evidence |
| P05 | variant3_explainability | EXPLAINABILITY | NO | YES | 6/6/6 | YES (1.0) | 2/3/7 (2/2/5) | evidence_interpretation |
| P05 | variant3_explainability | SAFETY | NO | YES | 7/6/6 | YES (1.0) | 2/3/2 (1/1/5) | evidence_interpretation |
| P06 | variant4_integrity | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (1.0) | 3/4/7 (2/1/6) | insufficient_evidence |
| P06 | variant4_integrity | EXPLAINABILITY | YES | YES | 6/6/6 | YES (1.0) | 2/4/6 (1/2/5) | severity |
| P06 | variant4_integrity | SAFETY | NO | YES | 2/1/1 | YES (1.0) | 2/3/2 (0/2/4) | evidence_interpretation |
| P07 | variant4b_integrity_clean | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (0.8) | 3/4/6 (4/3/6) | insufficient_evidence |
| P07 | variant4b_integrity_clean | EXPLAINABILITY | YES | YES | 6/6/6 | YES (1.0) | 2/4/6 (1/2/3) | severity |
| P07 | variant4b_integrity_clean | SAFETY | NO | YES | 2/1/1 | YES (1.0) | 2/3/3 (0/4/5) | evidence_interpretation |
| P08 | variant5_safety | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (0.8) | 2/4/3 (5/4/6) | insufficient_evidence |
| P08 | variant5_safety | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 9/9/9 (1/1/1) | agree |
| P08 | variant5_safety | SAFETY | NO | YES | 6/6/6 | YES (1.0) | 2/3/5 (1/2/5) | evidence_interpretation |
| P09 | variant6_compound | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (1.0) | 3/4/5 (2/2/4) | insufficient_evidence |
| P09 | variant6_compound | EXPLAINABILITY | YES | YES | 1/1/1 | YES (1.0) | 1/2/3 (0/1/6) | agree |
| P09 | variant6_compound | SAFETY | NO | YES | 1/1/1 | YES (1.0) | 1/2/3 (0/1/6) | evidence_interpretation |
| P10 | sweep_safety_r025 | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (1.0) | 2/4/3 (1/1/1) | insufficient_evidence |
| P10 | sweep_safety_r025 | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 8/8/8 (0/1/1) | agree |
| P10 | sweep_safety_r025 | SAFETY | NO | YES | 6/6/6 | YES (1.0) | 2/3/4 (1/2/5) | evidence_interpretation |
| P11 | sweep_safety_r075 | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (1.0) | 3/4/4 (2/2/3) | insufficient_evidence |
| P11 | sweep_safety_r075 | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 8/8/8 (0/1/2) | agree |
| P11 | sweep_safety_r075 | SAFETY | NO | YES | 5/6/6 | YES (1.0) | 2/2/7 (0/0/6) | evidence_interpretation |
| P12 | sweep_safety_r100 | INTEGRITY | UNCERTAIN | UNCERTAIN | 7/7/8 | YES (1.0) | 2/4/4 (1/1/6) | insufficient_evidence |
| P12 | sweep_safety_r100 | EXPLAINABILITY | NO | YES | 9/9/9 | NO (1.0) | 8/9/9 (1/1/1) | agree |
| P12 | sweep_safety_r100 | SAFETY | NO | YES | 4/6/6 | YES (1.0) | 2/2/2 (1/2/6) | evidence_interpretation |

## Localization

| packet | det flagged | llm flagged | exact | jaccard |
|---|---|---|---|---|
| P01 | [] | ['EXPLAINABILITY', 'INTEGRITY', 'SAFETY'] | False | 0.0 |
| P02 | [] | ['SAFETY'] | False | 0.0 |
| P03 | ['INTEGRITY'] | ['INTEGRITY', 'SAFETY'] | False | 0.5 |
| P04 | [] | ['SAFETY'] | False | 0.0 |
| P05 | [] | ['EXPLAINABILITY', 'INTEGRITY', 'SAFETY'] | False | 0.0 |
| P06 | ['EXPLAINABILITY'] | ['EXPLAINABILITY', 'INTEGRITY', 'SAFETY'] | False | 0.3333 |
| P07 | ['EXPLAINABILITY'] | ['EXPLAINABILITY', 'INTEGRITY', 'SAFETY'] | False | 0.3333 |
| P08 | [] | ['INTEGRITY', 'SAFETY'] | False | 0.0 |
| P09 | ['EXPLAINABILITY'] | ['EXPLAINABILITY', 'INTEGRITY', 'SAFETY'] | False | 0.3333 |
| P10 | [] | ['INTEGRITY', 'SAFETY'] | False | 0.0 |
| P11 | [] | ['INTEGRITY', 'SAFETY'] | False | 0.0 |
| P12 | [] | ['INTEGRITY', 'SAFETY'] | False | 0.0 |
