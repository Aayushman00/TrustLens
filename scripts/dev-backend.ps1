# TrustLens Phase 1 — start backend (Windows PowerShell)
Set-Location (Join-Path $PSScriptRoot "..\backend")
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
