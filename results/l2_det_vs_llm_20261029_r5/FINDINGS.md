# L2 — deterministic vs LLM interpretation: completed 60/60 run set (2026-10-28/29, r5)

Copy of `../l2_det_vs_llm_20261003_r3/` (left untouched) plus re-attempts of the missing runs with the same
script (`run_l2_interpretation --resume --retry-fallbacks`), the same prompt (`osd-llm-v3-decision-first-2026-10-03`),
the same frozen packets (`packet_index.json` checked identical) and the same provider chain (Gemini, Groq, NVIDIA).
No answer was written or edited by hand. The failed attempts of every earlier session stay in `llm_responses.jsonl`
(append-only; a later record supersedes its run index).

## Completion summary (`completion_audit_baseline_v9.json`, from `scripts/audit/l2_completion_audit.py`)

| quantity | value |
|---|---|
| planned runs (12 packets x 5) | 60 |
| valid answers already available (r3) | 22 (Gemini 9, Groq 13) |
| recovered by re-attempts | 38 (Groq 28, Gemini 6, NVIDIA 4) |
| invalid or unresolved at the end | 0 |
| valid answers now | 60/60 (Groq 41, Gemini 15, NVIDIA 4) |
| schema / packet / run-index violations | 0 |
| prompt hashes per packet | 1 (identical in all runs of a packet) |
| log records | 141 (60 final + 81 superseded failed records) |

Two slots needed a second pass after the main re-attempt: P05 run 4 (an earlier NVIDIA reply failed schema
validation: EXPLAINABILITY and SAFETY lacked O/S/D) and P12 run 4 (all three providers unavailable). Both were
re-attempted with the same chain by a one-off script (`retry_two.py`, forcing a fresh call for those two slots
only) and answered by Groq on the first attempt.

Recorded settings: Groq and NVIDIA calls carry temperature 0.2; Gemini records carry no temperature (provider
default), as in the original 9 Gemini answers. NVIDIA, the third provider of the original chain, returned 404 in
the first sessions (endpoint gone) and answers now.

## Caveats

* The 60 runs are not one provider: Groq 41, Gemini 15, NVIDIA 4. Provider effect is visible
  (mean O, Integrity: Gemini 5.33, Groq 2.59, NVIDIA 1.50). The runs were obtained over 2-28 Oct 2026 (22 on 2 Oct, 38 on 28 Oct).
* The deterministic baseline in `deterministic.json` was regenerated under the final method (v9); the baseline
  of 3 Oct is kept as `deterministic_original_v3.json` and `completion_audit_baseline_v3.json` gives the same
  statistics against it. Status and definite-risk agreement do not depend on the baseline; severity errors do.
* `analysis.md` still carries the header "v3 HeuristicOSDAgent" (stale label).
* The earlier pooled set `../l2_det_vs_llm_20261022_r4/` filled the same 38 slots with a different evaluator. It is
  kept for audit and is not used by the report.
