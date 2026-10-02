# Round 3 — L3: card-based risk flags fired on clean controls (2026-10-03)

Branch `round-3-limitations`. Methodology `v3-hardening-2026` → `v4-disclosure-gaps-2026`;
probes `tl-safety/tl-explainability/tl-integrity` v1.0 → v1.1. `ground_truth.json`
and its detection rules are unchanged.

## Problem

In the 2026-10-02 suite the evidence-level rule flagged both clean controls on SAFETY
and EXPLAINABILITY (rate 1.0) and one on INTEGRITY (0.5). Every flag came from an
*absence* of documentation or identity evidence, not from evidence of a defect:

| risk id | fired on | what it measures |
|---|---|---|
| S-GOV-DISCLOSURE-GAP | every model | a required safety-disclosure card section is missing |
| E-DOC-INCOMPLETE | both controls, V3, V4, V4b, V6 | a required documentation section is missing |
| I-INT-REV-UNPINNED, I-INT-MANIFEST-MISSING | every local folder | a local folder has no Hub revision / Hub file listing |
| I-INT-LICENSE-UNDISCLOSED | V3 | no structured license |

## Change

- `risks_triggered` now holds only **positive evidence of a problem**:
  E-DOC-CONTRADICTION, I-INT-BYTES-DIVERGE, I-INT-LISTING-DRIFT.
- The five ids above move to a new `disclosure_gaps` list. When only gaps are present,
  `aspect_scoring = "disclosure_gap"`. SAFETY/EXPLAINABILITY checks, `coverage_ratio`
  and flags are unchanged, so their bands do not move. The LLM prompt still sees the
  gaps in the evidence block.
- Score effect (INTEGRITY only): the heuristic band reads the check pass rate. For a
  local folder with a weight file, `revision_pinned` and `files_listed` now pass. The
  2-label control, for example, goes from 3/6 to 5/6.
- Local model folders: the integrity probe hashes the weight file
  (`model.safetensors` / `pytorch_model.bin`). When `train_manifest.json` records
  `model_safetensors_sha256`, that value is the trusted reference, giving `match` or
  `diverge` (I-INT-BYTES-DIVERGE). With a weight hash, `revision_pinned` and
  `files_listed` pass, because the folder is content-addressed. With only a
  self-computed hash, the cryptographic claim stays unverified (`not_performed`).
  A folder with no weight file keeps the identity gaps.

## Control flag rate, before → after (offline replay, not a re-run)

Method: the v1.1 card/identity logic was replayed on the suite's exact inputs:
- cards from `results/flawed_model_suite/cards|models/*/README.md`
- license from the stored integrity evidence
- the real weight files
- the toxic-bert card from the Hub

Every model's stored `coverage_ratio` was reproduced exactly. The frozen rule
(`compare_ground_truth.evidence_flag_one`) and the stored behavioural safety evidence
were applied unchanged. No thresholds were tuned, and nothing was written to `results/`.

| dimension | control flag rate before | after | injected recall before | after | non-injected flags before | after |
|---|---|---|---|---|---|---|
| SAFETY | 1.00 | 0.00 | 5/5 | 3/5 | 8/8 | 0/8 |
| EXPLAINABILITY | 1.00 | 0.00 | 2/2 | 1/2 | 2/11 | 2/11 |
| INTEGRITY | 0.50 | 0.00 | 3/3 | 0/3 | 10/10 | 0/10 |

Earlier evidence-level recall on these three dimensions was not a detection. The
clean controls were flagged at the same rate. After the split:
- SAFETY is flagged only by the behavioural severe-FNR rule (V5, sweep r075, r100).
- The overclaiming cards (V4, V4b, V6) are flagged under EXPLAINABILITY through
  E-DOC-CONTRADICTION. The ground truth attributes that defect to INTEGRITY, so for
  V4 and V4b these flags count as false positives under the frozen rule.
- The skeleton card (V3) is now only a disclosure gap.
- No card-only INTEGRITY defect is detected at evidence level. V4b's weights `match`
  their train_manifest reference.

## Not changed

These stay as they were:
- detection rules and ground truth
- historical results
- the LLM prompt template and version (`osd-llm-v2-compact-2026-10-02`)
- band formulas

API/UI: `disclosure_gaps` is stored in probe `metric_values` and evidence artifacts but
is not yet a field of `ProbeEvidenceRead`. The UI shows the gap through
`aspect_scoring` ("disclosure gap") and the `missing_*` flags.
