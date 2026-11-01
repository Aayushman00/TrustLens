# 01 — v1 baseline and known issues

Source of truth is `backend/app`, not the v1 docs (several were stale: e.g. the results matrix described an Adult-census fairness proxy that never ran the model, while `probes/fairness.py` now loads the HF model and uses the user's label mapping).

## What v1 actually implements

| Area | Implementation | Notes |
| ---- | -------------- | ----- |
| Pipeline | `tasks/evaluate_pipeline.py` (Celery) → `probes/runner.py` runs F→R→I→E→S, persists `probe_results`, then `confidence/engine.py` refines confidence | `services/evaluation_service.py` and `evaluation_service_v2.py` coexist |
| Fairness | `probes/fairness.py`: runs the model on a user CSV, equal-opportunity gap with bootstrap CI (`F-FAIR-EOPP`, `tl-fairness-binary-v1.2`); multiclass path in `fairness_multiclass.py`; gates for thin groups and wide CI | Needs a sensitive-attribute column. No counterfactual or intersectional analysis |
| Robustness | `probes/robustness*.py`: clean vs char-swap accuracy, paired-bootstrap drop CI, gates (`G-ROB-CI-WIDE`, `G-ROB-CLEAN-FLOOR`) | One perturbation family only |
| Integrity | `probes/integrity*.py`: Hub identity/revision/licence metadata checks; sha256 of weight files vs Hub LFS hashes (ADR 0013) | Covers hash match, not malicious content (e.g. pickle payloads) |
| Explainability | `probes/explainability*.py`: model-card section coverage + contradiction flags | Measures documentation, not explanations |
| Safety | `probes/safety*.py`: card disclosure checklist, high-impact-claim phrases, and (with a SAFETY contract) severe-harm false-negative rate with Wilson CI | Behavioural part is the only real measurement |
| Confidence | `confidence/engine.py`: three hand-set factors per dimension, geometric mean, floor 0.1 | Constants (0.45, 0.55, 0.35, n≥200→1.0…) are uncalibrated; self-labelled `proposed_calibration` |
| O/S/D | `osd/deterministic.py` always abstains; `osd/agent.py` heuristic bands; `osd/hybrid.py` LLM re-scores I/E/S via Gemini→Groq→NVIDIA | Heuristic and LLM outputs are unvalidated proposals |
| Scoring | `scoring/fries.py`: Π = cbrt(O·S·D), veto at 0, mean per aspect, weighted sum (weights ≥ 0.1) | Needs five complete human-finalised O/S/D sets; otherwise withheld |
| Evidence | `storage/evidence_store.py`: append-only sha256 filesystem store | Keep |
| Reports | `reports/builder.py`, versioned JSON + PDF | Keep, extend |
| Frontend | React/Vite: draft → run → review → report | Keep, extend |

## Suspected issues (to verify — none confirmed yet)

Each item gets a failing test or is closed as "not a bug" in M0.

| ID | Suspicion | Where | How to verify |
| -- | --------- | ----- | ------------- |
| K1 | Two evaluation services (`evaluation_service`, `_v2`) can drift; behaviour depends on which a router calls | `services/`, `routers/v1` | Trace callers; add a contract test hitting both paths |
| K2 | Confidence is not monotone in sample size at boundaries (data_quality steps at n=16/100/200) and ignores CI width except via gates | `confidence/engine.py` | Property test: more data never lowers confidence |
| K3 | `D` hard-coded to 8 for "directly measurable" dimensions inflates Π and makes dimension scores insensitive to detectability | `osd/agent.py` | Sensitivity analysis on flawed-suite results |
| K4 | LLM-assisted O/S/D is non-deterministic across providers and unvalidated; `llm_client.py` has uncommitted local edits | `osd/hybrid.py`, `osd/llm_client.py` | **Decision taken:** LLMs leave scoring and reports. Review the pending diff, keep anything useful for the archive, then remove the module, provider keys and settings (M0) |
| K5 | Veto rule maps any 0 to Π=0 but heuristics never propose 0, so a vetoed risk can only come from a human | `scoring/fries.py`, `osd/agent.py` | **Decision taken:** ADR 0014. Tier A integrity findings force `REJECT` and are non-overridable; vetoes come from evidence |
| K6 | Explainability and the Safety card part can be gamed by pasting headings into a model card (rule-based matcher, `MIN_BODY_CHARS`) | `probes/explainability_card.py`, `safety_card.py` | Adversarial-card test set |
| K7 | Fairness is only defined when the user supplies a sensitive column; label mapping errors silently change the positive class | `probes/fairness.py`, `datasets/user_dataset.py` | Test with swapped mapping; require explicit positive-class confirmation |
| K8 | Single-seed runs: repeatability verified (σ=0) but only because the pipeline is deterministic given the seed; sensitivity to the *sample draw* is not reported per probe | probes | Report seed-to-seed variance of the estimate itself |
| K9 | Docs and README drifted from code (fixed for docs layout in v2 cleanup) | repo | CI check that README claims map to code paths (spec 06) |
| K10 | Repo hygiene: large untracked artefacts (zips, `.7z`, backups, UI mock-ups) lived at the root | repo | Done: moved to `archive/v1/legacy/` |
| K11 | EOD/F1 spread is max − min over groups, biased upward: truth 0, estimate 0.23, 0 % coverage at k = 4 (spike S3-C) | `probes/fairness_metrics.py:132` | Replace with signed gaps vs pooled (`fair.group_signed`); regression test at truth 0 |
| K12 | `bootstrap_gap_ci` drops replicates where `stat_fn` returns None, so the CI is conditional on every group surviving resampling | `probes/fairness_stats.py:209-213` | Test with a small group that vanishes in some replicates; report the drop count or retire the function for decisions |
| K13 | Percentile bootstrap used for small-n rates: 0.39 coverage at n = 10, p = 0.05 (S3-A) | `probes/fairness_stats.py`, rate probes | Coverage test; switch rates to Jeffreys/Wilson with counts |
| K14 | No pickle-content scan exists anywhere (only hash checks) | `probes/`, `inference/`, `adapters/` | Add the stdlib opcode scan (S7 seed); Tier A on denylist hits only (ADR 0014) |

## Bug-hunt protocol (M0)

1. Run the full backend/worker/frontend test suites on a clean checkout; record failures and flakes (3 runs).
2. For each K-item: write the failing test first, then fix, then keep the test.
3. Run `/code-review` and a security pass over `routers/`, `datasets/url_fetch.py` (SSRF/redirect handling), `adapters/hf_hub.py` (token handling), evidence store paths (traversal).
4. Mutation spot-check the pure functions in `fairness_stats`, `robustness_stats`, `safety_behavior` (hand-written mutants must be caught).
5. Output: `docs/v2/bug-ledger.md` with ID, severity, status, test name.

Exit: zero known S1/S2 bugs, every K-item closed or documented, suite green three times in a row.
