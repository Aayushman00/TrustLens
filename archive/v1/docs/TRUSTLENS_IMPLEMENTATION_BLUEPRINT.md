# TrustLens Implementation Blueprint

**Document type:** Repository audit + implementation blueprint  
**Audience:** Developers implementing the correction plan without rediscovering the codebase  
**Scope:** Backend, frontend, probes, scoring/O-S/D, inference, schemas, DB, evidence, reports, configs, tests, experiments  
**Rule:** Do not treat this document as implemented code. It describes **current behavior**, **gaps**, **targets**, **concrete change locations**, **dependencies**, **tests**, and **risks**.

**Repository snapshot (audit date):** TrustLens MVP on original FRIES math; partial “Phase 1” status/abstain work already landed in code but README roadmap still marks Phase 1 as absent. Frozen experiment artifacts under `results/` from TrustLens **0.20.1** must not be silently rewritten.

---

## Table of contents

1. [How to read this document](#1-how-to-read-this-document)
2. [Executive summary](#2-executive-summary)
3. [Architecture map (current vs target)](#3-architecture-map-current-vs-target)
4. [Cross-cutting systems](#4-cross-cutting-systems)
   - [4.1 FRIES aggregation](#41-fries-aggregation)
   - [4.2 O/S/D mapping and HeuristicOSDAgent](#42-osd-mapping-and-heuristicosdagagent)
   - [4.3 Evidence, probe status, and scoring withhold](#43-evidence-probe-status-and-scoring-withhold)
   - [4.4 Model inference and resource checking](#44-model-inference-and-resource-checking)
   - [4.5 Human review (Assisted mode)](#45-human-review-assisted-mode)
   - [4.6 Reports and frontend UI](#46-reports-and-frontend-ui)
   - [4.7 Confidence engine](#47-confidence-engine)
   - [4.8 Database, API, and pipeline lifecycle](#48-database-api-and-pipeline-lifecycle)
5. [Dimension: Fairness](#5-dimension-fairness)
6. [Dimension: Robustness](#6-dimension-robustness)
7. [Dimension: Integrity](#7-dimension-integrity)
8. [Dimension: Explainability](#8-dimension-explainability)
9. [Dimension: Safety](#9-dimension-safety)
10. [Implementation phases and dependency graph](#10-implementation-phases-and-dependency-graph)
11. [Test matrix](#11-test-matrix)
12. [Backward compatibility and historical experiments](#12-backward-compatibility-and-historical-experiments)
13. [Open decisions register](#13-open-decisions-register)
14. [Quick start (for developers)](#14-quick-start-for-developers)

---

## 1. How to read this document

Each substantive finding uses five labels:

| Label | Meaning |
| ----- | ------- |
| **CURRENT** | What the repository actually does today (verified in code or committed artifacts). |
| **PROBLEM** | Shortcoming, incorrect behavior, methodological weakness, or misleading product surface. |
| **TARGET** | Intended behavior per README vision, backend contracts, and the redesign specification discussed in project history (risk catalog, status-aware scoring, model-faithful probes where applicable). |
| **CHANGE** | Exact files, classes, functions, schemas, configs to modify or add. |
| **TEST** | How to verify the change; references existing or new test modules. |

**Ambiguity:** Items marked **DECISION NEEDED** are not fully specified in the repo; pick a policy before coding.

**Do not invent:** Targets are tied to README “Target architecture”, probe module docstrings, `SCORING.md`, experiment write-ups, and enums already present (`ProbeEvaluationStatus.PROXY`). Features with no spec anchor (e.g. full attack-simulation Phases 20–21, FRIES2) are listed as **out of scope** unless explicitly scheduled.

---

## 2. Executive summary

### 2.1 What TrustLens is supposed to do

TrustLens is a **local-first evidence-driven audit platform** for ML models imported from Hugging Face. It:

1. Collects **measured evidence** per FRIES dimension (Fairness, Robustness, Integrity, Explainability, Safety).
2. Maps evidence to **named risks** and proposes inverted **O/S/D** ratings (0–10, higher = more trustworthy).
3. Aggregates risk scores `Pi = ∛(O×S×D)` into aspect scores and a weighted overall **original FRIES** score.
4. Supports **AI_AUTONOMOUS** (pipeline-finalized) and **AI_ASSISTED** (human review) modes with loud **PROPOSED** methodology labeling.
5. Produces versioned JSON/PDF reports and an opt-in leaderboard.

The FRIES number is an **audit artifact**, not proof of safety or fairness.

### 2.2 What the repository actually does today

| Area | Maturity |
| ---- | -------- |
| Auth, model metadata import, async pipeline, evidence store | **Working** |
| Five probes F→R→I→E→S | **Working** (heterogeneous depth) |
| Original FRIES math | **Frozen + tested** (`shared/scoring/fixtures/`) |
| Heuristic O/S/D agent | **Working** (one triple per aspect, PROPOSED bands) |
| Probe evaluation statuses | **Partial** (enum + F/R paths; E/I/S incomplete) |
| Abstain / withhold FRIES | **Partial** (F/R abstain; autonomous withholds if any aspect incomplete; E/S still band) |
| Model-faithful fairness | **Absent** (Adult + sklearn LR proxy) |
| Shared inference backend | **Absent** (robustness NLP only) |
| Risk catalog (1–3 risks/aspect) | **Absent** |
| Mapping traces (`rule_id`, methodology version) | **Absent** |
| Resource checker / benchmark estimate | **Absent** |
| Behavioral safety suite | **Absent** |
| Reports/UI limitation completeness | **Partial** |

### 2.3 Highest-impact problems (ordered)

1. **Fairness never evaluates the imported HF model** — identical across models at fixed seed; `PROXY` enum unused.
2. **Coverage → O/S/D collapse** — empty or header-less cards yield `(2,2,3)` or `scale(0)=1` → uniform low triples; Mode B experiments showed O=S=D=1 on thin cards despite substantive card text in `card_data`.
3. **One O/S/D per dimension** — not FRIES paper’s 1–3 risks per aspect with structured traces.
4. **Assisted `accept_all` breaks on abstained agent triples** — `merge_review_aspects` → `_triple` requires `int(O/S/D)`; null agent values raise `ValueError`.
5. **README roadmap stale** — claims Phase 1 absent while code has partial Phase 1.
6. **No partial FRIES reweighting** — withhold is binary (all five complete or no `final_scores`); no documented reweight-over-evaluated-aspects policy.
7. **Integrity/safety/explainability not status-aware** — always implicit `EVALUATED`; integrity emits `integrity_score_0_10` easy to confuse with aspect score.

### 2.4 Recommended implementation order (summary)

See [Section 10](#10-implementation-phases-and-dependency-graph). Broadly: finish status/abstain consistency → inference + resource gate → model-faithful fairness (with explicit PROXY legacy) → risk catalog + mapping traces → partial FRIES policy → reports/UI → integrity/safety behavioral extensions.

---

## 3. Architecture map (current vs target)

### 3.1 Current pipeline (as implemented)

```text
POST /v1/models/import-hf          → Hub metadata only (no weight download)
POST /v1/evaluations               → Celery enqueue → evaluate_pipeline
  PENDING → RUNNING
    run_all_probes (F→R→I→E→S)     → probe_results + MinIO evidence JSON
    PROBES_COMPLETED
    HeuristicOSDAgent.propose      → osd_agent_outputs (ai_suggestion)
    AGENT_COMPLETED
  AI_ASSISTED → AWAITING_REVIEW    → (human) POST human-review + finalize
  AI_AUTONOMOUS → if 5 complete O/S/D → final_scores + FINALIZED
                  else FINALIZED without final_scores (scoring withheld)
```

Key files:

| Stage | Primary files |
| ----- | ------------- |
| Enqueue | `backend/app/tasks/celery_client.py`, `worker/` consumer |
| Pipeline | `backend/app/tasks/evaluate_pipeline.py` |
| Probes | `backend/app/probes/runner.py`, `registry.py`, `*/fairness.py` etc. |
| OSD | `backend/app/osd/agent.py`, `serialize.py`, `review.py` |
| Scoring | `backend/app/scoring/fries.py` |
| API | `backend/app/routers/v1/evaluations.py`, `evaluation_actions.py` |
| Reports | `backend/app/reports/builder.py`, `render.py`, `store.py` |

### 3.2 Target pipeline (from README / spec)

```text
import-hf metadata
     ↓
Model analyzer + Resource checker (disk/RAM/VRAM) → SUPPORTED | CONSTRAINED | UNSUPPORTED
     ↓
Benchmark (50–100 samples) → runtime estimate → user confirm
     ↓
InferenceBackend (local HF) → predictions for F/R/S behavioral probes
     ↓
Probes → evidence + ProbeEvaluationStatus per dimension
     ↓
Risk detection → select 1–3 FRIES risks per aspect → O/S/D per risk (+ mapping trace)
     ↓
Aspect mean → weighted FRIES (partial/reweight or withhold policy)
     ↓
Human review (Assisted) → finalized_osd
     ↓
Report with statuses, limitations, calculation breakdown
```

**DECISION NEEDED:** Whether benchmark confirmation is blocking for all probes or only weight-download paths.

---

## 4. Cross-cutting systems

### 4.1 FRIES aggregation

#### CURRENT

- **Pure math** in `backend/app/scoring/fries.py`:
  - `risk_pi(O,S,D)` — cube root product; veto if any component 0; optimal if all 10.
  - `aspect_score(risks)` — mean of risk `Pi` values; **empty risk list → 0.0**.
  - `fries_total(aspect_scores, weights)` — default equal weights 0.2; custom weights must sum to 1, each ≥ 0.1.
  - `score_from_finalized_osd(finalized_osd)` — MVP shape: one triple per aspect **or** `risks: [{O,S,D},...]` list per aspect.
- **Frozen oracle:** `shared/scoring/fixtures/fries_test_vectors.json`; documented in `backend/tests/SCORING.md`; asserted by `backend/tests/test_fries_scorer.py`.
- **Pipeline integration:** Autonomous path calls `score_from_finalized_osd` only when `to_finalized_osd` has `complete_aspect_count == 5` (`evaluate_pipeline.py` lines ~233–251).
- **Assisted path:** `_finalize_assisted` in `evaluation_service.py` scores human-approved triples (all five required via review merge).

#### PROBLEM

1. **Empty aspect → Ti = 0** drags totals if multi-risk partial aspects are introduced without policy (fixture id 9 documents this paper behavior).
2. **No partial FRIES** — if fairness abstains, overall score is withheld entirely rather than reweighted over evaluated aspects (README target mentions partial/reweight).
3. **No `methodology_version` on scorer output** — only `trustlens_version` on evaluation row; heuristic band version not tracked separately from math version.
4. **Reports always assume `final_scores` exists** — `build_report_json` raises if no row; withheld autonomous runs cannot generate canonical report_v1 today.

#### TARGET

- Scorer math remains **original FRIES** (FRIES2 explicitly out of scope per `SCORING.md`).
- **Partial policy (DECISION NEEDED):** either (a) withhold overall T until all aspects complete, (b) reweight over aspects with `status=EVALUATED` and document excluded dimensions, or (c) produce `T_partial` plus `T_full` placeholder.
- Support **multi-risk** `risks[]` per aspect in finalized_osd (parser already exists).
- Persist **scoring metadata:** `scoring_complete`, `scoring_withheld`, `evaluated_aspect_count`, optional `weights`, `methodology_version_scorer` (e.g. `fries-original-v1`).

#### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/scoring/fries.py` | Add `score_partial_finalized_osd(...)` or extend `score_from_finalized_osd` with `allow_partial` + reweight helper; emit metadata dict alongside `FriesResult`. |
| `backend/app/osd/serialize.py` | Ensure `to_finalized_osd` / assisted builder set `scoring_complete`, `evaluated_aspects`, `withheld_reason`. |
| `backend/app/tasks/evaluate_pipeline.py` | Branch on partial policy; optionally upsert `final_scores` with `fries_score=null` and dimension_scores partial map. |
| `backend/app/services/evaluation_service.py` | `_finalize_assisted` — same partial rules as autonomous. |
| `backend/app/schemas/evaluations.py` | `FinalScoreRead` optional `fries_score`; add `scoring_withheld` on detail. |
| `backend/app/db/models.py` | **DECISION:** nullable `fries_score` on `final_scores` or separate `scoring_status` column. |
| `backend/app/reports/builder.py` | Report path for withheld/partial scores (executive summary bullets). |
| `shared/scoring/README.md` | Document partial policy once chosen. |

#### TEST

| Test | Location |
| ---- | -------- |
| Existing oracle vectors | `backend/tests/test_fries_scorer.py` — must remain green |
| Partial reweight | New cases in `test_fries_scorer.py` or JSON fixtures |
| Pipeline withhold / partial | Extend `backend/tests/test_evaluate_pipeline_evidence.py` |
| Lifecycle report on withheld eval | `backend/tests/test_lifecycle.py` — currently may assume score present |

#### Dependencies

- Depends on [4.3](#43-evidence-probe-status-and-scoring-withhold) status consistency.
- Multi-risk aspects depend on [4.2](#42-osd-mapping-and-heuristicosdagagent) risk catalog.

#### Risks

- Changing partial policy **invalidates comparability** with `results/mode_c_*.csv` unless runs are tagged `scoring_policy=v1_withhold`.
- Nullable `fries_score` breaks leaderboard queries — update `leaderboard` repository filters.

---

### 4.2 O/S/D mapping and HeuristicOSDAgent

#### CURRENT

- **Agent:** `backend/app/osd/agent.py` — `HeuristicOSDAgent.propose`.
- **Methodology label:** `METHODOLOGY_STATUS = PROPOSED_REQUIRES_VALIDATION` (`osd/base.py`).
- **Band rules (documented in agent module docstring):**
  - Proposals clamped to **[1, 9]** (never 0 veto or 10 optimal — reserved for humans).
  - **Fairness:** gap from DP/EOD → O=S=scale(1−gap); thin slices −1; D=7 or 8; missing metrics → `(None,None,None)` abstain.
  - **Robustness:** O,S,D from clean/robust/degradation; missing → abstain.
  - **Integrity:** pass_rate → O=S=scale(pass_rate), D=8; no checks → abstain.
  - **Explainability / Safety:** `coverage_ratio` → scale; **empty card (`card_chars==0`) → fixed `(2,2,3)`**; missing coverage → abstain; safety high-impact gaps lower S,D.
- **Status on aspects:** reads `probe_status` from metrics when complete; else `INSUFFICIENT_EVIDENCE`.
- **Serialization:** `backend/app/osd/serialize.py` — `to_ai_suggestion` includes per-aspect `status`, `scoring_withheld`, `complete_aspect_count`; `to_finalized_osd` **omits** incomplete aspects.

#### PROBLEM

1. **Not risk-based** — single triple per dimension; no `rule_id`, `risk_name`, or `risks[]` in agent output.
2. **E/S empty-card band `(2,2,3)`** is still a numeric score — contradicts “do not invent O/S/D when evidence is thin” for card-only dimensions (experiments: thin cards with `card_data` fields still got O=S=D=1 when `coverage_ratio=0` but `card_chars>0` because `scale(0)=0` → clamp to 1).
3. **Integrity D=8 always** when checks exist — not tied to FRIES integrity risk taxonomy.
4. **No `methodology_version`** on mapping rules (only free-text rationale).
5. **README still claims** agent always proposes numbers for skips — **partially fixed** for F/R but not E/S.

#### TARGET

- **Risk catalog:** 1–3 selected risks per aspect from a versioned catalog (YAML/JSON in `configs/` or `shared/fries_risks/`).
- **Mapping engine:** deterministic rules with `rule_id`, inputs, bands, output O/S/D per risk; store trace in `osd_agent_outputs` and finalized_osd.
- **Abstain policy:** `NOT_APPLICABLE`, `SKIPPED`, `FAILED`, `INSUFFICIENT_EVIDENCE`, `PROXY` → no numeric O/S/D unless human fills (Assisted).
- **Empty card:** `INSUFFICIENT_EVIDENCE` or explicit low-confidence disclosure — **DECISION NEEDED** vs fixed `(2,2,3)` band.
- Agent remains **PROPOSED**; humans may set 0 or 10.

#### CHANGE

| File | Change |
| ---- | ------ |
| `configs/fries_risks_v1.yaml` (new) | Risk definitions per dimension (id, name, description, evidence requirements). |
| `backend/app/osd/risk_catalog.py` (new) | Load catalog; validate evidence keys. |
| `backend/app/osd/mapping_rules.py` (new) | Rule functions + `rule_id` registry; version string `osd-mapping-v1`. |
| `backend/app/osd/agent.py` | Replace dimension-wide bands with risk-level mapping; remove or gate `_EMPTY_CARD_BAND`. |
| `backend/app/osd/base.py` | `AspectOSD` may need `risks: list[RiskOSD]` structure. |
| `backend/app/osd/serialize.py` | Serialize risks[], traces, `methodology_version`. |
| `backend/app/osd/review.py` | Merge/edit per risk or per aspect — **DECISION NEEDED**. |
| `frontend/src/pages/ReviewPage.tsx` | UI for multi-risk rows. |

#### TEST

| Test | Location |
| ---- | -------- |
| Agent bands / abstain | `backend/tests/test_osd_agent.py` — update for risk model |
| Serialization | same file `test_serialization_shapes` |
| Golden mapping traces | New `test_osd_mapping_rules.py` with fixture metrics → expected rule_ids |
| Review merge | New tests for null abstain + accept_all behavior |

#### Dependencies

- Fairness/Robustness probe metric keys must stabilize before locking rules.
- Frontend/API schemas must expose nullable O/S/D and statuses first ([4.3](#43-evidence-probe-status-and-scoring-withhold)).

---

### 4.3 Evidence, probe status, and scoring withhold

#### CURRENT

- **Enum:** `ProbeEvaluationStatus` in `backend/app/db/enums.py` — `EVALUATED`, `INSUFFICIENT_EVIDENCE`, `NOT_APPLICABLE`, `SKIPPED`, `FAILED`, `PROXY`.
- **ProbeOutput:** `backend/app/probes/base.py` — `status`, `status_reason` on dataclass; runner copies to `metric_values.probe_status` / `probe_status_reason` (`runner.py` ~103–106).
- **Fairness / Robustness:** set status on all exit paths (`fairness.py`, `robustness.py`).
- **Integrity / Explainability / Safety:** do **not** set `ProbeOutput.status`; rely on default `EVALUATED`; no `probe_status` in metrics unless runner adds only from `output.status` (always EVALUATED).
- **Evidence store:** `backend/app/storage/evidence_store.py` — SHA-256, MinIO, evaluation-scoped keys; probes must emit `evidence_refs` (runner validates non-empty).
- **Withhold:** Autonomous pipeline skips `FinalScoreRepository.upsert` when `complete_n < 5`; evaluation still `FINALIZED` (`evaluate_pipeline.py`).
- **AI suggestion JSON:** `scoring_withheld`, `scoring_complete`, per-aspect `status` in `to_ai_suggestion`.

#### PROBLEM

1. **Inconsistent status coverage** — I/E/S always appear `EVALUATED` even when evidence is purely “card empty”.
2. **`PROXY` never emitted** — fairness uses LR proxy with `status=EVALUATED`.
3. **Flags vs status** — skip paths add string flags (`metrics_skipped`, `attack_skipped`) but status semantics not unified in UI/reports.
4. **DB has no dedicated `probe_status` column** — only inside `metric_values` JSONB.
5. **Report builder** does not surface `probe_status` or `scoring_withheld`.

#### TARGET

- Every probe returns explicit `ProbeOutput.status` aligned with flags.
- Fairness on proxy predictor → `PROXY` with `status_reason` naming substitute model.
- Product surfaces (API, UI, report) show status per dimension and overall scoring completeness.
- **DECISION:** promote `probe_status` to column vs keep in JSONB with schema validation.

#### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/probes/integrity.py` | Set status for empty card / failed evidence store paths. |
| `backend/app/probes/explainability.py` | `INSUFFICIENT_EVIDENCE` when `card_chars==0`; consider when `coverage_ratio==0`. |
| `backend/app/probes/safety.py` | Same as explainability. |
| `backend/app/probes/fairness.py` | On successful LR path: `PROXY` unless real model inference used. |
| `backend/app/probes/runner.py` | Optionally validate status/reason contract per dimension. |
| `backend/app/schemas/evaluations.py` | Expose `probe_status` on probe progress/detail reads. |
| `backend/app/reports/builder.py` | Include probe statuses in `ReportProbe` or executive bullets. |
| `frontend/src/pages/EvaluationDetailPage.tsx` | Show status column; banner when `scoring_withheld`. |
| `frontend/src/api/types.ts` | `O: number \| null`, `status` on aspect types; `scoring_withheld` on agent suggestion. |
| Alembic migration (optional) | `probe_results.probe_status` ENUM column. |

#### TEST

| Test | Location |
| ---- | -------- |
| Fairness N/A / FAILED | `backend/tests/test_fairness_probe.py` |
| Robustness N/A / FAILED | `backend/tests/test_robustness_probe.py` |
| Pipeline status + withhold | `backend/tests/test_evaluate_pipeline_evidence.py` |
| I/E/S status | Extend `test_integrity_probe.py`, `test_explainability_probe.py`, `test_safety_probe.py` |
| PROXY fairness | New test when proxy path labeled |

#### Dependencies

- OSD agent must read statuses ([4.2](#42-osd-mapping-and-heuristicosdagagent)).
- Partial FRIES policy ([4.1](#41-fries-aggregation)).

---

### 4.4 Model inference and resource checking

#### CURRENT

- **HF import:** metadata only — `adapters/` / import-hf route; no weight download.
- **Robustness inference:** `backend/app/probes/robustness_nlp.py` — lazy `transformers` + `torch` CPU; loads `AutoModelForSequenceClassification` at probe time; char-swap attack.
- **Fairness inference:** `predict_with_logistic_regression` in `fairness.py` — sklearn on tabular features, **not** HF model.
- **No** `InferenceBackend` interface, **no** resource checker, **no** benchmark throughput estimate, **no** VRAM/RAM gate.

#### PROBLEM

1. Robustness may download large weights **without** user confirmation or compatibility check.
2. Fairness metrics **do not reflect** imported model behavior.
3. Vision / LM / non-classification models skip robustness but other probes still run — no unified “model execution” story.
4. README lists this as core target architecture.

#### TARGET

- `InferenceBackend` protocol (e.g. `backend/app/inference/base.py`) with `LocalHFBackend` implementation.
- `ResourceChecker` / `ModelAnalyzer` — disk, RAM, VRAM estimates; states `SUPPORTED`, `CONSTRAINED`, `UNSUPPORTED`, `UNKNOWN`.
- Short benchmark (50–100 samples) → runtime estimate → optional user confirm before download.
- Fairness and robustness (and future safety behavioral) call backend uniformly.

#### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/inference/base.py` (new) | Protocol: `load`, `predict`, `predict_batch`, `device_info`. |
| `backend/app/inference/local_hf.py` (new) | Wrap transformers pipelines; share with robustness runner. |
| `backend/app/compatibility/resource_checker.py` (new) | Parameter count heuristics + psutil/GPUtil optional. |
| `backend/app/compatibility/model_analyzer.py` (new) | Hub metadata → task/modality/compatibility hints. |
| `backend/app/probes/robustness_nlp.py` | Delegate to `InferenceBackend`. |
| `backend/app/probes/fairness.py` | Use backend for model predictions on appropriate dataset — **DECISION:** tabular vs NLP fairness task mapping. |
| `backend/app/routers/v1/import-hf.py` or evaluations | Pre-flight compatibility endpoint. |
| `configs/compatibility_v1.yaml` (new) | Reference machine profile (README: RTX 4060 8GB VRAM, 16GB RAM). |

#### TEST

| Test | Location |
| ---- | -------- |
| Inference backend fakes | `backend/tests/fakes.py` — extend `FakeInferenceBackend` |
| Robustness with fake backend | `test_robustness_probe.py` |
| Resource checker unit | `test_resource_checker.py` (new) |
| Integration (optional) | `-m integration` with tiny model |

#### Dependencies

- Blocks model-faithful fairness ([Section 5](#5-dimension-fairness)).
- Should precede benchmark UX (**DECISION:** blocking vs advisory).

#### Risks

- Downloading weights in CI/tests — keep fakes default.
- Windows vs Linux GPU detection differences.

---

### 4.5 Human review (Assisted mode)

#### CURRENT

- **Flow:** Pipeline → `AWAITING_REVIEW` → `POST /v1/evaluations/{id}/human-review` → `POST /finalize`.
- **Merge logic:** `backend/app/osd/review.py` — `merge_review_aspects`, `build_overrides`, `to_finalized_osd_assisted`.
- **Rules:** All five aspects required in agent suggestion; `accept_all` takes agent triples via `_triple(int(...))`; edits override per aspect.
- **Finalize:** `evaluation_service._finalize_assisted` — scores approved triples, upserts `final_scores`, `human_reviewed=true`.
- **Frontend:** `frontend/src/pages/ReviewPage.tsx` — draft from agent; `acceptAll` default true; O/S/D typed as `number` not nullable.

#### PROBLEM

1. **`accept_all` with null agent O/S/D fails** — `int(None)` → `ValueError` → 400 on review/finalize.
2. Review UI initializes draft with null O/S/D as `Number(raw)||0` → **0** (veto!) if user toggles off accept-all.
3. **No guidance** for abstained dimensions — reviewer must know to supply triples manually.
4. **Assisted finalize always scores five aspects** — does not validate against withheld/partial policy.
5. **`to_finalized_osd_assisted` lacks** `scoring_withheld` metadata present in autonomous serializer.

#### TARGET

- Reviewer can **accept, edit, or supply** O/S/D for abstained aspects; cannot finalize with missing required dimensions unless policy allows partial finalize (**DECISION**).
- `accept_all` skips aspects where agent abstained (leave for human) or copies only complete triples.
- UI shows probe status and abstention rationale beside agent row.
- Finalized document records which aspects were human-supplied vs agent-accepted.

#### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/osd/review.py` | `_triple` optional; `merge_review_aspects` handle null agent values; `accept_all` semantics. |
| `backend/app/services/evaluation_service.py` | `submit_human_review`, `_finalize_assisted` validation. |
| `backend/app/schemas/reviews.py` | `AspectOSDEdit` optional fields or explicit `abstain` flag. |
| `frontend/src/pages/ReviewPage.tsx` | Null-safe display; disable accept-all when invalid; status column. |
| `frontend/src/api/types.ts` | Nullable O/S/D on `AspectOSD`. |

#### TEST

| Test | Location |
| ---- | -------- |
| Review merge abstain | New `backend/tests/test_osd_review.py` |
| Assisted lifecycle with skips | `backend/tests/test_lifecycle.py` |
| API human-review 400/409 | `backend/tests/test_evaluation_actions.py` (if exists) |

#### Dependencies

- [4.3](#43-evidence-probe-status-and-scoring-withhold) agent abstain consistency.
- [4.1](#41-fries-aggregation) partial finalize policy.

---

### 4.6 Reports and frontend UI

#### CURRENT

- **Reports:** `backend/app/reports/builder.py` builds `ReportV1` from DB; requires `final_scores` row; executive summary mentions mode, vetoed dims, probe flags; **no** `scoring_withheld`, probe status, or mapping traces.
- **Template:** `backend/app/reports/templates/report_v1.html` — score-centric layout.
- **API:** `GET /v1/reports/{evaluation_id}` — 409 if not finalized; does not distinguish “finalized without score”.
- **Frontend:**
  - `EvaluationDetailPage.tsx` — shows `final_score` card only if row exists; agent table shows raw O/S/D without status column; no withheld banner.
  - `ReportPage.tsx` — `ScoreBars` when dimension scores exist; JSON dump fallback.
  - `LeaderboardPage.tsx` — published evaluations with fries scores.
  - `ModeDisclosure.tsx` — methodology banner.

#### PROBLEM

1. **Withheld-score evaluations** cannot produce report_v1 (builder raises).
2. UI **misleading** when `FINALIZED` but no FRIES number — looks incomplete without explanation.
3. **No limitation sections** for proxy fairness, skipped robustness, card-only E/S.
4. Types assume numeric O/S/D everywhere.

#### TARGET

- Reports for all `FINALIZED` evaluations: full score, partial score, or explicit “score withheld” with reasons.
- UI sections: per-dimension status, evidence links, probe limitations, calculation breakdown (per-risk when catalog exists).
- Leaderboard excludes or marks withheld entries (**DECISION**).

#### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/reports/builder.py` | Branch without `final_scores`; add `LimitationsSection`, `ProbeStatusSection`. |
| `backend/app/schemas/reports.py` | New optional fields on `ReportV1`. |
| `backend/app/services/report_service.py` | Allow report generation for withheld finals. |
| `frontend/src/pages/EvaluationDetailPage.tsx` | Withheld banner; status in agent table. |
| `frontend/src/pages/ReportPage.tsx` | Partial/withheld display. |
| `frontend/src/components/ScoreBars.tsx` | Handle missing scores. |

#### TEST

| Test | Location |
| ---- | -------- |
| Report builder withheld | New `backend/tests/test_reports.py` cases |
| Lifecycle report | `test_lifecycle.py` |

---

### 4.7 Confidence engine

#### CURRENT

- `backend/app/confidence/engine.py` — per-dimension factors: `data_quality`, `probe_reliability`, `evidence_completeness`; geometric mean; `proposed_calibration: true`.
- Integrated in `runner.py` via `refine()` — persists `confidence_factors` inside `metric_values`.
- Skip flags reduce `probe_reliability` (~0.4–0.6).

#### PROBLEM

1. **PROXY fairness** not distinguished in reliability factor.
2. **High confidence on card coverage** even when O/S/D mapping is weak — experiments: confidence ~0.64–0.73 on thin cards while agent still proposed concrete triples.
3. Confidence not shown in reports executive summary.

#### TARGET

- Factor down `probe_reliability` on `PROXY`, `NOT_APPLICABLE`, `INSUFFICIENT_EVIDENCE`.
- Optional cap: do not propose O/S/D when combined confidence below threshold — **DECISION NEEDED** (agent vs confidence-only signal).

#### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/confidence/engine.py` | Read `probe_status`; PROXY penalty. |
| `backend/app/osd/agent.py` | Optional abstain when confidence < threshold. |

#### TEST

`backend/tests/test_confidence_engine.py` (extend or create).

---

### 4.8 Database, API, and pipeline lifecycle

#### CURRENT

- **Statuses:** `EvaluationStatus` — PENDING, RUNNING, PROBES_COMPLETED, AGENT_COMPLETED, AWAITING_REVIEW, FINALIZED, FAILED.
- **Tables:** `evaluations`, `models`, `probe_results`, `osd_agent_outputs`, `human_reviews`, `final_scores`, `reports` — see `backend/app/db/models.py`.
- **Migrations:** `001_initial_schema.py`, `002_add_evaluation_created_by.py`.
- **Version stamp:** `evaluations.trustlens_version` set at create time.
- **Probe results:** `metric_values` JSONB holds metrics + `probe_status` + `confidence_factors` + flags.

#### PROBLEM

- No DB-level constraint on `probe_status`.
- No `methodology_version` field on evaluations or osd outputs.
- `FINALIZED` without `final_scores` is valid but under-documented in API OpenAPI descriptions.

#### TARGET

- Optional columns or JSON schema version fields for methodology tracking.
- API documents withheld scoring on detail endpoint.

#### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/db/models.py` | Optional new columns. |
| `backend/alembic/versions/003_*.py` | Migration if columns added. |
| `backend/app/schemas/evaluations.py` | `EvaluationRead` fields for scoring state. |
| `README.md` | Sync roadmap with actual Phase 1 partial completion. |

#### TEST

Migration tests in `backend/tests/test_migrations.py` (destructive — see `tests/README.md`).

---

## 5. Dimension: Fairness

### CURRENT

| Item | Detail |
| ---- | ------ |
| Probe | `backend/app/probes/fairness.py` — `FairnessProbe` |
| Dataset | Pinned `adult_fairness` in `configs/datasets_v1.yaml` (`scikit-learn/adult-census-income`) |
| Metrics | `demographic_parity_difference`, `equalized_odds_difference`, `subgroup_f1_spread`, group stats, `min_group_n_observed` |
| Predictor | Default `predict_with_logistic_regression` — sklearn LR on tabular features |
| Status paths | `NOT_APPLICABLE` (non-tabular modality), `FAILED` (load/predict errors), `EVALUATED` on success |
| Evidence | JSON artifact in MinIO via `evidence_store.put_artifact` |
| OSD | Agent `_fairness_band` when `demographic_parity_difference` present; else abstain |
| Flags | `insufficient_slice_size`, `metrics_skipped`, etc. |

**Experiment note (`results/`, `docs/RESULTS_SUMMARY.md`):** Fairness metrics identical across all six HF models at fixed seed — probe does not load HF weights.

### PROBLEM

1. **Not model-faithful** — core trust claim broken for fairness dimension.
2. **`PROXY` status unused** — successful LR path returns `EVALUATED`.
3. **Adult + sex attribute** — default sensitive attribute; no model-task alignment (NLP models evaluated on census tabular proxy).
4. **`needs_human_review: True` always** on success — but agent still proposes O/S/D automatically.
5. No **subgroup selection** tied to model card claims or dataset metadata.

### TARGET

- Primary path: run **imported model** on fairness-relevant dataset with protected attributes (or model-specific slices) via `InferenceBackend`.
- Explicit **legacy proxy mode** (`fairness_mode: proxy_lr`) for backward compat / research reproduction — must emit `ProbeEvaluationStatus.PROXY`.
- Map disparity metrics to **named fairness risks** (e.g. demographic parity violation, equalized odds gap) with separate O/S/D per risk.
- Document limitations when only proxy available.

### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/probes/fairness.py` | Branch: `model_faithful` vs `proxy_lr`; set PROXY on proxy. |
| `backend/app/probes/fairness_metrics.py` | Keep pure functions; optional NLP fairness inputs. |
| `backend/app/datasets/loader.py` | Load slices for NLP fairness if added — **DECISION:** dataset choice. |
| `configs/datasets_v1.yaml` | New fairness datasets if needed. |
| `configs/experiments_v1.yaml` | Pin `fairness_mode` for reproducibility. |
| `backend/app/inference/local_hf.py` | Predictions for fairness subset. |
| `backend/app/osd/mapping_rules.py` | Fairness risk rules from disparity thresholds. |
| `backend/README.md` | Update fairness section when proxy labeled. |

### TEST

| Test | Location |
| ---- | -------- |
| N/A modality | `test_fairness_probe.py` |
| FAILED paths | same |
| PROXY status | new `test_fairness_proxy_status` |
| Model-faithful with fake backend | new integration with `FakeInferenceBackend` |
| Agent abstain / band | `test_osd_agent.py` |

### Dependencies

- [4.4](#44-model-inference-and-resource-checking) inference backend.
- [4.2](#42-osd-mapping-and-heuristicosdagagent) risk catalog for multi-risk fairness.

### Risks

- Re-running experiment grid will change fairness numbers — tag new runs `fairness_mode=v2_model`.
- NLP fairness datasets with protected attributes are **non-trivial** — may remain PROXY for many models until dataset catalog expands.

---

## 6. Dimension: Robustness

### CURRENT

| Item | Detail |
| ---- | ------ |
| Probe | `backend/app/probes/robustness.py`, runner `robustness_nlp.py` |
| Attack | Discrete **char-swap**; budget → `max_changes` |
| Dataset | Default `ag_news_robustness` (`fancyzhx/ag_news`) |
| Gating | `NOT_APPLICABLE` if modality ≠ nlp or model not text-classification/sentiment |
| Metrics | `clean_accuracy`, `robust_accuracy`, `degradation_ratio`, `attack_success_rate` |
| Inference | **Yes** — loads HF sequence classification model on CPU |
| OSD | Abstain when accuracies missing; else O,S,D from clean/robust/degradation |
| Status | `EVALUATED`, `NOT_APPLICABLE`, `FAILED` |

**Experiment note:** 6/18 robustness slots skipped (BERT-tiny LM, ViT-B/16).

### PROBLEM

1. **Single attack** — char-swap only; no FGSM/ART (deferred in docstrings).
2. **Vision modality** pinned (`cifar10_subset`) but unused — always N/A for vision models.
3. **No resource check** before model download.
4. **CPU-only** — may be impractical for large models (silent slowness, not UNSUPPORTED).
5. Soft-fail on model load → `FAILED` with `attack_skipped` flags — good, but user may not see clear UI reason.

### TARGET

- Robustness on imported model for supported tasks (text classification first; vision later).
- Skipped/N/A → abstain O/S/D (already for metrics missing); status surfaced in UI/report.
- Optional additional attacks — **out of scope** unless Phases 20–21 scheduled.
- Map clean/robust gap to **robustness risks** (e.g. input perturbation sensitivity).

### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/probes/robustness.py` | Clearer skip_reason taxonomy; optional SKIPPED vs NOT_APPLICABLE semantics. |
| `backend/app/probes/robustness_nlp.py` | Use `InferenceBackend`; GPU option when CONSTRAINED. |
| `backend/app/osd/mapping_rules.py` | Risk-level mapping from degradation metrics. |
| `configs/datasets_v1.yaml` | SST-2 robustness pin for sentiment models — **DECISION**. |

### TEST

| Test | Location |
| ---- | -------- |
| N/A non-text | `test_robustness_probe.py` |
| FAILED model load | same |
| Pipeline withhold | `test_evaluate_pipeline_evidence.py` |
| Char-swap determinism | existing robustness tests |

### Dependencies

- Inference backend [4.4](#44-model-inference-and-resource-checking).
- Dataset pins stable for experiment reproduction.

### Risks

- Enabling GPU changes determinism across hardware — document seed/device policy.

---

## 7. Dimension: Integrity

### CURRENT

| Item | Detail |
| ---- | ------ |
| Probe | `backend/app/probes/integrity.py` |
| Checks | `revision_pinned`, `files_listed`, `license_declared`, `card_present`, `reproducibility_claims`, `checksum_recorded` |
| Scoring | `integrity_score_0_10 = 10 - fail_count * weight` — **probe evidence**, not FRIES |
| Inference | None — metadata only |
| OSD | pass_rate from checks → O=S=scale(pass_rate), D=8 |
| Status | Default `EVALUATED` always |

### PROBLEM

1. **Not FRIES integrity risk taxonomy** (tampering cannot be ruled out, output uncertainty, change traceability, label uncertainty).
2. **`integrity_score_0_10` misleading** — looks like dimension score in artifacts.
3. **No hash verification** against downloaded weights (import never downloads).
4. **checksum_recorded** uses files fingerprint from Hub listing — not cryptographic proof of local artifact integrity.
5. Reproducibility = keyword groups in card — easily gamed.

### TARGET

- Evidence items aligned to **named integrity risks** from catalog.
- When weights downloaded: SHA-256 of local files vs Hub revision manifest — **DECISION:** mismatch interpretation (provenance vs drift).
- Separate **probe evidence** from O/S/D; abstain when only thin metadata.
- Status `INSUFFICIENT_EVIDENCE` when `card_present` fails and files empty.

### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/probes/integrity.py` | Risk-oriented evidence struct; rename or demote `integrity_score_0_10`; set explicit status. |
| `backend/app/probes/integrity_risks.py` (new) | FRIES risk IDs + check mapping. |
| `backend/app/inference/local_hf.py` | Post-download hash verification hook. |
| `backend/app/osd/agent.py` | Integrity mapping via rules per risk, not single pass_rate. |

### TEST

`backend/tests/test_integrity_probe.py` — extend for status and risk keys.

### Dependencies

- Weight download path from inference [4.4](#44-model-inference-and-resource-checking).

---

## 8. Dimension: Explainability

### CURRENT

| Item | Detail |
| ---- | ------ |
| Probe | `backend/app/probes/explainability.py` |
| Logic | `explainability_card.py` — ATX heading matcher + `card_data` fallback |
| Required sections | `intended_use`, `limitations`, `training_data`, `evaluation`, `ethical_considerations` |
| Metrics | `coverage_ratio`, `sections_present`, `contradictions`, `card_chars` |
| Methods | **No** SHAP/LIME |
| OSD | `coverage_ratio` → O=S=D=scale(coverage); `card_chars==0` → `(2,2,3)` |
| Status | Default `EVALUATED` |

### PROBLEM

1. **Coverage ≠ explainability** — header presence does not measure interpretability quality.
2. **coverage_ratio=0 with card_chars>0** → O=S=D=1 (clamp of scale(0)) — Mode B experiment bug class.
3. **`card_data` fields** can satisfy sections without ATX headings — agent ignores if `coverage_ratio` still 0 due to required section keys.
4. Contradictions detected but **not mapped** to O/S/D adjustments.

### TARGET

- Evidence for **documentation/transparency risks** (missing limitations, missing training data disclosure, etc.) — one O/S/D per risk or abstain.
- Thin documentation → `INSUFFICIENT_EVIDENCE` or low bands with explicit rationale — **DECISION** on `(2,2,3)` vs abstain.
- Optional SHAP/LIME — **out of scope** per README non-goals unless extension phase approved.

### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/probes/explainability.py` | Emit per-section evidence; set status on empty card. |
| `backend/app/probes/explainability_card.py` | Expose which rules fired for mapping traces. |
| `backend/app/osd/agent.py` | Remove `_EMPTY_CARD_BAND` or tie to status; per-risk mapping from missing sections. |
| `configs/osd_mapping_v1.yaml` (new) | Thresholds for coverage → bands. |

### TEST

| Test | Location |
| ---- | -------- |
| Section detection | `test_explainability_probe.py` |
| Agent thin card | `test_osd_agent.py` — extend for coverage 0 + chars > 0 |
| Mode B regression | Fixture from experiment thin-card models |

### Dependencies

- Risk catalog [4.2](#42-osd-mapping-and-heuristicosdagagent).

---

## 9. Dimension: Safety

### CURRENT

| Item | Detail |
| ---- | ------ |
| Probe | `backend/app/probes/safety.py` |
| Logic | `safety_card.py` — misuse, privacy, security_warnings, data_disclosure |
| Metrics | `coverage_ratio`, `high_impact_claims`, check dict |
| Behavioral tests | **None** |
| OSD | Same as explainability + high-impact lowers S,D |
| Status | Default `EVALUATED` |

### PROBLEM

1. **Governance checklist only** — no unsafe-prompt / red-team behavioral evidence.
2. Same **coverage → O/S/D collapse** as explainability.
3. `high_impact_claims` keyword detection only — no validation of mitigation content.
4. FRIES2 safety caps — explicitly **not implemented** (docstring).

### TARGET

- **Governance risks** from disclosure gaps (current checks → risk objects).
- **Behavioral safety probe** (pinned prompt set, refusal rate, harmful completion rate) — **DECISION:** dataset source and severity labeling.
- High-impact deployment claims require stronger evidence or lower O/S/D / abstain.

### CHANGE

| File | Change |
| ---- | ------ |
| `backend/app/probes/safety.py` | Status semantics; split governance vs behavioral evidence. |
| `backend/app/probes/safety_behavioral.py` (new) | Optional phase — prompt suite + inference backend. |
| `configs/safety_prompts_v1.yaml` (new) | Pinned behavioral prompts. |
| `backend/app/osd/agent.py` | Safety risk mapping; abstain on missing behavioral where required — **DECISION**. |

### TEST

`backend/tests/test_safety_probe.py`; future behavioral tests with fake backend.

### Dependencies

- Inference backend for behavioral path.
- Governance path can ship before behavioral.

### Risks

- Behavioral prompts introduce **content policy** and licensing concerns for prompt datasets.

---

## 10. Implementation phases and dependency graph

Aligned with README roadmap but **corrected for code reality** (Phase 1 partial).

```mermaid
flowchart TD
  P1[Phase 1: Status + abstain consistency]
  P2[Phase 2: Resource checker + compatibility]
  P3[Phase 3: InferenceBackend]
  P4[Phase 4: Benchmark estimate]
  P5[Phase 5: Model-faithful fairness + PROXY label]
  P6[Phase 6: Robustness hardening]
  P7[Phase 7: Integrity risk taxonomy]
  P8[Phase 8: E/S risk mapping]
  P9[Phase 9: Safety behavioral optional]
  P10[Phase 10: Mapping traces + catalog]
  P11[Phase 11: Multi-risk + partial FRIES]
  P12[Phase 12: Reports/UI limitations]
  P13[Phase 13: Regression suite + README sync]

  P1 --> P10
  P1 --> P11
  P2 --> P3
  P3 --> P4
  P3 --> P5
  P3 --> P6
  P3 --> P9
  P5 --> P10
  P6 --> P10
  P7 --> P10
  P8 --> P10
  P9 --> P10
  P10 --> P11
  P11 --> P12
  P12 --> P13
```

| Phase | Deliverable | Primary files |
| ----- | ----------- | ------------- |
| **1a (partial done)** | F/R status, abstain, withhold autonomous FRIES | `enums.py`, `fairness.py`, `robustness.py`, `agent.py`, `serialize.py`, `evaluate_pipeline.py` |
| **1b** | I/E/S status; PROXY fairness; review null-safe; UI nullable | Sections [4.3](#43-evidence-probe-status-and-scoring-withhold), [4.5](#45-human-review-assisted-mode) |
| **2** | Resource checker + compatibility API | `compatibility/*`, routers |
| **3** | InferenceBackend + local HF | `inference/*`, `robustness_nlp.py` |
| **4** | Benchmark + estimate | new service + evaluation create flow |
| **5** | Model-faithful fairness + explicit proxy | `fairness.py`, configs |
| **6** | Robustness modality expansion policy | `robustness.py`, datasets |
| **7** | Integrity risks + hash path | `integrity.py` |
| **8** | Explainability risks; fix coverage collapse | `explainability.py`, `agent.py` |
| **9** | Safety behavioral (optional) | `safety_behavioral.py` |
| **10** | Risk catalog + mapping traces | `osd/risk_catalog.py`, `mapping_rules.py` |
| **11** | Multi-risk finalized_osd + partial FRIES | `fries.py`, `serialize.py` |
| **12** | Reports/UI | `reports/builder.py`, frontend pages |
| **13** | Full regression + README roadmap sync | `README.md`, tests |

---

## 11. Test matrix

| Area | Existing tests | Gaps to add |
| ---- | -------------- | ----------- |
| FRIES math | `test_fries_scorer.py`, `SCORING.md` | Partial reweight vectors |
| OSD agent | `test_osd_agent.py` | Risk catalog, coverage=0+card_chars>0 |
| OSD review | — | `test_osd_review.py` (accept_all + null) |
| Fairness | `test_fairness_probe.py` | PROXY, model-faithful fake |
| Robustness | `test_robustness_probe.py` | InferenceBackend injection |
| Integrity | `test_integrity_probe.py` | Status, risk keys |
| Explainability | `test_explainability_probe.py` | Status empty card |
| Safety | `test_safety_probe.py` | Status, behavioral |
| Pipeline | `test_evaluate_pipeline_evidence.py` | Assisted withhold, report |
| Lifecycle | `test_lifecycle.py` | Withheld autonomous E2E |
| API/RBAC | `test_lifecycle.py`, evaluation tests | Human-review abstain |
| Confidence | partial in pipeline test | `test_confidence_engine.py` |
| Reports | report tests if present | Withheld score report |
| Frontend | — | Manual or Playwright — **DECISION** |

Run instructions: `backend/tests/README.md`.

---

## 12. Backward compatibility and historical experiments

### Frozen artifacts (do not silently rewrite)

| Path | Contents |
| ---- | -------- |
| `results/manifest_v1.jsonl` | Run manifest |
| `results/mode_c_runs.csv`, `mode_c_summary.csv` | Autonomous grid |
| `results/mode_b_reviews.csv`, `mode_b_review_plan.json` | Assisted reviews |
| `results/mode_a_manual.csv` | Manual rubric |
| `results/analysis/*` | Phase 26 tables/figures |
| `docs/results_chapter.md`, `docs/RESULTS_SUMMARY.md` | Write-ups |

### Methodology assumptions in those runs

- TrustLens **0.20.1**
- Fairness: **Adult proxy LR**, not HF model
- Robustness: char-swap, skips on non-text-classification
- Agent: heuristic bands including empty-card / zero-coverage collapse
- Autonomous: full FRIES only when five complete O/S/D (withhold otherwise — verify per-run in CSV `fries_score` column)

### Compatibility guidance

1. **Tag new evaluations** with `methodology_version` string when implemented (e.g. `trustlens-methodology-2026-03`).
2. **Leaderboard** should filter or badge rows by methodology version.
3. **Re-run experiments** only with explicit new manifest version (`experiments_v2.yaml`) — document in runbook.
4. **DB migrations** adding non-null columns need defaults for old `probe_results` rows.
5. **API clients** must handle `final_score: null` and nullable O/S/D when Phase 1b ships.

### README drift

`README.md` lines 129–134 and roadmap table (Phase 1 **Absent**, item 2–3) conflict with code. Update README in Phase 13 — not application logic, but blueprint implementers should treat **code as truth** until README synced.

---

## 13. Open decisions register

| ID | Question | Options | Recommendation |
| -- | -------- | ------- | -------------- |
| D1 | Partial FRIES policy | Withhold vs reweight evaluated aspects | Start with **withhold** (current) + report reasons; add reweight as v2 with explicit `scoring_policy` |
| D2 | Empty card O/S/D | Fixed `(2,2,3)` vs abstain | **Abstain** + `INSUFFICIENT_EVIDENCE` for E/S; human fills in Assisted |
| D3 | coverage_ratio=0, card_chars>0 | Band 1 vs abstain | **Abstain** — fixes experiment collapse |
| D4 | Fairness dataset for NLP models | Stay Adult PROXY vs NLP fairness corpus | Short term: **PROXY labeled**; medium: add NLP dataset with attributes |
| D5 | Benchmark gate | Blocking vs advisory | **Advisory** for MVP; blocking for UNSUPPORTED only |
| D6 | Multi-risk review UI | Edit per risk vs per aspect | Per aspect first, per risk when catalog lands |
| D7 | `probe_status` storage | JSONB vs column | JSONB + schema validation first; column if querying needed |
| D8 | Behavioral safety scope | Ship without vs minimal prompt set | **Defer** until governance path stable |
| D9 | Leaderboard withheld scores | Hide vs show with badge | **Hide** from numeric sort; show in filtered view |
| D10 | GPU inference | CPU-only vs auto GPU | **CONSTRAINED** uses GPU when checker allows |

---

## 14. Quick start (for developers)

From `README.md` — local demo stack:

```powershell
cp .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
make seed-users
```

| Service | URL |
| ------- | --- |
| API / OpenAPI | http://127.0.0.1:8000/docs |
| Frontend | http://localhost:5173 |

**Run tests (with Postgres):**

```powershell
$env:DATABASE_URL = 'postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens'
cd backend
python -m pytest -q -m "not integration"
```

**Reproduce experiment analysis (does not re-run evaluations):**

```powershell
cd backend
python -m app.scripts.analyze_experiments
```

Output: `results/analysis/`.

**Key env vars:** `HF_TOKEN` (gated Hub), `DATABASE_URL`, MinIO settings in `.env`.

---

## Appendix A — File index (implementation touch map)

| Concern | Files |
| ------- | ----- |
| Probes | `backend/app/probes/*.py` |
| Probe runner | `backend/app/probes/runner.py`, `registry.py` |
| Datasets | `configs/datasets_v1.yaml`, `backend/app/datasets/` |
| OSD | `backend/app/osd/agent.py`, `base.py`, `serialize.py`, `review.py` |
| Scoring | `backend/app/scoring/fries.py`, `shared/scoring/fixtures/` |
| Pipeline | `backend/app/tasks/evaluate_pipeline.py` |
| API | `backend/app/routers/v1/evaluations.py`, `evaluation_actions.py`, `reports.py` |
| Services | `backend/app/services/evaluation_service.py`, `report_service.py` |
| DB | `backend/app/db/models.py`, `enums.py`, `repositories/*` |
| Reports | `backend/app/reports/builder.py`, `render.py`, `templates/report_v1.html` |
| Frontend | `frontend/src/pages/EvaluationDetailPage.tsx`, `ReviewPage.tsx`, `ReportPage.tsx` |
| Types | `frontend/src/api/types.ts` |
| Tests | `backend/tests/test_*` |
| Experiments | `configs/experiments_v1.yaml`, `backend/app/scripts/run_experiments.py` |
| Docs | `docs/experiments_runbook.md`, `docs/results_chapter.md` |

---

## Appendix B — Evaluation status vs scoring state

| EvaluationStatus | final_scores row | Agent scoring_withheld | User-visible meaning |
| ---------------- | ---------------- | ------------------------ | -------------------- |
| FINALIZED | present | false | Full FRIES available |
| FINALIZED | absent | true | Run complete; score withheld |
| AWAITING_REVIEW | absent | true/false | Assisted; reviewer action needed |
| FAILED | absent | — | Probe/agent/scorer hard failure |
| PROBES_COMPLETED / AGENT_COMPLETED | absent | — | Transient; should not surface to UI long |

---

## Appendix C — ProbeEvaluationStatus semantics (intended)

| Status | Probe should use when | Agent O/S/D | FRIES aspect |
| ------ | --------------------- | ----------- | ------------ |
| `EVALUATED` | Required evidence measured on intended path | May propose (PROPOSED) | Include if triple complete |
| `INSUFFICIENT_EVIDENCE` | Required inputs missing | Abstain | Exclude or withhold overall |
| `NOT_APPLICABLE` | Risk/dimension meaningless for model task | Abstain | Exclude |
| `SKIPPED` | Intentionally not run (config) | Abstain | Exclude |
| `FAILED` | Technical failure | Abstain | Exclude |
| `PROXY` | Substitute model/dataset/predictor | May propose with PROXY label | Include with limitation |

---

*End of blueprint. Implement phases in [Section 10](#10-implementation-phases-and-dependency-graph); resolve [Section 13](#13-open-decisions-register) before coding ambiguous areas.*
