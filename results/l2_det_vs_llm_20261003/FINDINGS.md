# L2 — deterministic vs LLM interpretation: findings (2026-10-03)

Pre-registration: `docs/superpowers/plans/2026-10-03-round3-L2-det-vs-llm.md`.
Numbers: `analysis.json` / `analysis.md` (regenerated with `--replay` from `llm_responses.jsonl`).
No winner, no ranking; both outputs kept verbatim.

## What ran

- 12 anonymized packets (`packets/`, hashes in `packet_index.json`; id→model map in
  `packet_sources.json`, never read by an evaluator). Every deterministic record and every
  LLM run carries the packet sha256; all 72 match the index (`packet_hashes_identical_across_evaluators: true`).
- Deterministic: production pure functions + v3 `HeuristicOSDAgent`, ~2 ms/packet.
- LLM: production `HybridOSDAgent._get_llm_judgment`, prompt `osd-llm-v3-decision-first-2026-10-03`
  (unchanged), 5 live runs per packet = 60 calls.

## Provider availability (the dominant outcome)

- 19/60 runs answered (Gemini 9, Groq 10); 41/60 fell back. All 41 are provider-unavailable
  (no text returned): Gemini 503 "high demand" then 429 RESOURCE_EXHAUSTED (quota), Groq 429
  tokens-per-day (limit 200,000), NVIDIA 404 "Function not found" (the configured
  `mistralai/mistral-large-2-instruct` endpoint no longer exists for this key — a production
  defect of the third fallback, recorded, not fixed here).
- Parser failures 0, output truncations 0. Prompt truncation (card > 5,000 chars): 5 runs (P01).
- Only P01–P04 have LLM answers (P04: 4 runs). P05–P12 have none, so 24 of 36 packet×dimension
  pairs are category `truncation_fallback`. The remaining runs can be completed after the quotas
  reset with `--resume --retry-fallbacks` (re-attempts only provider-unavailable runs; the failed
  record stays in the log and is counted as superseded). Provider org/account ids in error text
  were redacted after the run.

## Agreement on the 12 answered pairs (4 packets x I/E/S)

| measure | value |
|---|---|
| exact status agreement (3-valued risk_present) | 4/12 = 0.333 |
| risk-present agreement where both definite | 4/9 = 0.444 |
| localization exact set match / mean Jaccard | 0/4 / 0.125 (answered packets P01–P04) |
| severity S exact / within 1 / MAE | 0.333 / 0.417 / 1.67 |
| O/S/D exact triple; MAE O/S/D | 0.25; 1.75 / 1.67 / 2.00 |
| deterministic UNCERTAIN pairs (answered packets) | 3 (INTEGRITY, gate-blocked) |
| LLM UNCERTAIN | 0 — the frozen prompt has no abstain option |

Categories on answered pairs: evidence_interpretation 5, insufficient_evidence 3, agree 3, severity 1.

Where they disagree:
- SAFETY (4/4 disagree): the LLM puts O ≤ 4 on every packet ("risk present"). The deterministic
  risk layer says NO for all, because card-based safety findings are disclosure gaps (L3) and
  behavioural severe_fnr has no risk ID. The deterministic v3 band itself is low on P02–P04
  (2/2/2), so the deterministic path disagrees with itself between its risk layer and its band.
- INTEGRITY: deterministic is UNCERTAIN on unpinned/listing-unverified folders (P01, P02, P04);
  the LLM always answers. On the tampered packet (P03, MISMATCH) both say risk present
  (5/5 runs); severity differs (det S=7, LLM median S=3).
- EXPLAINABILITY: agree on P02–P04 (O=9 both, LLM 9/9/9 in ≥4/5 runs); on P01 (real Hub card,
  truncated in the prompt) the LLM says risk present (O 2–5), deterministic says no risk (6/6/6).

## LLM repeatability (answered pairs)

- risk_present identical in all valid runs: 9/12 pairs; mean modal agreement 0.93.
- identical O/S/D triple in all valid runs: 1/12 pairs; mean range O 2.25, S 1.83, D 2.67.
- Strong provider effect (runs mix providers because of the fallback chain): mean INTEGRITY O
  Gemini 5.7 vs Groq 2.9; SAFETY O 3.2 vs 1.8; EXPLAINABILITY O 8.6 vs 6.2. Variation across
  runs is largely between-provider, not within-provider.
- Mean LLM call time (answered runs) ~21.6 s including backoff; deterministic ~2 ms/packet.

## Limitations

- Coverage: 4/12 packets answered; agreement statistics rest on 12 pairs and are descriptive only.
- The suite's model cards disclose their injected flaws in prose ("deliberately injected safety
  flaw"); names were anonymized but disclosure text is evidence and was kept, so LLM "detection"
  on such packets may be reading the disclosure. P04's card mentions "variant 3/1's base slice"
  (provenance prose, not its own identity).
- The LLM's evidence view excludes TrustLens decisions (`risks_triggered`, `aspect_scoring`,
  gates, status); production llm_v1 sees them. Results describe blind interpretation, not production.
- LLM `evidence_sufficient` is not elicited by the frozen prompt (null); LLM "risk present" uses the
  prompt's own O ≤ 5 definition.
- FAIRNESS/ROBUSTNESS are never LLM-rated in TrustLens; not compared.
- Deterministic O/S/D here is the v3 mapping (pinned; L1 later adds v4).
