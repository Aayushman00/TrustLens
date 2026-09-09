# Backend test guide (Phase 24)

One pytest suite covers unit, DB-backed API, lifecycle-journey, and opt-in
live tests. Everything external is faked by default; only Postgres is real
when available, and tests that need it **skip cleanly** when it is not.

## How to run

| What | Command | Needs |
|------|---------|-------|
| Unit-only (DB tests auto-skip) | `python -m pytest -q -m "not integration and not lifecycle and not slow"` | venv + `pip install -e ".[dev]"` |
| Full suite (unit + API + lifecycle) | `python -m pytest -q -m "not integration"` | `TEST_DATABASE_URL` + root `.env` |
| Skip destructive migration tests | `python -m pytest -q -m "not slow"` | `TEST_DATABASE_URL` |
| Lifecycle regression pack only | `python -m pytest -q -m lifecycle` | `TEST_DATABASE_URL` |
| Live Hub import (network) | `$env:TRUSTLENS_LIVE_TESTS='1'; python -m pytest -q -m integration` | network + `TEST_DATABASE_URL` |
| What CI runs | `python -m pytest -q -m "not integration"` | Postgres service (`TEST_DATABASE_URL`, ephemeral `trustlens_test` DB) |

Pytest loads the repo-root `.env` automatically and rewrites `@postgres:` → `@127.0.0.1:` for host-side runs. See [docs/LOCAL_DEVELOPMENT.md](../../docs/LOCAL_DEVELOPMENT.md).

### Dedicated test database (`TEST_DATABASE_URL`) — audit P1-2

DB-backed tests — including the destructive migration round-trip below —
connect **only** through `TEST_DATABASE_URL`, never `DATABASE_URL` (the
development database). This is enforced in `conftest.py::resolve_test_database_url`:

- If no database is configured at all (`DATABASE_URL` and `TEST_DATABASE_URL`
  both unset), DB-backed tests skip cleanly — the "unit-only" row above still
  works with zero Postgres setup.
- If `DATABASE_URL` is set (a Postgres connection is configured, e.g. from
  `.env`) but `TEST_DATABASE_URL` is not, tests **fail with an error**
  (not a skip) — this is the exact ambiguous state that used to let the
  migration test reach the real dev database.
- If `TEST_DATABASE_URL` names the known dev database (`trustlens`), or is
  byte-for-byte identical to `DATABASE_URL`, tests **fail with an error**.

Set up once, against the same Postgres server your `.env` already points at:

```
docker compose exec postgres createdb -U trustlens trustlens_test
```

Then add to `.env` (see `.env.example`):

```
TEST_DATABASE_URL=postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens_test
```

## Markers

- `slow` — the Alembic migration round-trip (`test_migrations.py`); destructive
  (see footguns).
- `lifecycle` — Phase 24 end-to-end API journeys (`test_lifecycle.py`): login →
  import-hf → create → pipeline → finalize → report → publish → leaderboard →
  unpublish, for both Autonomous and Assisted (incl. in-flow RBAC 403s).
- `integration` — touches live external services (real Hugging Face Hub
  import). Doubly gated: deselect with `-m "not integration"` *and* skipped
  unless `TRUSTLENS_LIVE_TESTS=1`.

## What is faked vs. real

| Service | In tests |
|---------|----------|
| Postgres | Real when `TEST_DATABASE_URL` is set; otherwise those tests skip |
| Redis / Celery | Never needed — enqueue is monkeypatched; pipeline runs inline |
| MinIO | Never needed — `FakeEvidenceStore` / `FakeReportStore` (`tests/fakes.py`) |
| Hugging Face Hub | Adapter patched with canned records; live only via `integration` |
| WeasyPrint (PDF) | Optional — without Pango/HarfBuzz OS libs reports ship JSON-only (`pdf_uri=null`) |

## Scoring vectors

The frozen FRIES oracle (veto, optimal, golden Π≈5.04, two-risk 5.895→5.89,
Table 8 T=5.06, weight rules) is documented in [SCORING.md](SCORING.md) and
asserted by `test_fries_scorer.py` from
`shared/scoring/fixtures/fries_test_vectors.json`.

## Footguns

1. **Migration tests wipe the database — including seed users.**
   `test_migrations.py` downgrades to base and back, deleting every row in the
   target DB. This now always targets the isolated `TEST_DATABASE_URL`
   database, never the dev/Compose database — nothing to re-seed there. If
   you point `TEST_DATABASE_URL` at a database you care about, re-run
   `make seed-users` after the full suite (or use `-m "not slow"`).
2. **No-DB mode returns 503 before 401.** Without `DATABASE_URL`, any `/v1`
   call — including login — fails `503 DATABASE_UNCONFIGURED` before auth
   runs. A "broken login" against a fresh stack is usually this, not a
   credential problem.
3. **Ruff is pinned to the classic default rules** (`E4,E7,E9,F`; `E741`
   ignored because `O` is the FRIES paper's Occurrence field and a public API
   name). Newer ruff majors widened their defaults — the pin keeps local and
   CI lint identical. Known debt outside the pinned set (e.g. B008
   `Depends(...)`-in-default, FastAPI house style) is intentionally left.
4. **huggingface_hub majors differ.** hub 1.x error constructors require a
   `response=` argument; `test_hf_adapter_unit.py` builds errors through a
   version-agnostic factory. Verified on hub 0.35 (global `make test` path)
   and 1.27 (`uv run pytest`, `.venv`).
