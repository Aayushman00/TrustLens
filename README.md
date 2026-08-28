# TrustLens

Evidence-driven, risk-based auditing and benchmarking for machine-learning models.

TrustLens organizes evaluation around five FRIES dimensions — **Fairness, Robustness, Integrity, Explainability, and Safety** — and treats the overall FRIES number as a **traceable aggregation of risk assessments**, not as an objective or absolute measure of model safety or trustworthiness.

This README describes **what TrustLens is intended to become**, **what the repository currently implements**, and **what remains to be built**. Claims about current behavior are taken from the code. Claims about target methodology follow the TrustLens architecture specification.

## Vision

The intended system is a local-first platform that:

1. Imports a Hugging Face model and checks whether it can run on the available machine.
2. Collects **measured evidence** (metrics, hashes, documentation coverage, behavioral tests).
3. Maps that evidence onto **relevant FRIES risks**.
4. Proposes **Occurrence / Severity / Detection (O/S/D)** ratings.
5. Computes risk trust scores, aspect scores, and a weighted overall FRIES score.
6. Exposes every step for **human review and audit**.

The conceptual pipeline is:

```text
Measured evidence
       ↓
Relevant FRIES risk
       ↓
O / S / D assessment
       ↓
Risk trust score  T_risk = ∛(O × S × D)
       ↓
Aspect score
       ↓
Weighted FRIES score
```

TrustLens must never collapse a raw metric into a dimension score. Demographic parity difference is evidence of disparity, not the Fairness score. Documentation coverage is evidence of transparency, not the Explainability score. An unsafe-response rate is evidence for a safety risk, not the Safety score. An artifact hash is evidence of identity, not the Integrity score.

The FRIES score is a **systematic, interpretable, reproducible audit artifact**. It is not a scientific proof that a model is fair, robust, or safe.

## Methodology

### Three layers

| Layer | What it is | What it is not |
| ----- | ---------- | -------------- |
| **A. Measured evidence** | Probe outputs: DPD, EOD, F1 gap, clean vs perturbed accuracy, SHA-256, card coverage, entropy, and similar measurements | A FRIES dimension score |
| **B. Risk assessment** | Selecting relevant FRIES risks and assigning inverted O/S/D (heuristic unless empirically validated) | Automatic proof that a risk is present or absent |
| **C. FRIES score** | Geometric risk scores, aspect averages, weighted overall T | An objective ranking of models across unrelated tasks |

### O/S/D (FRIES convention)

FRIES adapts FMEA but **inverts** the usual meaning so that **higher values mean greater trustworthiness** (0–10):

- **O (Occurrence)** — higher means the risk is less likely.
- **S (Severity)** — higher means the potential impact is less severe.
- **D (Detection)** — higher means the risk is easier to detect.

A high ordinary FMEA score means high risk. A high FRIES O/S/D score means the opposite. Confusing the two is a correctness failure.

### Scoring (target and implemented math)

For each selected risk:

```text
T_risk = ∛(O × S × D)
```

Edge cases from the original FRIES algorithm, as implemented in `backend/app/scoring/fries.py`:

- Any of O, S, D equal to **0** (veto / deficit) → `T_risk = 0`.
- O = S = D = **10** (optimal) → `T_risk = 10`.

The aspect score is the mean of selected risk scores for that aspect. Overall FRIES is:

```text
FRIES = w_F T_F + w_R T_R + w_I T_I + w_E T_E + w_S T_S
```

Default weights are equal (`0.2` each). Custom weights must be documented in the report. The original methodology typically selects **1–3 relevant risks per aspect**.

Metric → O/S/D bands in this project are **heuristics**. They are labeled `PROPOSED / REQUIRES VALIDATION` and are not published scientific conversions.

### Evidence status (target)

Unavailable evidence must not become a fabricated numeric score. Intended statuses:

| Status | Meaning |
| ------ | ------- |
| `EVALUATED` | Required evidence was measured; O/S/D may exist |
| `INSUFFICIENT_EVIDENCE` | Required inputs were missing — do not invent O/S/D |
| `NOT_APPLICABLE` | Risk is not meaningful for this model/task |
| `SKIPPED` | Intentionally not run |
| `FAILED` | Attempted and failed technically |
| `PROXY` | A substitute model or dataset was used — must be labeled, never silent |

