# L2 supplement — Claude as independent LLM evaluator (2026-10-03)

**evaluator = Claude, evaluator_type = independent_llm** (model `claude-opus-5-5`).
Supplemental only. Not part of the official L2 provider results (`results/l2_det_vs_llm_20261003/`,
unchanged, read-only) and not mixed into them. No TrustLens methodology, packet, threshold, mapping,
score or `ground_truth.json` changed. No winner, no ranking; disagreements kept as they are.

## Why and how

The API providers (Gemini, Groq, NVIDIA) were unavailable, so Claude answered the same frozen prompt
the providers get (`osd-llm-v3-decision-first-2026-10-03`), built by the existing
`build_prompt_with_truncation(llm_context(packet))` from the 12 frozen L2 packets.

- Packet hashes checked against the frozen `packet_index.json`; each prompt's sha256 checked
  against the `prompt_sha256` the providers recorded in `llm_runs.json`. All 12 identical.
- Blinding: the answers came from a fresh-context Claude subagent with no conversation history.
  It was told to read only the 24 exported prompt files (`prompts/`), run no code, and open nothing
  else. That rule was given as an instruction; the tooling did not technically enforce it. The
  orchestrating session, which had read the TrustLens findings, did not write or edit any answer.
- Prompts contain no TrustLens decision: risks, aspect scoring, gates, status and O/S/D are stripped
  by the existing L2 `llm_context` (tested in `tests/test_claude_eval.py`).
- One answer per packet, so 12 answers cover 36 packet x dimension cases (one prompt rates
  INTEGRITY, EXPLAINABILITY and SAFETY together). The request mentioned 60; that number is the
  official design's 12 packets x 5 *repeat runs*. No repeat Claude runs were made, because they
  would not be independent samples. Repeatability and latency fields are therefore omitted.
- Parsed with the existing `parse_gemini_response`; LLM risk rule unchanged (O <= 5 = risk present).
  12/12 parsed, 0 failures, 0 truncations. Raw answers are in `claude_responses.jsonl`.

## Claude vs TrustLens deterministic (36 pairs, frozen `deterministic.json`)

| measure | value |
|---|---|
| exact status agreement (YES/NO/UNCERTAIN) | 12/36 = 0.333 |
| risk-present agreement, both definite | 12/25 = 0.48 |
| severity S exact / within 1 / MAE | 0.056 / 0.167 / 2.47 |
| O/S/D exact triple; MAE O / S / D | 0.0; 2.39 / 2.47 / 3.25 |
| localization exact / mean Jaccard (12 packets) | 0/12 / 0.125 |
| categories | evidence_interpretation 13, insufficient_evidence 11, severity 10, agree 2 |

Per dimension:
- **INTEGRITY** 1/12 status agreement. Deterministic is UNCERTAIN on 11/12 (unpinned local folder,
  listing unverified) and YES on P03 (tampered weights). Claude answers on all 12: YES on 11, NO on
  P02. Both flag P03, but severity differs: deterministic S 7, Claude S 2.
- **EXPLAINABILITY** 11/12. Only P05 (auto-generated skeleton card) differs: deterministic finds a
  disclosure gap but no risk, while Claude finds a risk (O 1). The 10 severity cases are cards both
  call no-risk, where deterministic gives 9/9/9 and Claude gives 8/7/7 or lower.
- **SAFETY** 0/12. The deterministic risk layer never raises a safety risk; Claude raises one on
  12/12 packets (O 1–5). The same split appears in the official provider run (6/6 there).

## Claude vs the genuine provider answers (official run, 18 pairs on P01–P05, P09)

The provider side is the modal answer over the official run's genuine answers (Gemini/Groq, mixed by
the fallback chain). The official run has no NVIDIA answers (all its NVIDIA calls returned 404).

| measure | value |
|---|---|
| risk-present agreement | 16/18 = 0.889 |
| O/S/D exact triple | 0/18 |
| MAE O / S / D | 1.17 / 1.28 / 2.56 |

Disagreements: P01 EXPLAINABILITY (providers YES O 3, Claude NO O 6) and P04 INTEGRITY (providers NO
O 6, Claude YES O 5, on the O <= 5 boundary). Claude's D is lower than the providers' on P05/P09 (3–4
vs 7–8).

## Limitations

- One Claude answer per packet; no temperature control or seed; nothing about Claude's repeatability.
- The orchestrating session was not blind. Independence rests on the separate fresh-context subagent
  following its instructions.
- Provider comparison covers only the 18 officially answered pairs. Four further NVIDIA nemotron
  answers collected in an interrupted, uncommitted resume (`l2_det_vs_llm_20261003_r3/`, untracked)
  are not used here.
- The categories and the risk rule are the pre-registered L2 ones; Claude's "risk present" is the
  prompt's O <= 5 rule, not a separate question.
