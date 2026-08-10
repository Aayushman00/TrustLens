# TrustLens Backend (Phase 1)

Empty FastAPI shell with `GET /health` only.

## Run

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or from repo root: `.\scripts\dev-backend.ps1` / `make dev-backend`

## Test

```powershell
cd backend
python -m pytest -q
```

## Out of scope (later phases)

- `/v1/*` routes, auth, DB, Celery, Hugging Face, FRIES/O/S/D
