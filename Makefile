# TrustLens — local native scripts + Docker helpers

.PHONY: help dev-backend dev-frontend dev-worker test lint compose-up compose-down migrate migrate-down seed-users

help:
	@echo "TrustLens targets:"
	@echo "  make compose-up    - docker compose up --build -d"
	@echo "  make compose-down  - docker compose down"
	@echo "  make migrate       - alembic upgrade head (via api container)"
	@echo "  make migrate-down  - alembic downgrade -1 (via api container)"
	@echo "  make seed-users    - seed dev users (admin/researcher/reviewer, via api container)"
	@echo "  make dev-backend   - run FastAPI with uvicorn (native)"
	@echo "  make dev-worker    - run worker shell (native)"
	@echo "  make dev-frontend  - run Vite frontend (native)"
	@echo "  make test          - run backend + worker pytest"
	@echo "  make lint          - run ruff on backend/worker (if installed)"

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

migrate:
	docker compose exec api alembic upgrade head

migrate-down:
	docker compose exec api alembic downgrade -1

seed-users:
	docker compose exec api python -m app.scripts.seed_users

dev-backend:
	cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-worker:
	cd worker && celery -A app.celery_app worker --loglevel=INFO -Q trustlens

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && python -m pytest -q
	cd worker && python -m pytest -q

lint:
	cd backend && python -m ruff check app tests
	cd worker && python -m ruff check app tests
