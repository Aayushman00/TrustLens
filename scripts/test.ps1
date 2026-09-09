# TrustLens Phase 1 — run tests (Windows PowerShell)
$ErrorActionPreference = "Stop"
$root = Join-Path $PSScriptRoot ".."
Set-Location (Join-Path $root "backend")
python -m pytest -q
Set-Location (Join-Path $root "worker")
python -m pytest -q
Write-Host "All Phase 1 tests passed."
