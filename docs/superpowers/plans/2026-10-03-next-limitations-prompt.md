# Prompt: fix TrustLens's remaining limitations (round 3)

Paste everything below the line into a new Claude Code session at the repo root.

---

You are continuing work on TrustLens (branch `hardening-month`, not pushed). Read first, in order:

1. `results/flawed_model_suite/FINAL_RESULTS_20261002.md` (what the experiments showed)
2. `docs/superpowers/plans/2026-10-02-hardening-audit-findings.md` (findings A1–A12 and their status)
3. `results/flawed_model_suite/ground_truth.json` (hidden labels + pre-registered detection rules)
4. `results/flawed_model_suite/final_20261002_analysis/analysis.md` and `final_20261002_analysis_with_sweep/analysis.md`

Treat code and stored results as the source of truth. Do not write the academic report.

## Rules

- Never edit or overwrite existing result folders (`eval_results*`, `final_20261002_*`, `sweep_20261002_*`, `hub_final_*`). New runs go to new folders created with `fresh_out_dir`.
- Any change that alters a score, band, flag or prompt bumps `CURRENT_METHODOLOGY_VERSION` (`backend/app/scoring/methodology_version.py`) or `PROMPT_VERSION` (`backend/app/osd/llm_client.py`) and is listed in that file's comment.
- TDD for every change: write the failing test, watch it fail, implement, watch it pass. After each fix run the whole suite: backend `python -m pytest -q`, frontend `npm test`, worker `python -m pytest -q`. Add no new ruff errors (baseline: 31).
- Keep the pre-registered detection rules in `ground_truth.json` unchanged. If a rule should change, add a new rule version next to the old one and report both.
- Do not add Claude co-author or attribution lines to commits. Commit per fix. Do not push.
- Long runs: the docker stack shares about 16 GB of RAM. Run evaluations in the foreground in chunks under 10 minutes, or the background job may be killed. Rebuild `api` and `worker` after backend changes:
  `docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.experiment.yml build api worker && ... up -d api worker`.
  Use `../.venv/Scripts/python.exe` with `USE_TF=0` for training.
- Negative results are results. Do not tune thresholds against the existing suite to make detection look better. Any recalibration must be fitted on held-out data and then evaluated on the frozen suite.

## Limitations to fix (in priority order)

### L1. The decision layer compresses severity (main research gap)
- **Evidence:** the 0→100% flip sweep moves Fairness 8.65→7.32 and Safety 6.95→5.24, while the evidence moves monotonically (ρ = 1.0).
- **Do:** design an evidence-to-O/S/D mapping v4 in `backend/app/osd/agent.py`. Calibrate it on a NEW held-out sweep:
  - train it with `make_severity_sweep` at different rates and seed 43;
  - add a `--seed` option to the script;
  - store the training data in a new folder.
- **Then report:**
  - Spearman correlation and score range on the frozen sweep;
  - re-run `compare_ground_truth` under rule v1 (frozen) and the new mapping.
- **Keep:** the v3 bands for comparison (abstain logic unchanged).

### L2. LLM-rated dimensions are noisy and depend on a provider quota
- **Evidence:** Integrity/Explainability std up to 2.2; 11/45 runs fell back; the daily quota was exhausted.
- **Do:**
  - (a) add a deterministic card-evidence band for Integrity/Explainability (`HeuristicOSDAgent` already has `_card_band`) as the DETERMINISTIC-mode baseline;
  - (b) add an LLM response cache keyed by `llm_prompt_sha256` + model + temperature, so identical prompts are not re-billed;
  - (c) add a `--engine` flag to `repeat_eval` and run a deterministic vs `llm_v1` comparison (RQ4) on the 9 suite models, 5 runs each, in new folders;
  - (d) report detection, std, runtime and fallback counts side by side.

### L3. Card-based risk flags fire on clean controls
- **Evidence:** `control_flag_rate` is SAFETY 1.0, EXPLAINABILITY 1.0, INTEGRITY 0.5.
  - S-GOV-DISCLOSURE-GAP fires on real model cards.
  - I-INT-REV-UNPINNED fires for every local folder.
