# Round 3D — L2: deterministic vs LLM evidence interpretation (pre-registration)

Written 2026-10-03, before any packet was built or any LLM call was made.
Script: `backend/app/scripts/run_l2_interpretation.py`. Output: `results/l2_det_vs_llm_20261003/`.

## Question

On the SAME frozen evidence, does the frozen LLM interpretation
(`PROMPT_VERSION = osd-llm-v3-decision-first-2026-10-03`, unchanged) agree with the
current deterministic TrustLens interpretation, and how repeatable is it?
Factual characterization only: no winner, no ranking, no adjudication.

## Scope

The frozen `llm_v1` prompt rates INTEGRITY, EXPLAINABILITY and SAFETY only;
FAIRNESS/ROBUSTNESS never reach an LLM in TrustLens. Comparing them would need a
new prompt, so they are out of scope (recorded as a limitation, not added).

## Packets (pre-declared set, 12)

One packet per controlled condition with distinct I/E/S evidence:
reference_toxicbert_2label, variant1_fairness, variant1_fairness_tampered,
variant2_robustness, variant3_explainability, variant4_integrity,
variant4b_integrity_clean, variant5_safety, variant6_compound,
sweep_safety_r025, sweep_safety_r075, sweep_safety_r100.

Packet = raw evidence, schema `l2-evidence-packet-v1`:
- `card_text`: the model folder's README.md with the folder name replaced by the
  packet id (P01..P12, assigned in the order above); other card text unchanged.
- `model_ref` = `/models/<packet id>`, `model_revision` = `local`.
- `artifact_verification`: `verify_local_artifacts` on the folder. For
  variant1_fairness and variant1_fairness_tampered an operator manifest is
  supplied = `build_artifact_manifest(variant1_fairness)` (the known-good copy,
  as in the tamper demo), so the pair yields VERIFIED / MISMATCH. Others as found.
- `safety_behavior`: the frozen L6 measurement (`results/defect_severity_20261003/analysis.json`)
  where one exists (reference, variant3, r025, variant5, r075, r100); otherwise
  `{"status": "NOT_APPLICABLE"}`.

Never in a packet or prompt: FRIES score, O/S/D, `risks_triggered`,
`scored_risk_id`, `aspect_scoring`, probe status/gates (`status`, `probe_status`,
`reliability`), claim verdict text (`claims`), `flags`, model folder name,
injected-defect label. The id→source map is written to a separate file that no
evaluator reads.

Hash: sha256 of canonical JSON (sorted keys, compact). Both evaluators record
the hash of the packet they received; the analysis asserts equality.

## Deterministic evaluator

Recomputes the current probe evidence from the packet with the production pure
functions (`evaluate_integrity` + `local_integrity_extras`, `evaluate_explainability`,
`evaluate_safety` + the behaviour fields), then `HeuristicOSDAgent` (v3 bands) for O/S/D.
Per dimension: status, aspect_scoring, risks_triggered, disclosure_gaps, failed gates,
- evidence_sufficient: NO if status INSUFFICIENT_EVIDENCE / aspect_scoring not_scored;
  UNCERTAIN if mapping_blocked or a failed gate; else YES.
- risk_present: YES iff risks_triggered non-empty or aspect_scoring in
  {risk_detected, scored_risk}; otherwise NO when evidence_sufficient is YES, else UNCERTAIN.
  (Pre-run correction, found by the unit test before any packet was built: the first
  wording made a triggered I-INT-BYTES-DIVERGE "UNCERTAIN" whenever an unrelated gate
  also failed, although TrustLens reports the risk.)
- severity = S of the v3 band (the project's only structured severity scale).

## LLM evaluator

Production `HybridOSDAgent._get_llm_judgment` (provider order, retries, parser,
truncation handling unchanged) on an `AgentContext` built from the packet:
card_text plus, per dimension, the deterministic evidence view with the keys above
removed. The deterministic answer is never in the prompt. Derived fields
(rule fixed here):
- risk_present = YES iff O <= 5 (the frozen prompt's own definition: "a real risk
  is clearly present, O<=5"), else NO. The prompt has no abstain option, so the LLM
  cannot answer UNCERTAIN.
- evidence_sufficient: not elicited by the frozen prompt → recorded as null.
- severity = S.

5 independent live runs per packet (60 calls). Every raw response is stored in
`llm_responses.jsonl` keyed by (packet sha256, run index); a stored response is
only ever reused for the same run index (resume / `--replay` re-parse), never
copied to another run index, and replayed runs are marked as such.

## Comparison (per packet x dimension; LLM side = modal answer over valid runs)

- exact status agreement (3-valued risk_present), risk-present agreement where both definite
- localization: per packet, set of dimensions with risk_present YES, exact-set match and Jaccard
- severity: S exact / |dS| <= 1 / MAE; O/S/D: exact triple, per-component MAE
- abstention: UNCERTAIN counts each side; LLM fallback count
- runtime: deterministic ms/packet; LLM s/call
- repeatability: modal-agreement fraction for risk_present, O/S/D range and std,
  distinct triples, fallback, parser failures, truncations (prompt / output)

Disagreement category (first that applies):
1. parser/format failure (all runs for the packet failed to parse)
2. truncation/fallback (all runs fell back, or output truncated)
3. insufficient-evidence (deterministic UNCERTAIN, LLM definite)
4. localization (risk_present differs, and the side saying NO flags another
   dimension of the same packet)
5. evidence interpretation (risk_present differs otherwise)
6. severity (risk_present agrees, |S_det - S_llm| >= 2)

Both outputs are preserved verbatim; no evaluator is changed after seeing results.

## Deviations recorded after the run (no evaluator, rule or prompt changed)

1. All three providers became unavailable mid-run (Gemini quota, Groq tokens-per-day,
   NVIDIA 404); 41/60 runs fell back without any model text. Added after the run:
   `provider_unavailable` / superseded-record counts and `--retry-fallbacks` so those runs can
   be re-attempted later under the same run index (failed records kept in the log).
2. Analysis fix before reporting: localization statistics now skip packets with no LLM
   answer (an empty LLM set had been counted as an exact match).
3. Provider org/account identifiers in stored error text redacted.
4. Session 2 (2026-10-02 23:13–23:17 UTC): `--resume --retry-fallbacks` re-attempted only the 41
   provider-unavailable runs; 3 answered (Groq), 38 still unavailable. Stored answers reused,
   not re-called; log append-only. Analysis-only changes in the same session: repeatability counted
   only on pairs with >= 2 valid runs, latency also reported for successful calls only, provider
   variation and per-provider attempt counts added. Evaluators, prompt, parser and packets unchanged.
