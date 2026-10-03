# External Hub validation — pinned Hugging Face models (2026-10-03)

Seven real Hugging Face text-classification models, each pinned to an immutable revision SHA, audited
with the current TrustLens methodology (`v8-osd-calibrated-map-2026`), unchanged. **Descriptive audit
profiles only.** No ranking and no trustworthy/untrustworthy label: no ground truth exists for these
models, and TrustLens's FRIES numbers are reproduced as reported, not used to compare them.

Script: `backend/app/scripts/run_external_hub_validation.py` (`select` → `run` → `profile`).

## Protocol

- **Selection** (`selection.json`, written before any evaluation). Models were chosen deliberately so that
  architecture, size, head type, training data, label scope, documentation and language scope vary
  across the set. This is not a sample of the Hub. Every pinned SHA was re-resolved against the Hub
  (`model_info(revision=sha).sha == sha`) and its config checked for the binary contract. Weight-file LFS
  sha256 values are recorded.
- **Stack**: Docker `api` and `worker` images rebuilt from HEAD `4f58db9` (all round-3 methodology
  commits). Container sources were checked against `git show HEAD` for agent.py, fairness.py,
  methodology_version.py, evaluate_pipeline.py and llm_client.py; they are identical once line endings
  are normalized. `CURRENT_METHODOLOGY_VERSION = v8-osd-calibrated-map-2026` in both containers. Worker
  torch 2.14.1+cu130, CUDA available (RTX 4060 Laptop, 8 GB). Image ids are in `run_log.json`.
- **Contract**: identical to the earlier suite/Hub runs (`run_flawed_suite_eval.create_and_run_evaluation`):
  suite `eval_set.csv` (3,000 English Civil Comments rows, `identity_ref` group column, `severe` column),
  FAIRNESS + ROBUSTNESS + SAFETY contracts, `AI_AUTONOMOUS`, `assessment_engine = llm_v1`. For
  multi-label models the toxicity head is the target (`multilabel_target_index`).
- **Execution**: sequential, one model at a time (RAM/VRAM).
- **Verification** (`profiles.json` → `completeness`): 7/7 evaluation files, 7/7 `FINALIZED`, 7/7
  evaluated revision equals the pin, 7/7 with all five probes. `SHA256SUMS` covers every file here.

## What the profiles show (descriptive)

See `PROFILES.md` for one table per model; `evaluations/` holds the full API responses.

- **Risk IDs raised**: F-FAIR-EOPP on `unitary/unbiased-toxic-roberta` (EOD 0.093, CI 0.020–0.162) and
  `facebook/roberta-hate-speech-dynabench-r4-target` (0.130, CI 0.075–0.181); R-ROB-PERT on the facebook
  model (accuracy drop 0.072). No other model triggers a risk ID.
- **Disclosure gaps** (documentation findings, not risks): E-DOC-INCOMPLETE and S-GOV-DISCLOSURE-GAP on
  all 7; I-INT-LICENSE-UNDISCLOSED on `martin-ha/toxic-comment-model` and the facebook model (no
  license in card metadata). Card length ranges from 570 chars (facebook) to 11,095 (`unitary/toxic-bert`).
- **Integrity**: all 7 `VERIFIED`, hash comparison `match` (pinned revision).
- **Measured behaviour** (same 3,000 rows): clean accuracy 0.664–0.927, perturbation accuracy drop
  0.010–0.072, severe-harm FNR 0.089–0.837 (n = 282 severe rows), benign FPR 0.018–0.368. The highest
  severe-harm FNR (0.837) is the hate-speech model, whose label scope (hate) differs from the eval
  labels (toxicity). The value measures that mismatch as much as the model.
- **FRIES status**: `unitary/toxic-bert` is **withheld**. Its FAIRNESS gate G-FAIR-CI-WIDE failed
  (EOD 0.174, CI 0.098–0.252 too wide), so the evidence is insufficient for a FAIRNESS score. The other
  6 are scored; the values are in `PROFILES.md`, as reported.

## Deviations and caveats

- **LLM provider availability.** Gemini returned 429 (quota) and Groq returned 429 after the first model.
  The NVIDIA endpoint `mistralai/mistral-large-2-instruct` is still 404 (the committed configuration;
  the nemotron change was discarded on request). Result:
  - `unitary/toxic-bert`: INTEGRITY/EXPLAINABILITY O/S/D from Groq `openai/gpt-oss-120b` (prompt
    `osd-llm-v3-decision-first-2026-10-03`). SAFETY keeps the heuristic band because behavioural evidence
    exists; the LLM's card judgment is kept as metadata only.
  - The other 6 models: `heuristic_fallback` for INTEGRITY/EXPLAINABILITY/SAFETY.
  - FAIRNESS/ROBUSTNESS always use the heuristic mapping (by design).

  The O/S/D *source* therefore differs between the first model and the rest; each aspect records it
  (`osd_source`, `osd_provider`). This is the production fallback behaviour, not a methodology change.
- **Redaction.** A Groq organization id in stored provider error text was replaced by
  `org_<redacted>` in `evaluations/*.json` (same practice as L2). No other content was changed.
- **Overlap with earlier runs.** All 7 repos were also in the 2026-10-02 15-model Hub run, at the same
  SHAs, under the pre-round-3 methodology. That run is not modified or compared here.
- One run per model; no repeat runs. Card metadata comes from the Hub at evaluation time.
- No result folder, `ground_truth.json`, FRIES formula, risk rule, threshold, O/S/D mapping or scoring
  code was changed.