- **Do:**
  - Split "documentation gap" from "defect" severity.
  - Make the local-folder pin check use the `train_manifest.json` / weight-file sha256 as the revision, so locally registered suite models are not unpinned by construction.
  - Re-run the evidence-level rule as a new rule version, and report the control flag rate before and after.

### L4. Binary fairness evidence can never raise a flag
- **Do:** emit `aspect_scoring` and `risks_triggered` (an F-FAIR-* risk) from the binary fairness path in `backend/app/probes/fairness.py` when the bootstrap CI of EOD (or `excess_dpd`) excludes a pre-declared epsilon. Mirror `fairness_multiclass.py`.
- **Excess DPD:** make it direction-aware using per-group bias b_g = P(Ŷ=1|g) − P(Y=1|g) and gap = max b_g − min b_g. Keep the old value as `excess_dpd_v1`.
- **Re-check V1 honestly.** It may still be undetectable.

### L5. The V1 fairness defect is undetectable on this eval set
- **Do:**
  - Build a fairness eval set where the identity groups have similar base rates (stratified resample from Civil Comments, seed 42, with a manifest).
  - Add it as a second dataset.
  - Re-evaluate V1, V3 (clean) and the fairness sweep on it.
- **Report** whether V1 becomes separable. Do not drop the original eval set.

### L6. Severity is only one level in the main suite and safety scoring is coarse
- **Do:**
  - Safety band S currently jumps 3/6 on `fnr_ratio > 1.5`; replace it with a graded function of `severe_fnr` vs the control.
  - Extend the sweep to robustness: train-slice size 600/1500/4000 at fixed epochs. This is one-knob only; justify why.

### L7. Integrity gaps
- **Do:**
  - Support sharded checkpoints (`model-0000x-of-0000y.safetensors` + index) in `backend/app/probes/integrity_artifact.py`.
  - Persist `artifact_verification` into the evidence artifact dict, not only `metrics`.
  - Remove the stale ADR comment at `integrity.py:47`.
  - Write an ADR note in `docs/` that supersedes ADR 0012 for this check.

### L8. Pipeline robustness leftovers
- **Do:**
  - Enqueue after commit: commit before `enqueue_and_record` in `evaluation_service_v2.create_from_draft` and the legacy create path. Keep the worker retry as a backstop.
  - Make `on_failure` mark PENDING evaluations FAILED when the exception is `EvaluationNotVisibleError`.
  - Put `aspect_scoring`, `risks_triggered` and `status` first in the LLM evidence block, so truncation cannot drop them. This is a prompt version bump.

### L9. Minor deferred items
- `export_artifacts.py`:
  - make the container name configurable;
  - make re-runs idempotent (no nested `<eid>` folder).
- `make_severity_sweep.py`: `parse_args()` is called twice.
- `extra_models_eval --only`: error on repos that are not in the selection.
- `summarize_hub_models.py`: `.get("ai_suggestion", {})` breaks when the value is null.
- `compare_ground_truth.severity_sweep`: use the per-run mean when `evidence_identical_across_runs` is false.

### L10. Human validation (needs people; prepare only)
- Packets exist in `results/flawed_model_suite/human_validation_20261002/`.
- Write the reviewer instruction sheet for the two rounds.
- Add an `analyze` run on a synthetic 3-rater CSV as a test fixture.
- Do NOT fabricate ratings.

## Finish

1. Run all suites.
2. Dispatch one fresh reviewer subagent (most capable model) over `git diff <start>..HEAD` (excluding `results/`).
3. Fix Critical/Important findings with RED→GREEN tests.
4. Write `results/flawed_model_suite/FINAL_RESULTS_<date>.md` from the new result files only.
5. Commit; do not push.

Final message:
- what passed;
- what failed;
- unexpected findings;
- remaining limitations;
- every ruling you made, with its cost if wrong.
