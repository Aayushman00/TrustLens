# TrustLens

Semi-automated FRIES benchmarking framework for trustworthy ML evaluations (Hugging Face Hub models, dual O/S/D modes, evidence-linked reports).

**Development Status:** `Phase 1 — Repository Bootstrap (no ML evaluation)`

## Prerequisites

- Python **3.11+**
- Node.js **18+**
- (Optional) Make

## Repository layout

```text
backend/   FastAPI health shell
worker/    Process shell (no Celery queue yet)
frontend/  Vite + React + TypeScript minimal page
shared/    Scoring fixtures (data only for Phase 16+)
```

## Setup

```powershell
# Backend
cd backend
python -m pip install -e ".[dev]"

# Worker
cd ..\worker
python -m pip install -e ".[dev]"

# Frontend
cd ..\frontend
npm install
```

Copy `.env.example` to `.env` if you want local overrides (`.env` is gitignored).

## Run locally (native — no Docker in Phase 1)

```powershell
# Terminal 1 — API
make dev-backend
# or: cd backend; python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — Worker shell
make dev-worker
# or: cd worker; python -m app.main

# Terminal 3 — Frontend
make dev-frontend
# or: cd frontend; npm run dev
```

- API health: `http://127.0.0.1:8000/health`
- UI: `http://localhost:5173`

## Tests

```powershell
make test
# or: cd backend; python -m pytest -q; cd ..\worker; python -m pytest -q
```

## What Phase 1 does **not** include

Docker, Postgres, Redis, Celery wiring, `/v1` APIs, auth, Hugging Face ingestion, FRIES/O/S/D scoring, probes, or the O/S/D Agent.

**Next:** Phase 2 — Local Development Environment (`docker-compose` for Postgres, Redis, MinIO).
