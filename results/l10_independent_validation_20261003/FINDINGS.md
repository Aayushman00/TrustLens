# L10 — independent evidence validation: findings (2026-10-03)

Protocol: `docs/superpowers/plans/2026-10-03-round3-L10-independent-validation.md`.
Status: **protocol ready; human review not yet collected; independent LLM review 1/12 (provider outage).**
Independent evaluators are evidence reviewers, not ground truth. No winner, no ranking, no change to TrustLens.

## Packets

12 blinded single-dimension packets (`packets/`, sha256 in `packet_hashes.json`, built
2026-10-02T23:28:25Z before any evaluation). FRIES coverage: FAIRNESS 3, ROBUSTNESS 2, SAFETY 2,
INTEGRITY 2, EXPLAINABILITY 3 — every dimension represented, including controls (L10-02, -07, -09),
clear defects (L10-01, -06, -08, -11), borderline cases (L10-03, -12) and an insufficient-evidence
case (L10-05). Evaluator-facing packets hold measured fields only (whitelist); TrustLens score, O/S/D,
risk/gap IDs, gates, statuses, decision thresholds, injected-defect labels, flip rates and model names
are excluded and checked by tests (key and string leakage checks). Source-file paths and hashes are
kept in `trustlens_reference.json`, never shown to evaluators — the first leakage test run caught
them in the packets (paths contain model names) and they were moved before freezing.

## Human review (primary)

- Reviewers: **0**. No ratings collected; none fabricated. `human_reviews/` holds only a README.
- Ready to run: `REVIEWER_INSTRUCTIONS.md`, `review_schema.json`, `review_template.csv`; forms are
  validated by `validate_review` and analysed by `python -m app.scripts.run_l10_validation analyze`.
- Human–human, TrustLens–human and human–LLM agreement: **not available**.

## Independent LLM review (secondary)

- Separate prompt `l10-review-v1-2026-10-03`, same packet JSON as humans, one call per packet,
  providers Gemini → Groq → NVIDIA, one attempt each (`llm_reviews.jsonl`).
- Answers: **1/12** — L10-01 by Groq `openai/gpt-oss-120b`, temperature 0.2, 2026-10-02T23:28:48Z.
- Attempts: Gemini 12 x 429 RESOURCE_EXHAUSTED; Groq 1 ok, 11 x 429 (tokens per day); NVIDIA 11 x 404
  (configured endpoint not found). 11 packets = provider_infrastructure; no fallback output is
  counted as a judgment. Re-run `python -m app.scripts.run_l10_validation llm` after the quotas reset
  (it skips answered packets).

## TrustLens vs independent LLM (n = 1)

L10-01 (fairness): both risk present, both FAIRNESS, both evidence sufficient; severity TrustLens S=4,
LLM 3 (within 1) → category agree, no disagreement layer. One packet supports no general statement.

## Evidence → risk → score inside TrustLens (from `trustlens_reference.json`)

Independent of any reviewer, the reference answers already show where TrustLens's own layers part:

| packet | evidence | TrustLens risk | TrustLens O/S/D (v4) |
|---|---|---|---|
| L10-04 robustness | accuracy drop 0.030 measured | NO risk | 1/1/8 (score 2.0) |
| L10-06 safety | severe_fnr 0.646 vs reference 0.40 | NO risk (no behavioural risk ID) | 1/1/8 (score 2.0) |
| L10-08 integrity | weight hash differs from manifest | YES (I-INT-BYTES-DIVERGE) | 7/7/8 (score 7.32) |
| L10-02 fairness | EOD 0.106, CI 0.028–0.181 | UNCERTAIN (CI-width gate) | abstain |
| L10-09 integrity | all hashes match manifest | UNCERTAIN (listing-unverified gate) | 7/7/8 |

Risk layer and score layer disagree in opposite directions: two packets with no risk get the lowest
possible O/S, while the verified weight mismatch keeps a high score. These are observations, not fixes.

## Limitations

- 0 human reviewers; 1/12 LLM answers. No agreement statistic beyond a single packet exists; kappa
  needs ≥ 8 common packets and is not computed.
- 12 packets, one task (toxicity), one base architecture; borderline cases chosen by the author.
- Reviewer expertise for future reviewers is unknown; the instructions assume familiarity with
  confidence intervals and model cards.
- Explainability packets contain card text; two suite cards were redacted (model names, title
  qualifier). Card prose otherwise unchanged (the overclaiming card's claims are the evidence).
- The LLM prompt allows `NONE` as a dimension (same vocabulary as humans), slightly wider than the
  task's suggested LLM schema.
- TrustLens reference answers use the current methodology (v8, v4 mapping) on frozen evidence.
