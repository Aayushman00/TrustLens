<div align="center">

# TrustLens Worker

**Celery worker that runs the five FRIES probes.**

![Celery](https://img.shields.io/badge/Celery-37814A?logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-queue-DC382D?logo=redis&logoColor=white)

[Pipeline](#pipeline-stages) · [Shared code](#shared-code-with-the-backend) · [Config](#config) · [Run](#run-docker) · [Test](#test)

</div>

The worker consumes `trustlens.evaluate_model` from the Redis `trustlens` queue and runs the probes in the order **F → R → I → E → S**. All five dimensions are real: Fairness, Robustness, Integrity, Explainability and Safety. Each probe writes filesystem evidence (ADR 0004, ADR 0014).

| Step | What happens |
| ---- | ------------ |
| Confidence | The runner refines each probe's confidence with the shared Confidence Engine (geometric mean of `data_quality` × `probe_reliability` × `evidence_completeness`) before persisting, and stores the factors under `metric_values.confidence_factors` |
| O/S/D proposal | After the probes, the selected assessment engine persists its output (`osd_agent_outputs`). The default `deterministic` engine **abstains** (no O/S/D). `legacy_heuristic` (`HeuristicOSDAgent`) and `llm_v1` (`HybridOSDAgent`) are opt-in via top-level `probe_config.assessment_engine`, and their values are **PROPOSED / REQUIRES VALIDATION** |
| Autonomous scoring | Autonomous evaluations then run the pure FRIES scorer and upsert `final_scores` |
| Mode disclosure | The autonomous `finalized_osd` carries `human_reviewed=false`, `evaluation_mode` and the locked disclaimer text (shared via the vendored `app/schemas/modes.py`) |

## Pipeline stages

1. Load the evaluation and model. If `model_ref` differs from `hf_repo_id`, mark `FAILED`.
2. `PENDING` → `RUNNING`.
3. `run_all_probes` runs F→R→I→E→S. The Confidence Engine refines each `probe_results.confidence` before insert.
4. `RUNNING` → `PROBES_COMPLETED`.
5. The assessment engine persists `osd_agent_outputs`, then `PROBES_COMPLETED` → `AGENT_COMPLETED`.
6. Mode branch:
   - **`AI_ASSISTED`** → `AWAITING_REVIEW`. The worker never writes assisted `final_scores`; the human-review and finalize path runs **API-side**.
   - **`AI_AUTONOMOUS`** → when complete O/S/D exist, the FRIES scorer upserts `final_scores` (`human_reviewed=false` plus disclaimer); otherwise FRIES is withheld. Either way → `FINALIZED`.

Soft-skips still write evidence and let the evaluation continue. Agent or scorer logic errors → `FAILED`, with no Celery retry. Report generation (canonical JSON and PDF) also runs **API-side**; reports read the rows this pipeline persists.

## Shared code with the backend

`backend/` and `worker/` both use the top-level package name `app`, so installing `trustlens-backend` into the worker image would collide. Instead, [`Dockerfile.worker`](../Dockerfile.worker) **vendors** these single-source modules from `backend/app/` into the worker image at build time:

| Source (backend) | Destination (worker image) |
| ---------------- | -------------------------- |
| `backend/app/db/` | `./app/db/` |
| `backend/app/core/db.py` | `./app/core/db.py` |
| `backend/app/core/storage.py` | `./app/core/storage.py` |
| `backend/app/schemas/internal.py` | `./app/schemas/internal.py` |
| `backend/app/schemas/evidence.py` | `./app/schemas/evidence.py` |
| `backend/app/schemas/probe_config.py` | `./app/schemas/probe_config.py` |
| `backend/app/storage/` | `./app/storage/` |
| `backend/app/datasets/` | `./app/datasets/` |
| `backend/app/probes/` | `./app/probes/` (all five FRIES probes) |
| `backend/app/confidence/` | `./app/confidence/` (Confidence Engine) |
| `backend/app/osd/` | `./app/osd/` (O/S/D agent, PROPOSED) |
| `backend/app/scoring/` | `./app/scoring/` (pure FRIES scorer) |
| `backend/app/schemas/modes.py` | `./app/schemas/modes.py` (disclaimer texts) |
| `backend/app/schemas/evaluation_contract_v2.py` | `./app/schemas/evaluation_contract_v2.py` |
| `backend/app/inference/` | `./app/inference/` (`LocalHFBackend`, device auto-detection) |
| `backend/app/tasks/evaluate_pipeline.py` | `./app/tasks/evaluate_pipeline.py` |

**ML dependencies.** The worker installs `torch` and `transformers` for Fairness and Robustness inference. Explainability and Safety (governance part) read metadata only, using stdlib card parsing.

## Config

| Variable | Purpose |
| -------- | ------- |
| `REDIS_URL` | Celery broker and result backend |
| `DATABASE_URL` | Postgres (same ORM as the API) |
| `STORAGE_DIR` | Artifact directory (shared with the API) |
| `HF_TOKEN` / `HF_HOME` | Hub auth and cache |

## Run (Docker)

```powershell
docker compose up --build -d worker
docker compose logs worker -f
```

The container runs:

```text
celery -A app.celery_app worker --loglevel=INFO -Q trustlens
```

## Test

```powershell
cd worker
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Out of scope

Human review accept/edit and the assisted FRIES write (API-side), report generation (API-side), validated metric → O/S/D science and any LLM agent, confidence calibration claims, FRIES2 caps, NLP risk extraction, evidence GC, a public evidence download API, and attack simulation (post-MVP).
