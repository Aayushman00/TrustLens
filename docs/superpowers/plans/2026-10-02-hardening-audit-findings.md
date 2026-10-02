# Hardening month — audit findings and status (2026-10-02)

Branch `hardening-month`. Source of truth: code + stored results, not docs.

## Findings

| ID | Finding | Evidence | Status |
|---|---|---|---|
| A1 | Original toxic-bert run was a constant predictor yet scored Fairness 9/9/8 | `eval_results_v2/trustworthy_unitary_toxic-bert.json`: DPD=0, EOD=0, clean_acc 0.7987 = majority-class rate 0.80 | Fixed: `prediction_gate.py` (≥98% one class → INSUFFICIENT_EVIDENCE) |
| A12 | Root cause of A1: `inspect_model_config` ignored `config.problem_type`; multi-label heads were argmax-decoded | `model_inspection.py` before this branch | Fixed: MULTILABEL_TARGET_REQUIRED gate (draft + submit), native sigmoid decode, migration 016 |
| A2 | V4 (integrity) weights byte-identical to V1 (fairness) → V4 inherits V1's fairness defect | sha256 `5918a851…` for both `model.safetensors` | Resolved: V4 labelled FAIRNESS+INTEGRITY compound in `ground_truth.json`; new `variant4b_integrity_clean` (variant3 clean weights + V4 card) isolates INTEGRITY |
| A3 | Eval set's own label-rate gap across `identity_ref` is 0.505 (> every model's DPD). After subtraction V1's defect vanishes: excess_dpd 0, EOD 0.164 vs 2-label reference 0.174 | `results/flawed_model_suite/excess_dpd_rederived.json` | **Negative result** — V1 fairness defect not detectable on this eval set |
| A4 | Old robustness band (accuracy-based) gave 9/9/9 to all forged models; V2's 4.1-pt drop < ε=0.05 | `eval_results_v2/*` | Fixed: drop-based band (V2 → S=6, others S=9); methodology `v3-hardening-2026` |
| A5 | `llm_v1` O/S/D disclosed as "legacy heuristic … not an LLM assessment" | stored `mode_disclosure` | Fixed: LLM-specific disclosure; provider/model/temperature/prompt hash per aspect |
| A6 | Binary fairness wide-CI path says "scoring blocked" but returns EVALUATED and is scored | `fairness.py` G-FAIR-CI-WIDE branch | Fixed: binary wide-CI path sets `aspect_scoring=mapping_blocked`; band abstains (regression test) |
| A7 | Heuristic robustness band ignored probe gates | `osd/agent.py` | Fixed: abstain on `mapping_blocked` / `not_scored` |
| A8 | `results/` and `report/` untracked in git | `git status` | Fixed: results, reports, evidence tracked; weights ignored |
| A10 | Rerunning `run_flawed_suite_eval` overwrote historical `eval_results/` | old `OUT_DIR` | Fixed: required `--out`, `fresh_out_dir` refuses non-empty dirs |
| A11 | Integrity probe never hashes weights; I-INT-BYTES-DIVERGE compares caller-supplied strings (`probe_config.extra.integrity`), unreachable from the v2 API | `integrity.py`, `integrity_eval.py:372` | Fixed: Hub models' cached weight bytes are hashed against the Hub LFS sha256 (15/15 `match` on real models) |
| — | Safety was card-only | `safety.py` | Fixed: behavioural severe-FNR branch + SAFETY contract (migration 015); never-toxic collapse measured, always-toxic refused |

## Final experiments

See `results/flawed_model_suite/FINAL_RESULTS_20261002.md`.

## Not yet run (superseded — all below were run on 2026-10-02 except human validation and Hub publishing) (need stack restart on new code, `alembic upgrade head`, secrets, people)

- 5× repeat runs (`python -m app.scripts.repeat_eval --runs 5 --out <new>`)
- Suite with behavioural safety (`python -m app.scripts.run_flawed_suite_eval --out eval_results_v5`)
- Hub-hosted variants (`publish_suite_to_hub --prefix <user>` needs HF_TOKEN, then `--hub-prefix`)
- Extra models: selection frozen in `results/flawed_model_suite/extra_models.json` (rule v3); `python -m app.scripts.extra_models_eval run --out eval_results_extra`
- Human validation: `docs/human_rating/protocol.md`
- Report regeneration (deferred until experiments land)

## Known limitations (deferred minors)

- `excess_dpd` ignores direction (reversed group ordering → 0; EOD usually catches).
- Collapse gate ignores label distribution (≥98% one-class data would flag a perfect model).
- SAFETY S=6 whenever fnr_ratio ≤ 1.5 regardless of magnitude.
- Multi-label sigmoid uses `math.exp`; logits below about −709 overflow (not an InferenceError).
- Frontend has no input for `multilabel_target_index` (API only); multi-label models show the gate error in the UI.
