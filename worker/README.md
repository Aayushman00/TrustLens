# TrustLens Worker (Phase 1)

Process shell only. Logs ready and waits for Ctrl+C. No Celery/Redis tasks.

## Run

```powershell
cd worker
python -m pip install -e ".[dev]"
python -m app.main
```

Or from repo root: `.\scripts\dev-worker.ps1` / `make dev-worker`

## Test

```powershell
cd worker
python -m pytest -q
```

## Out of scope

- `evaluate_model` tasks, Redis broker, probe execution (Phase 2/7+)
