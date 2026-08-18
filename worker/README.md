# TrustLens Worker (Phase 22 — no worker changes; version bump only)

Celery worker that consumes `trustlens.evaluate_model` from the Redis `trustlens`
queue and runs FRIES probes (F→R→I→E→S). **All five dimensions are real** after
Phase 14 (Fairness, Robustness, Integrity, Explainability, Safety). Each probe
writes MinIO evidence (ADR 0004). Phase 15: the runner refines each probe's
confidence via the shared Confidence Engine (geometric mean of `data_quality` ×
`probe_reliability` × `evidence_completeness`) before persisting, and stores the
factors under `metric_values.confidence_factors`. Phase 16: after probes the
`HeuristicOSDAgent` persists a **PROPOSED / REQUIRES VALIDATION** O/S/D
suggestion (`osd_agent_outputs`); Autonomous evals then run the pure FRIES
scorer and upsert `final_scores`. Phase 17: the Autonomous `finalized_osd`
also carries the mode disclosure — `human_reviewed=false`, `evaluation_mode`,
and the locked disclaimer text (shared via vendored `app/schemas/modes.py`).

## Shared ORM / evidence / probes strategy (Option A)

`backend/` and `worker/` both use the top-level package name `app`, so installing
`trustlens-backend` into the worker image would collide. Instead,
[`Dockerfile.worker`](../Dockerfile.worker) **vendors** these single-source modules
from `backend/app/` into the worker image at build time:

| Source (backend) | Destination (worker image) |
|------------------|----------------------------|
| `backend/app/db/` | `./app/db/` |
| `backend/app/core/db.py` | `./app/core/db.py` |
| `backend/app/core/s3.py` | `./app/core/s3.py` |
| `backend/app/schemas/internal.py` | `./app/schemas/internal.py` |
| `backend/app/schemas/evidence.py` | `./app/schemas/evidence.py` |
| `backend/app/schemas/probe_config.py` | `./app/schemas/probe_config.py` |
| `backend/app/storage/` | `./app/storage/` |
| `backend/app/datasets/` | `./app/datasets/` |
| `backend/app/probes/` | `./app/probes/` (all five FRIES probes) |
| `backend/app/confidence/` | `./app/confidence/` (Phase 15 Confidence Engine) |
| `backend/app/osd/` | `./app/osd/` (Phase 16 O/S/D agent — PROPOSED) |
| `backend/app/scoring/` | `./app/scoring/` (Phase 16 pure FRIES scorer) |
| `backend/app/schemas/modes.py` | `./app/schemas/modes.py` (Phase 17 disclaimer texts) |
| `backend/app/tasks/evaluate_pipeline.py` | `./app/tasks/evaluate_pipeline.py` |
| `configs/datasets_v1.yaml` | `./configs/datasets_v1.yaml` |

`DATASETS_CONFIG_PATH=/app/configs/datasets_v1.yaml` is set in the image.

### ML deps

Worker installs torch/transformers/datasets (Robustness) plus fairlearn/sklearn/numpy
(Fairness). Explainability and Safety are metadata-only (stdlib card parsing).

## Celery CMD

```text
celery -A app.celery_app worker --loglevel=INFO -Q trustlens
```

## Pipeline stages

1. Load evaluation + model; fail → `FAILED` if `model_ref` ≠ `hf_repo_id`
2. `PENDING` → `RUNNING`
3. `run_all_probes` — F→R→I→E→S (all real); ConfidenceEngine refines each
   `probe_results.confidence` before insert (Phase 15)
4. `RUNNING` → `PROBES_COMPLETED`
5. `HeuristicOSDAgent.propose` → persist `osd_agent_outputs` (PROPOSED / REQUIRES
   VALIDATION) → `PROBES_COMPLETED` → `AGENT_COMPLETED` (Phase 16)
6. Mode branch:
   - `AI_ASSISTED` → `AWAITING_REVIEW` — the worker never writes Assisted
     `final_scores`; the Phase 18 human-review → finalize path runs **API-side**
     (no worker/Dockerfile change)
   - `AI_AUTONOMOUS` → FRIESScorer on agent O/S/D → upsert `final_scores`
     (`finalized_osd` carries `human_reviewed=false` + disclaimer, Phase 17) → `FINALIZED`

Soft-skips still write evidence and let the eval continue. Agent/scorer logic
errors → `FAILED` (no Celery retry).

Phase 19 report generation (canonical JSON + PDF) runs **API-side** — the
worker is untouched; reports read the rows this pipeline persists.

**Next (MVP path):** Phase 22 opt-in leaderboard; Phases 20–21 attack sim are post-MVP.

## Config

| Variable | Purpose |
|----------|---------|
| `REDIS_URL` | Celery broker + result backend |
| `DATABASE_URL` | Postgres (same ORM as API) |
| `S3_ENDPOINT` / keys / bucket | MinIO evidence store |
| `DATASETS_CONFIG_PATH` | Pinned datasets YAML |
| `HF_TOKEN` / `HF_HOME` | Hub auth + cache |

## Run (Docker)

```powershell
docker compose up --build -d worker
docker compose logs worker -f
```

## Test

```powershell
cd worker
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Out of scope

Human review accept/edit + Assisted FRIES write (18, API-side), report
generation (19, API-side), validated metric→O/S/D science / LLM agent,
confidence calibration claims, FRIES2 caps, NLP risk extraction, evidence GC,
public evidence download API.
