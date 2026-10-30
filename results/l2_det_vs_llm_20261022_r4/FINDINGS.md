# L2 — deterministic vs LLM interpretation: 60/60 run set (2026-10-22, supplemental fill)

Builds on `../l2_det_vs_llm_20261003_r3/` (frozen, unchanged). Same 12 packets, same prompt
(`osd-llm-v3-decision-first-2026-10-03`), same prompt sha256 per packet. No methodology, threshold,
packet or deterministic output changed. No winner, no ranking.

## What is in the 60

| source | runs |
|---|---|
| Gemini (original, 2026-10-02) | 9 |
| Groq `openai/gpt-oss-120b` (original, 2026-10-02) | 13 |
| **Claude `claude-sonnet-5-5` (supplemental, 2026-10-22)** | **38** |
| total | 60 (0 fallbacks, 0 parse failures) |

The 38 runs are exactly those that every API provider failed on (`provider_unavailable` in r3).
Each was answered once by a fresh-context Claude subagent that read only the exported prompt file
(`../l2_claude_eval_20261003/prompts/l2_Pxx.txt`), no TrustLens findings, no code, no other files
(an instruction, not technically enforced). The orchestrating session wrote none of the answers.
Raw answers are in `llm_responses.jsonl` (`provider: claude`, `supplemental: true`); the r3 records
are kept, later records supersede by run index. `ingest_claude_supplement.py` shows the exact step.

## Caveats (state these wherever the 60 is quoted)

- The 60 is **not one provider**. 38/60 are Claude; the original provider question (do Gemini/Groq
  agree with each other) rests on the 22 genuine provider runs only.
- Claude runs were made on 2026-10-22, not 2026-10-02; model sampling settings are the Claude
  defaults (temperature not recorded, `null`).
- P05–P12 are covered almost entirely by Claude, so per-packet repeatability there is
  Claude-vs-Claude, not cross-provider.
- `elapsed_s` is 0 for Claude records: `llm_s_per_call_mean` (7.26 s) is NOT a latency measurement.
  Use the r3 figures for provider latency.

## Headline (36 packet x dimension pairs, modal answer per pair)

| measure | r3 (22 genuine) | r4 (60/60) |
|---|---|---|
| answered pairs | 18 | 36 |
| exact status agreement | n/a on 18 | 0.306 |
| risk-present agreement, both definite | n/a on 18 | 0.44 (25 definite) |
| severity exact / within 1 / MAE | — | 0.111 / 0.222 / 2.19 |
| O / S / D MAE | — | 1.86 / 2.19 / 2.31 |
| mean risk agreement across repeats | 0.917 (12 pairs) | 0.939 (36 pairs) |
| mean O / S / D range across repeats | 2.33 / 2.08 / 2.67 | 1.28 / 1.31 / 2.14 |
| O/S/D exact-repeatable pairs | 0 | 0 |

Per dimension status agreement: INTEGRITY 0.083, EXPLAINABILITY 0.833, SAFETY 0.000
(deterministic never raises a safety risk; LLM raises one on 12/12). Provider effect persists:
Groq mean O 2.8 (INTEGRITY) vs Gemini 5.7 vs Claude 4.9.
Full numbers: `analysis.json`, `analysis.md`.
