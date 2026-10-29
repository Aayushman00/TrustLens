# TrustLens engineering notes

Companion to the thesis in `report/`. It holds implementation detail that was moved out of the
report (Chapter 3 and the former Chapter 5, "Implementation") so that the thesis stays a research
document. Experiment commands, result-folder maps and method-version history are in
`docs/REPRODUCING_THESIS_RESULTS.md`; setup is in `README.md` and `docs/TRUSTLENS_LOCAL_DEVELOPMENT.md`.

## 1. Component status and source files

Checked against the source at the time of the thesis (2026-10-25).

| Component | Status | Source / notes |
|---|---|---|
| Model import (metadata only) | Implemented | `adapters/hf_hub.py`: card, tags, licence, file list, no weights; revision fixed at draft time |
| Local inference backend | Implemented | `inference/local_hf.py`: batched `transformers`, CUDA or CPU, softmax over logits |
| Fairness probe | Implemented | `probes/fairness.py`; binary path `tl-fairness-binary-v1.2`, multiclass path `tl-methodology-v1.0` (worst-group accuracy gap, `F-FAIR-PERF`; not used in any experiment) |
| Robustness probe | Implemented, narrow | `probes/robustness_nlp.py`: random character swaps, text classifiers only; `max_changes` default 3 from attack budget 0.03; other modalities skip |
| Safety probe | Implemented | Card checklist `safety_card.py` (`tl-safety-v1.1`) and behavioural severe-miss `safety_behavior.py` (`tl-safety-v1.2`); needs a labelled set with a `severe` marker |
| Integrity probe | Implemented | Metadata checks plus artifact-set hashing, `integrity_artifact.py`, `tl-integrity-v1.2` (ADR 0013) |
| Explainability probe | Implemented, card only | `explainability_card.py`, `explainability_eval.py` (`tl-explainability-v1.1`); not SHAP or LIME |
| O/S/D engines | Implemented | `osd/deterministic.py` (never proposes), `osd/agent.py` (heuristic, v3 and v4 mapping), `osd/hybrid.py` (LLM-assisted), `osd/review.py` (human review merge) |
| FRIES scorer | Implemented | `scoring/fries.py`; test vectors in `shared/scoring/fixtures` |
| Reports (JSON, PDF) | Implemented | `reports/builder.py`, `render.py`; PDF via WeasyPrint |
| Evidence store | Implemented | Files named by SHA-256 on a local volume |
| Resource checker, benchmark-first runtime estimate | Not implemented | README gap 6 |
| Built-in unsafe-prompt suite | Not implemented | Safety behaviour needs user-supplied labelled data (README gap 9) |
| SHAP / LIME, attack simulation | Not implemented | Planned extensions |

## 2. Technology stack

Python >= 3.11, FastAPI, Pydantic v2 (REST under `/v1`; Pydantic models define the evaluation
contract, probe output and report schemas); SQLAlchemy 2, Alembic, PostgreSQL (16 migration files);
Celery + Redis (asynchronous pipeline); `transformers` + PyTorch (local inference),
`huggingface_hub` (metadata, LFS hashes); `httpx` (LLM providers), Jinja2 + WeasyPrint (reports);
React 19, Vite, TypeScript (dashboard); pytest, Vitest, ruff (GitHub Actions); Docker Compose
(postgres, redis, api, worker, frontend; CPU-only, GPU and experiment compose files).
Reference machine: laptop with an NVIDIA RTX 4060 (8 GB VRAM); experiment logs confirm CUDA.

## 3. Evaluation contract and statuses

* **Contract** (`schemas/evaluation_contract_v2.py`): dataset stored under a hash-derived name, text
  and target columns, sensitive-attribute column, `label_mapping`, `min_group_n`,
  `positive_label_index`, a snapshot of the model's `id2label` and the resolved revision. It made
  the pilot's label-mapping mistake visible after the fact.
* **Workflow mode:** `AI_AUTONOMOUS` finalises without a reviewer (`human_reviewed=false`);
  `AI_ASSISTED` stops at `AWAITING_REVIEW`. Despite the names, no LLM is involved in the mode.
* **Assessment engine:** `deterministic` (default; no proposals, FRIES withheld unless a human
  supplies O/S/D), `legacy_heuristic`, `llm_v1` (heuristic proposal, then an LLM re-rates
  Integrity, Explainability and Safety-card; Fairness, Robustness and behavioural Safety keep the
  heuristic rating and the LLM judgment is stored as metadata). Experiments use `llm_v1` in
  `AI_AUTONOMOUS` mode unless stated.