When an entire aspect cannot be evaluated, the overall FRIES score should be marked **partial** (reweight evaluated aspects) or **withheld**. Do not fill the gap with 0 or 1.

## Current implementation

TrustLens today is a **working MVP**: FastAPI + Celery worker + React UI, Hugging Face **metadata** import, five FRIES probes, a heuristic O/S/D agent, original FRIES math, dual evaluation modes, human review, versioned JSON/PDF reports, an opt-in leaderboard, and append-only MinIO evidence.

It is **not** yet the full local-inference, risk-catalog, status-aware architecture described above.

### What works

- **Auth and RBAC** — researcher / reviewer / admin JWT roles.
- **Model registry** — `POST /v1/models/import-hf` resolves Hub **metadata only** (card, tags, license, file list). It does **not** download weights.
- **Async evaluations** — `POST /v1/evaluations` enqueues `trustlens.evaluate_model`; probes run F → R → I → E → S.
- **Probes emit metrics and evidence**, not FRIES scores. Confidence is an **evidence-strength** geometric mean (`data_quality`, `probe_reliability`, `evidence_completeness`) — not correctness and not O/S/D.
- **Original FRIES scorer** — cube-root risk scores, veto, aspect mean, weighted total; frozen vectors in `shared/scoring/fixtures/fries_test_vectors.json`.
- **Modes**
  - `AI_AUTONOMOUS` — agent O/S/D is treated as finalized (`human_reviewed=false`). Disclosure: not ground truth.
  - `AI_ASSISTED` — stops at `AWAITING_REVIEW`; a reviewer accepts or edits O/S/D, then finalize writes FRIES.
- **Reports** — canonical `report_v1` JSON in MinIO; PDF is a projection. Append-only versions.
- **Leaderboard** — private by default; owner/admin publish after FINALIZED. No claim of universal cross-task ranking.
- **Evidence store** — SHA-256 artifacts in MinIO, evaluation-scoped.

### How probes actually run

| Dimension | Current evidence | Runs the imported model? |
| --------- | ---------------- | ------------------------ |
| **Fairness** | Adult Census tabular subset; demographic parity difference, equalized odds difference, subgroup F1 spread | **No.** Default predictor is a sklearn `LogisticRegression` fit on the subset — a **proxy**, not the imported HF model |
| **Robustness** | Pinned NLP subset; clean vs character-swap accuracy | **Yes**, for text-classification models (`transformers` on CPU). Other modalities skip the attack |
| **Integrity** | Hub metadata checks (revision, files, license, card, reproducibility language, recorded checksum). Emits `integrity_score_0_10` as **probe evidence** | No weight download; no SHA-256 of model files vs a trusted reference |
| **Explainability** | Model-card ATX section coverage (intended use, limitations, training data, evaluation, ethical considerations) | Metadata only; not SHAP/LIME |
| **Safety** | Mandatory disclosure checklist (misuse / privacy / security / data) plus high-impact claim flags | Metadata only; no behavioral unsafe-prompt suite |

### Known methodological gaps (present in code)

These are the main deviations from the target architecture:

