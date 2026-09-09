# TrustLens — one-time local backend dev setup (Windows PowerShell)
# Usage: .\scripts\setup-local-dev.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$VenvPip = Join-Path $RepoRoot ".venv\Scripts\pip.exe"

Write-Host "TrustLens local dev setup ($RepoRoot)"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating .venv ..."
    python -m venv (Join-Path $RepoRoot ".venv")
}

Write-Host "Installing backend[dev] ..."
& $VenvPip install --upgrade pip
& $VenvPip install -e (Join-Path $RepoRoot "backend[dev,robustness,fairness]")

$EnvFile = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (-not (Test-Path $EnvExample)) {
        throw "Missing .env.example at repo root"
    }
    Copy-Item $EnvExample $EnvFile
    (Get-Content $EnvFile -Raw) `
        -replace '@postgres:', '@127.0.0.1:' `
        -replace 'redis://redis:', 'redis://127.0.0.1:' `
        -replace 'http://minio:', 'http://127.0.0.1:' |
        Set-Content $EnvFile -NoNewline
    Write-Host "Created .env with 127.0.0.1 service hostnames (native host -> Compose infra)."
} else {
    Write-Host ".env already exists — not overwritten."
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. .\.venv\Scripts\Activate.ps1"
Write-Host "  2. docker compose up -d postgres redis minio minio-init"
Write-Host "  3. cd backend; alembic upgrade head"
Write-Host "  4. python -m app.scripts.seed_users   (from backend/, venv active)"
Write-Host "  5. uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "See docs/LOCAL_DEVELOPMENT.md for full details."