* **Probe statuses:** `EVALUATED`, `PROXY`, `SKIPPED`, `NOT_APPLICABLE`, `INSUFFICIENT_EVIDENCE`,
  `FAILED`. **`aspect_scoring`:** `risk_detected`, `no_material_risk`, `disparity_observed`,
  `disclosure_gap`, `mapping_blocked`, `not_scored`. A rating is withheld (`None`) when either says
  the evidence is insufficient; the report builder withholds FRIES when any dimension lacks a
  complete triple; the API answers such a report request with HTTP 409.
* **Integrity statuses (ADR 0013):** VERIFIED, MISMATCH (`I-INT-BYTES-DIVERGE`), INCOMPLETE
  (`G-INT-ARTIFACT-INCOMPLETE`, rating withheld), UNPINNED, UNSUPPORTED. The gaps
  `I-INT-REV-UNPINNED` and `I-INT-MANIFEST-MISSING` are separate findings about how a Hub model is
  identified.
* **Gate identifiers:** `G-FAIR-N-GROUP`, `G-FAIR-POSITIVES`, `G-FAIR-CI-MISSING`,
  `G-FAIR-CI-WIDE`, `G-ROB-PERT-COVERAGE`, `G-ROB-CI-WIDE`.
* **Disclosure-gap identifiers:** `S-GOV-DISCLOSURE-GAP`, `E-DOC-INCOMPLETE`,
  `I-INT-REV-UNPINNED`, `I-INT-MANIFEST-MISSING`, `I-INT-LICENSE-UNDISCLOSED`.
  Risks: `F-FAIR-EOPP`, `R-ROB-PERT`, `S-BEH-SEVERE-MISS`, `I-INT-BYTES-DIVERGE`,
  `I-INT-LISTING-DRIFT`, `E-DOC-CONTRADICTION`.
* **Constant-predictor gate:** `prediction_gate.py`, collapse at >= 98% of predictions in one class.
* **LLM engine:** three providers tried in order, temperature 0.2; first valid answer used; backup
  rating tagged `heuristic_fallback`; per aspect `llm_fallback_reason`, `llm_attempts`,
  `llm_prompt_version` are stored. Prompt `osd-llm-v3-decision-first-2026-10-03` caps card text at
  5 000 and evidence at 3 000 characters and puts the decision fields on an untruncated first line.

## 4. Engineering issues found while running experiments

Each got a regression test; none changed a score formula.

| Issue | Effect | Fix |
|---|---|---|
| `str(engine.url)` masks the password, so the API built a new connection pool per request | Postgres "too many clients"; runs failed | Compare the raw URL; dispose the old engine |
| FastAPI 0.121+ commits yield-dependencies after the response is sent | Client saw "not validated" right after a 200 | `Depends(get_db, scope="function")` |
| Celery task enqueued before the API committed | Evaluation stuck in `PENDING` | Commit before enqueue at all call sites; worker retry as backstop |
| LLM prompt about 7.3k tokens for long cards; reason for backup ratings only in logs | Well-documented models never LLM-assessed; backup ratings untraceable (11 of 45 suite runs) | Compact prompt v2; reason, attempts, prompt version stored per aspect |
| Post-start transient error silently retried | Evaluation left in `RUNNING` forever | Re-raise as `PipelineInterruptedError`; failure handler also rescues `PROBES_COMPLETED` and `AGENT_COMPLETED` |
| Decision fields emitted last by probes, cut by the evidence cap | LLM could not see risks or gaps | `decision:` line first and never truncated (prompt v3) |

## 5. Reproducibility features in the data model

* Probe output saved as JSON named by its SHA-256; evaluations stamped with an immutable
  `methodology_version`; model revision fixed at draft time and checked by `model_snapshot_check.py`;
  explicit probe seeds; Civil Comments pinned to revision `f2970eb3...` in
  `prepare_flawed_suite_data.py` (recorded only from 2026-10-03).
* Probe outputs that violate the contract raise `ProbeError` and fail the evaluation.

## 6. Tests and CI

* 111 backend test modules (913 collected `pytest` items; 843 `def test_` functions by a plain text
  count; parametrisation accounts for the difference), 9 worker tests, 29 frontend test files.
* CI (`.github/workflows/ci.yml`) on pushes to `Main` and on pull requests: backend `ruff` and
  `pytest` against a Postgres service container, worker `ruff` and `pytest` (slim install),
  frontend tests, type-check and build. No coverage report was generated.
