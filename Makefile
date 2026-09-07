# TrustLens — local native scripts + Docker helpers

.PHONY: help dev-backend dev-frontend dev-worker test test-unit test-backend lint compose-up compose-infra compose-down migrate migrate-native seed-users

help:
	@echo "TrustLens targets:"
	@echo "  make compose-up      - docker compose up --build -d (full stack)"
	@echo "  make compose-infra   - postgres + redis + minio only (native API dev)"
	@echo "  make compose-down    - docker compose down"
	@echo "  make migrate         - alembic upgrade head (via api container)"
	@echo "  make migrate-native  - alembic upgrade head (host, needs DATABASE_URL)"
	@echo "  make seed-users      - seed dev users (admin/researcher/reviewer, via api container)"
	@echo "  make dev-backend     - run FastAPI with uvicorn (native)"
	@echo "  make dev-worker      - run worker shell (native)"
	@echo "  make dev-frontend    - run Vite frontend (native)"
	@echo "  make test            - backend + worker pytest (-m 'not integration')"
	@echo "  make test-unit       - backend pytest, skip lifecycle/slow (no Postgres OK)"
	@echo "  make test-backend    - backend pytest (-m 'not integration', needs Postgres)"
	@echo "  make lint            - run ruff on backend/worker (if installed)"
	@echo ""
	@echo "See docs/LOCAL_DEVELOPMENT.md for Windows/PowerShell equivalents."

compose-up:
	docker compose up --build -d

compose-infra:
	docker compose up -d postgres redis minio minio-init

compose-down:
	docker compose down

migrate:
	docker compose exec api alembic upgrade head

migrate-native:
	cd backend && alembic upgrade head

seed-users:
	docker compose exec api python -m app.scripts.seed_users

dev-backend:
	cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-worker:
	cd worker && celery -A app.celery_app worker --loglevel=INFO -Q trustlens

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && python -m pytest -q -m "not integration"
	cd worker && python -m pytest -q

test-unit:
	cd backend && python -m pytest -q -m "not integration and not lifecycle and not slow"

test-backend:
	cd backend && python -m pytest -q -m "not integration"

lint:
	cd backend && python -m ruff check app tests
	cd worker && python -m ruff check app tests