1. **One O/S/D triple per dimension**, not a catalog of 1–3 selected FRIES risks with structured mapping traces (`rule_id`, band, rationale, methodology version).
2. **Heuristic agent always proposes numbers**, including skip/empty-card defaults such as `(4, 4, 3)` or `(2, 2, 3)`. Skipped fairness/robustness and missing evidence still become numeric O/S/D.
3. **No first-class evaluation statuses** (`EVALUATED`, `INSUFFICIENT_EVIDENCE`, `NOT_APPLICABLE`, `SKIPPED`, `FAILED`, `PROXY`). Soft skips complete the job and still feed the scorer.
4. **Fairness does not evaluate the imported model.** Proxy behavior is documented in code comments but is not a first-class `PROXY` path in the product.
5. **Coverage ratios and integrity pass rates are still easy to confuse with aspect scores.** The scorer uses O/S/D, but the agent bands those O/S/D values directly from coverage / pass rate / disparity — closer to “metric → dimension rating” than “evidence → named risk → O/S/D”.
6. **Overall FRIES always assumes five aspects.** Missing dimensions are not withheld or reweighted; empty risk lists currently score as `0`.
7. **No resource checker, compatibility states, or benchmark-first runtime estimate** before download. HF import never downloads weights; robustness may download a sequence-classification model at probe time with no VRAM/RAM/disk gate.
8. **No shared inference backend.** Only the robustness NLP runner loads the imported model.
9. **Integrity is a weighted checklist**, not the FRIES integrity risk list (tampering cannot be ruled out, output uncertainty unavailable, change traceability, data/label uncertainty). Hash mismatch is not interpreted as provenance vs change.
10. **Safety has no behavioral test set.** Governance coverage is the evidence.
11. **Reports are still score-centric** relative to the target (limited hardware, mapping-trace, and limitation sections).
12. **Historical results** are version-stamped (`evaluations.trustlens_version`) but there is no separate methodology version for heuristic bands vs scorer math.

The research experiment CSVs under `results/` were produced under this older methodology. They must not be silently rewritten.

## Target architecture

flowchart TD
    TL["TrustLens"]

    TL --> MA["Model Analyzer"]
    TL --> DA["Dataset Analyzer"]

    MA --> RC["Resource Checker"]
    DA --> RC

    RC -->|Compatible| COMP["Compatible"]
    RC -->|Unsupported| UNSUP["Unsupported"]

    UNSUP --> SKIP["SKIP: No Download"]

    COMP --> RT["Runtime Estimator"]
    RT --> UC{"User Confirmation"}

    UC -->|No| STOP["Stop Evaluation"]
    UC -->|Yes| BM["Benchmark<br/>50–100 Samples"]

    BM --> LI["Local Inference"]
    LI --> PA["Predictions / Artifacts"]

    PA --> FRS["FRIES Evaluation"]

    FRS --> FAIR["Fairness Probes"]
    FRS --> ROB["Robustness Probes"]
    FRS --> SAFE["Safety Probes"]

    FAIR --> IE["Integrity / Explainability Evidence"]
    ROB --> IE
    SAFE --> IE

    IE --> RD["Risk Detection"]

    RD --> RISKS["Relevant FRIES Risks<br/>+ O / S / D"]

    RISKS --> TR["T_risk"]
    TR --> AS["Aspect Scores"]
    AS --> SCORE["Weighted FRIES Score"]

    SCORE --> HR["Human Review"]
    HR --> OUT["Finalized Audit Report"]

Local Hugging Face execution is the intended default. Hosted inference is not required for the core system. Compatibility must treat **disk, RAM, and VRAM as separate constraints** (reference machine in the spec: RTX 4060 Laptop, 8 GB VRAM, 16 GB RAM). Parameter-count heuristics are estimates with safety margin, not hard guarantees.

## Roadmap

Work is ordered to match the specification’s implementation phases. Items already in the repo are marked.

| Phase | Intent | Status |
| ----- | ------ | ------ |
| 1 | Probe evaluation statuses, nullable O/S/D, status-aware runner | **Absent** |
| 2 | Model analyzer + disk/RAM/VRAM compatibility (`SUPPORTED` / `CONSTRAINED` / `UNSUPPORTED` / `UNKNOWN`) | **Absent** |
| 3 | `InferenceBackend` / `LocalInferenceBackend`; evaluation separated from execution | **Partial** (robustness NLP load only) |
| 4 | Short benchmark, throughput, runtime estimate, optional cache | **Absent** |
| 5 | Fairness on the **imported** model; explicit legacy proxy mode | **Partial** (metrics exist; predictor is proxy LR) |
| 6 | Robustness on the imported model; skipped/N/A must not invent O/S/D | **Partial** (NLP char-swap exists; skip still bands O/S/D) |
| 7 | Integrity as FRIES risk taxonomy + provenance/hash/uncertainty evidence | **Partial** (metadata checklist) |
| 8 | Explainability as documentation/transparency **risks**, not coverage-as-score | **Partial** (card coverage) |
| 9 | Safety behavioral + governance evidence → risks | **Partial** (governance checklist only) |
| 10 | Explicit mapping rules, traces, methodology version | **Partial** (free-text rationales; no structured trace) |
| 11 | Multi-risk aspect aggregation; partial FRIES / withhold policy | **Partial** (math exists; always five aspects; empty → 0) |
| 12 | Reports/UI: evidence, statuses, limitations, calculation breakdown | **Partial** (reports + UI exist; not limitation-complete) |
| 13 | Regression suite covering statuses, proxy, mapping, partial FRIES | **Partial** (strong probe/API/lifecycle tests; status enum untested because absent) |

