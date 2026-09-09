# TrustLens Phase 1 — start worker shell (Windows PowerShell)
Set-Location (Join-Path $PSScriptRoot "..\worker")
python -m app.main