* Latest full run (2026-10-23, branch `docs/report-final`): backend 911 passed, 2 skipped (WeasyPrint
  system libraries; live Hub import, `TRUSTLENS_LIVE_TESTS=1`), 1 warning, 266 s (other runs 130-326 s);
  worker 9 passed; frontend 29 files / 275 tests passed; `ruff` (rules E4, E7, E9, F) no findings
  (31 at the start of round 3).
* Re-check 2026-10-30 (branch `feat/ui-shell`, no Postgres available, so the 220 DB-backed tests
  skipped): backend 692 passed, 220 skipped (after fixing five `test_report_claims.py` assertions
  that pinned pre-restructure report prose); worker 9 passed; frontend 34 files / 340 tests passed
  (UI work added after the 2026-10-23 run); `ruff` clean for backend and worker. The 911 figure above
  is the full run with Postgres and was not reproduced.
* Tests found real mistakes before experiments: the leakage test caught model names in packet source
  paths; a unit test caught a risk-present rule that returned UNCERTAIN for a triggered integrity
  risk whenever an unrelated rule had also failed. Most probe tests use injected fake backends.

## 7. Cost measurements (reference laptop, RTX 4060, float32, batch 8)

Fine-tuning one BERT-base variant (8 000 rows, 3 epochs) 160.4-178.3 s; one full API evaluation of a
Hub model (3 000 rows, five probes) 23.2-110.5 s over the seven v9 audit runs; one deterministic
packet interpretation about 2 ms; one successful LLM call mean 19.8 s including back-off; BERT-base
float32 checkpoint about 438 MB. Peak memory was not recorded.

## 8. Dashboard

Import a model, create a draft, attach a dataset with label mapping and sensitive column, confirm,
read the report. Screenshots kept in `report/figures/` (`ui_results_profile.png`, `ui_review.jpg`,
`ui_report.jpg`): the review page of an `AI_ASSISTED` evaluation (deterministic engine proposes no
values, evidence read-only) and the report page of a documentation-only evaluation of
`gravitee-io/bert-tiny-toxicity` (FRIES withheld, banner states the result is not human-reviewed).

## 9. Plain-language wording in the thesis ↔ internal identifiers

The thesis uses descriptions instead of code names. Mapping (see also section 3):

| Thesis wording | Identifier in code / results |
|---|---|
| fairness-gap risk / "the TPR gap flagged a disparity" | `F-FAIR-EOPP` |
| robustness risk (drop at least 0.05) | `R-ROB-PERT` |
| exploratory severe-miss rule | `S-BEH-SEVERE-MISS` |
| byte mismatch in the file-set comparison | `I-INT-BYTES-DIVERGE` |
| documentation-contradiction risk | `E-DOC-CONTRADICTION` |
| rating withheld for insufficient evidence | status `INSUFFICIENT_EVIDENCE`; aspect scoring `mapping_blocked` |
| human-review mode / automatic mode | `AI_ASSISTED` / `AI_AUTONOMOUS` |
| rule-based fallback rating | O/S/D source `heuristic_fallback` |
| LLM-assisted engine | `llm_v1` |
| risk list / disclosure-gap list | `risks_triggered` / `disclosure_gaps` |
| original scoring bands / range-scaled mapping / evidence guards | v3 / v4 / v9 (methodology versions) |
| robustness sensitivity analysis | deviation A2 (`defect_severity_20261003_a2`) |
| exploratory severe-miss replay | v10 (`safety_severe_miss_replay_20261022`) |
| fairness group flag / severe subset | dataset columns `identity_ref` (identity-attack score > 0.0001) and `severe_toxicity` (> 0.0001) |
| hypotheses H1-H4 of the fairness confirmation | no flagged control; flips >= 0.4 flagged; Spearman rho > 0; width-rule behaviour |

The per-dimension and aggregate FRIES scores of the seven Hub models, which the thesis does not
tabulate because the Integrity and Explainability ratings come from different rating sources, are in
`results/external_hub_validation_20261003_v9r/profiles.json` and `PROFILES.md`.

## 10. Integrity finding detail (moved from thesis Section 6.7)

`textdetox/xlmr-large-toxicity-classifier` and `textdetox/xlmr-base-toxicity-classifier` ship
byte-identical weights; both have hidden size 768 and 12 layers, i.e. base-size architecture.

## 11. API endpoints (all under `/v1`; the service publishes the full OpenAPI description)