Also remaining (product, not FRIES math): attack-simulation phases, anonymous public leaderboard, cryptographic report signing, SHAP/LIME as optional explainability extensions, calibrated O/S/D science, OAuth/SSO.

**Non-goals:** do not add an ML model that predicts trustworthiness or classifies risk. Do not treat proxy evaluation as direct evaluation. Do not present heuristic thresholds as empirically validated.

## Repository layout

```text
backend/   FastAPI /v1, probes, O/S/D agent, FRIES scorer, reports
worker/    Celery consumer (same probe pipeline)
frontend/  Vite + React dashboard
configs/   Pinned datasets_v1.yaml + experiments_v1.yaml
docs/      Experiment runbook and results write-up
results/   Frozen experiment CSVs (do not silently rewrite)
shared/    Frozen FRIES scoring fixtures
```

API detail, RBAC, and probe formulas: [backend/README.md](backend/README.md).  
Worker: [worker/README.md](worker/README.md).  
UI routes: [frontend/README.md](frontend/README.md).  
Test matrix: [backend/tests/README.md](backend/tests/README.md).  
Scoring oracle: [backend/tests/SCORING.md](backend/tests/SCORING.md).

## Quick start

**Prerequisites:** Docker Desktop (Compose v2). Python 3.11+ and Node 18+ for native/hybrid runs. Optional: Make.

```powershell
cp .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
make seed-users
```

| Service | Port |
| ------- | ---- |
| API | 8000 |
| Frontend | 5173 |
| Postgres | 5432 |
| Redis | 6379 |
| MinIO | 9000 / 9001 |

Open `http://localhost:5173`. Dev logins:

| Role | Email | Password |
| ---- | ----- | -------- |
| Researcher | `researcher@trustlens.local` | `trustlens-researcher-dev` |
| Reviewer | `reviewer@trustlens.local` | `trustlens-reviewer-dev` |
| Admin | `admin@trustlens.local` | `trustlens-admin-dev` |

Typical demo: import a small text-classification Hub id (for example `distilbert-base-uncased-finetuned-sst-2-english` or `prajjwal1/bert-tiny`) → create an **AI-Autonomous** evaluation → wait for FINALIZED → open report → optionally publish. For **AI-Assisted**, a reviewer accepts or edits proposed O/S/D, then finalize.

Gated Hub repos need `HF_TOKEN` in `.env`. Access tokens last 15 minutes; refresh tokens last 7 days. The demo UI stores tokens in `localStorage` (XSS-readable) — an MVP trade-off, not a production auth design.

OpenAPI: `http://localhost:8000/docs`. Health: `GET /health`.

```powershell
make test    # backend + worker pytest
```

CI (`.github/workflows/ci.yml`) runs ruff + pytest (Postgres service) and the frontend `tsc` + Vite build.

> After the full backend suite against the Compose database, re-run `make seed-users`. Migration tests wipe all rows, including seeded users.

## Using the product honestly

- Agent O/S/D is **proposed**, not ground truth.
- Confidence is **evidence strength**, not model quality.
- Fairness numbers on the default path describe a **tabular logistic-regression proxy**, not the imported NLP model.
- Robustness numbers describe **character-swap** degradation on supported text classifiers only.
- Integrity and safety numbers in this MVP largely reflect **metadata and card checklists**.
- Leaderboard entries are comparable only with shared task/dataset/config/revision context.

## License and research

Experiment protocol and limitations: [docs/experiments_runbook.md](docs/experiments_runbook.md).  
Analysis: [docs/results_chapter.md](docs/results_chapter.md), [docs/RESULTS_SUMMARY.md](docs/RESULTS_SUMMARY.md).
