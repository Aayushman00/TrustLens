# TrustLens Phase 1 — local native scripts (no Docker)

.PHONY: help dev-backend dev-frontend dev-worker test lint

help:
	@echo "TrustLens Phase 1 targets:"
	@echo "  make dev-backend   - run FastAPI with uvicorn"
	@echo "  make dev-worker    - run worker shell"
	@echo "  make dev-frontend  - run Vite frontend"
	@echo "  make test          - run backend + worker pytest"
	@echo "  make lint          - run ruff on backend/worker (if installed)"

dev-backend:
	cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-worker:
	cd worker && python -m app.main

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && python -m pytest -q
	cd worker && python -m pytest -q

lint:
	cd backend && python -m ruff check app tests
	cd worker && python -m ruff check app tests