| Endpoint | Purpose |
|---|---|
| `POST /models`, `GET /models`, `GET /models/{id}` | Manual model registry |
| `POST /models/import-hf` | Resolve a repo id or URL through the Hub metadata API (card, file list, revision, no weights); upsert the registry; 403 for gated models without a token, 404 unknown repo, 502 Hub unavailable |
| `GET/POST/DELETE /models/{id}/documentation` | Documentation sources of a model |
| `POST /dataset-fetches`, `POST /dataset-uploads`, `GET /dataset-contents/{id}` | Dataset intake; content stored under its hash |
| `POST /evaluation-drafts`, `GET /evaluation-drafts/{id}` | Create and read a draft; the model revision is fixed here |
| `PUT /evaluation-drafts/{id}/{dimension}` | Set and validate dataset, columns, label mapping, favourable label, group and severe columns for one dimension |
| `POST /evaluation-drafts/{id}/{dimension}/confirm` | Freeze one dimension |
| `GET /evaluation-drafts/{id}/{dimension}/target-values` | Distinct target values for label mapping |
| `POST /evaluations-v2` | Consume a fully confirmed draft into a frozen `EvaluationContractV2`, commit, then enqueue (`POST /evaluations` is deprecated) |
| `GET /evaluations`, `GET /evaluations/{id}` | List and read evaluations |
| `GET /evaluations/{id}/events` | Event log (`evaluation_created`, `evaluation_started`, `probes_completed`, `agent_completed`, `awaiting_review`, `evaluation_finalized`, `evaluation_failed` with reason code, `evaluation_requeued`) |
| `POST /evaluations/{id}/reconcile-enqueue` | Operator retry of a confirmed enqueue failure; 409 unless the evaluation is PENDING with `enqueued=false` |
| `POST /evaluations/{id}/human-review` | Submit overrides (AI_ASSISTED only; 409 `ASSISTED_ONLY` otherwise); the latest review is used |
| `POST /evaluations/{id}/finalize` | Idempotent; 409 `NOT_READY` while running, `FAILED_EVALUATION` after failure, `REVIEW_REQUIRED` in AI_ASSISTED mode until a review exists |
| `POST /evaluations/{id}/publish`, `.../unpublish` | Publication flag |
| `GET /reports/{id}`, `POST /reports/{id}/generate` | Versioned JSON and PDF report; 409 `NOT_FINALIZED` until finalised |

## 12. Data model details (tables in `backend/app/db/models.py`)

`models` (hf_repo_id, revision, checksum, card metadata); `dataset_content` (content_hash, storage_uri,
row_count, columns); `dataset_fetch_event`; `evaluation_draft` and `draft_dimension_config` (per dimension:
dataset, text/target/sensitive columns, label_mapping, min_group_n, positive_label_index, severe_column,
multilabel_target_index); `documentation_sources` (documentation revision, content hash, retrieval status);
`evaluations` (model_id, status, evaluation_mode, probe_config holding the contract, model_revision,
methodology_version, execution_metadata, publication flags); `evaluation_events`; `probe_results`
(dimension, metric_values, confidence, evidence_refs with uri and sha256); `osd_agent_outputs`
(ai_suggestion, evidence_used, rationale); `human_reviews` (overrides, human_changed, notes);
`final_scores` (fries_score, dimension_scores, finalized_osd, evaluation_mode); `reports` (json_uri,
pdf_uri, version); `attack_flags` (not used in any experiment).

## 13. Task execution and failure handling (`tasks/evaluate_pipeline.py`, `worker/app/tasks/evaluate.py`)

* States: PENDING, RUNNING, PROBES_COMPLETED, AGENT_COMPLETED, AWAITING_REVIEW, FINALIZED, FAILED. Every
  transition is `transition_status(expected, new)`, an atomic compare-and-set that returns nothing when the
  evaluation is not in the expected state (duplicate delivery and late failure signals are no-ops).
* `ProbeError` or `EvidenceStoreError`, a missing evidence store, an assessment-engine exception and a
  scoring exception move the evaluation to FAILED with a reason code and do not raise (no Celery retry).
* The Celery task retries `ConnectionError` and `TimeoutError` with back-off, up to three times
  (`autoretry_for`, `max_retries=3`), but only before the pipeline has started: a transient error after
  start is re-raised as `PipelineInterruptedError`, outside `autoretry_for`, because a retry would find the
  evaluation no longer PENDING and report success. `Task.on_failure` then moves any evaluation left in
  RUNNING, PROBES_COMPLETED or AGENT_COMPLETED to FAILED with the same compare-and-set.
* AI_AUTONOMOUS finalises in the worker: with fewer than five complete O/S/D triples the evaluation is
  FINALIZED without a final score (`scoring_withheld: true`); AI_ASSISTED stops at AWAITING_REVIEW.
