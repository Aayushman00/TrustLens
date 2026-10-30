# L2 — deterministic vs LLM interpretation: findings (2026-10-03, after provider-recovery attempt)

Pre-registration: `docs/superpowers/plans/2026-10-03-round3-L2-det-vs-llm.md` (deviations listed there).
Numbers: `analysis.json` / `analysis.md`, recomputed with `--replay` from `llm_responses.jsonl`.
No winner, no ranking; both outputs kept verbatim. Status: **incomplete — blocked by provider availability.**

## Sessions

| session | when (UTC) | what |
|---|---|---|
| 1 | 2026-10-02 ~22:00–22:35 | 60 planned runs; 19 answered, 41 provider-unavailable |
| 2 | 2026-10-02 23:13–23:17 | `--resume --retry-fallbacks`: only the 41 provider-unavailable runs re-attempted; 3 answered (Groq), 38 still unavailable |

The 19 session-1 answers were reused from the store, not re-called (byte-identical; sha256 of
those records unchanged). The log is append-only: 101 records = 60 + 41 retries; a retry
supersedes its run index, the failed record stays. Same prompt (`osd-llm-v3-decision-first-2026-10-03`)
and one prompt sha256 per packet across both sessions. Packets, `packet_index.json` and
`deterministic.json` unchanged (the re-run deterministic decisions were identical; only its
timing field differed, so the committed file was kept).

## A–D. Run accounting

| | count |
|---|---|
| A. planned runs (12 packets x 5) | 60 (36 packet x dimension pairs) |
| B. genuine LLM answers | 22 (Gemini 9, Groq 13) |
| C. fallback runs (no LLM judgment; not counted as answers) | 38 |
| D. of which provider/infrastructure failures | 38 (all) |
| parser failures / output truncations / prompt truncations | 0 / 0 / 5 (P01 card > 5,000 chars) |
| stored answers reused (cache hits) | 19 in session 2; all 60 in the final `--replay` |

Provider attempts over both sessions (including retries inside a run):

| provider | ok | failures |
|---|---|---|
| Gemini (gemini-3.6-flash) | 9 | 12 x 503 UNAVAILABLE (high demand), 80 x 429 RESOURCE_EXHAUSTED (quota) |
| Groq (openai/gpt-oss-120b) | 13 | 82 x 429 (tokens per day, limit 200,000) |
| NVIDIA (mistralai/mistral-large-2-instruct) | 0 | 79 x 404 "Function not found" (endpoint gone; configuration defect, not quota) |

Answered packets: P01–P04 (5 runs each), P05 (1 run), P09 (1 run). No answer: P06, P07, P08,
P10, P11, P12. Completing them requires the Gemini daily quota to reset (midnight Pacific) and/or
the Groq rolling 24-hour token window to free; NVIDIA will keep failing until its model id is fixed.

## Agreement (18 answered pairs; LLM side = modal answer over its valid runs)

| measure | value |
|---|---|
| exact status agreement (3-valued risk_present) | 5/18 = 0.278 |
| risk-present agreement, both definite | 5/13 = 0.385 |
| severity S exact / within 1 / MAE | 0.222 / 0.389 / 1.78 |
| O/S/D exact triple; MAE O / S / D | 0.167; 2.17 / 1.78 / 2.22 |
| localization exact / mean Jaccard (6 answered packets) | 0/6 / 0.139 |
| deterministic UNCERTAIN (answered pairs) | 5 (all INTEGRITY: unpinned / listing unverified) |
| LLM UNCERTAIN | 0 (frozen prompt has no abstain option; no modal ties) |

Categories (all 36 pairs): evidence_interpretation 8, insufficient_evidence 5, severity 2,
agree 3, truncation_fallback 18 (no LLM answer; provider outage).

Per dimension (answered pairs): INTEGRITY status agreement 1/6 (det YES 1, UNCERTAIN 5; LLM YES 4);
EXPLAINABILITY 4/6 (det YES 1; LLM YES 3); SAFETY 0/6 (det never YES; LLM YES 6/6).

Where they disagree:
- SAFETY: LLM O ≤ 4 on every answered packet; deterministic risk layer never raises a safety
  risk (card findings are disclosure gaps; behaviour has no risk ID), even where its own v3 band is
  1/1/1 (P09) or 2/2/2 (P02–P04).
- INTEGRITY: deterministic is UNCERTAIN on unverified local folders; the LLM always answers. Both
  flag the tampered weights (P03); severity differs (det S 7, LLM S 3).
- EXPLAINABILITY: agree on P02–P04 (O = 9 both). P01 (real Hub card, truncated in prompt) and P05
  (auto-generated skeleton card): LLM risk present, deterministic no risk (disclosure gap only).
  P09 (skeleton card + overclaims): both risk present; severity differs (det 1, LLM 3).

## LLM repeatability (12 pairs with ≥ 2 valid runs: P01–P04)

P05 and P09 have a single answer each and are excluded (one answer says nothing about repeatability).
- risk_present identical across valid runs: 9/12 pairs; mean modal agreement 0.917.
- identical O/S/D triple across valid runs: 0/12; mean range O 2.33, S 2.08, D 2.67.
- Provider effect (mean O over all answers): INTEGRITY Gemini 5.67 vs Groq 2.85; EXPLAINABILITY
  8.56 vs 5.69; SAFETY 3.22 vs 1.77. Runs mix providers because of the fallback chain, so
  between-run spread is largely between-provider.

## Latency

- LLM, successful calls: mean 19.8 s (includes in-run 503 backoff before falling through to Groq);
  all 60 runs including fallbacks: 10.3 s.
- Deterministic: ~2 ms/packet (1.98 ms in the committed run; 2.14 ms in the replay).
- Fallback rate: 38/60 = 0.63.

## Comparability of post-run changes

Before any real packet was executed (no effect on comparability): risk_present rule correction
(triggered risk wins over an unrelated failed gate); anonymization of all suite identifiers.

After some runs had completed (none changes a stored answer, the prompt, the parser, the
evaluators or the packets):
- `--retry-fallbacks` / provider-unavailable counts: only decides which outage runs are re-attempted;
  successful records are never re-called. Retried answers come ~1 h later from Groq only (Gemini
  still out), which shifts the provider mix of P04 run 5, P05 run 1, P09 run 4.
- Localization fix: analysis only; skips packets without an LLM answer; applied to all data.
- This session: repeatability restricted to pairs with ≥ 2 answers, latency reported for successful
  calls only, provider variation and attempt counts added: analysis only, applied to all data.
- L1 (commit e384363) pinned the deterministic path to `mapping="v3"`; deterministic decisions
  verified identical to the committed `deterministic.json`.

## Limitations

- Incomplete: 22/60 answers, 6/12 packets, 18/36 pairs; P05 and P09 rest on one answer each.
  Statistics are descriptive.
- Suite cards self-disclose their injected flaws in prose; names anonymized, disclosure text kept.
  P04's card mentions "variant 3/1's base slice" (provenance prose).
- The LLM did not see TrustLens's own risk decisions (`risks_triggered`, `aspect_scoring`, gates,
  status); production llm_v1 does. Results describe blind interpretation, not production.
- LLM `evidence_sufficient` not elicited by the frozen prompt (null); LLM "risk present" uses the
  prompt's O ≤ 5 definition.
- FAIRNESS/ROBUSTNESS are never LLM-rated in TrustLens; not compared.
- Provider org/account ids in stored error text redacted.
