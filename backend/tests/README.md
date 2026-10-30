# Backend test guide

One pytest suite covers unit tests, DB-backed API tests, lifecycle journeys and opt-in live tests. Everything external is faked by default. Only Postgres is real when available, and tests that need it **skip cleanly** when it is not.

## How to run

| What | Command | Needs |
| ---- | ------- | ----- |
| Unit-only (DB tests auto-skip) | `python -m pytest -q -m "not integration and not lifecycle and not slow"` | venv and `pip install -e ".[dev]"` |
| Full suite (unit, API, lifecycle) | `python -m pytest -q -m "not integration"` | `TEST_DATABASE_URL` and root `.env` |
| Skip destructive migration tests | `python -m pytest -q -m "not slow"` | `TEST_DATABASE_URL` |
| Lifecycle regression pack only | `python -m pytest -q -m lifecycle` | `TEST_DATABASE_URL` |
| Live Hub import (network) | `$env:TRUSTLENS_LIVE_TESTS='1'; python -m pytest -q -m integration` | network and `TEST_DATABASE_URL` |
| What CI runs | `python -m pytest -q -m "not integration"` | Postgres service (`TEST_DATABASE_URL`, ephemeral `trustlens_test` DB) |

Pytest loads the repo-root `.env` automatically and rewrites `@postgres:` → `@127.0.0.1:` for host-side runs. See [docs/TRUSTLENS_LOCAL_DEVELOPMENT.md](../../docs/TRUSTLENS_LOCAL_DEVELOPMENT.md).

## Dedicated test database

DB-backed tests, including the destructive migration round-trip, connect **only** through `TEST_DATABASE_URL`, never `DATABASE_URL` (the development database). `conftest.py::resolve_test_database_url` enforces this:

| Situation | Result |
| --------- | ------ |
| `DATABASE_URL` and `TEST_DATABASE_URL` both unset | DB-backed tests skip cleanly, so the unit-only run works with zero Postgres setup |
| `DATABASE_URL` set, `TEST_DATABASE_URL` not | Tests **fail with an error**, not a skip. This is the ambiguous state that used to let the migration test reach the real dev database |
| `TEST_DATABASE_URL` names the dev database (`trustlens`) or equals `DATABASE_URL` | Tests **fail with an error** |

Set up once, against the same Postgres server your `.env` already points at:

```powershell
docker compose exec postgres createdb -U trustlens trustlens_test
```

Then add to `.env` (see `.env.example`):

```text
TEST_DATABASE_URL=postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens_test
```

## Markers

| Marker | Meaning |
| ------ | ------- |
| `slow` | The Alembic migration round-trip (`test_migrations.py`). Destructive; see [Footguns](#footguns) |
| `lifecycle` | End-to-end API journeys (`test_lifecycle.py`): import-hf → create → pipeline → finalize → report → publish → unpublish, for both Autonomous and Assisted (including the review gate) |
| `integration` | Touches live external services (real Hugging Face Hub import). Doubly gated: deselect with `-m "not integration"`, and it is skipped unless `TRUSTLENS_LIVE_TESTS=1` |

## What is faked and what is real

| Service | In tests |
| ------- | -------- |
| Postgres | Real when `TEST_DATABASE_URL` is set; otherwise those tests skip |
| Redis / Celery | Never needed. Enqueue is monkeypatched and the pipeline runs inline |
| Object storage | Never needed. `FakeEvidenceStore` and `FakeReportStore` (`tests/fakes.py`) stand in for the local filesystem stores |
| Hugging Face Hub | Adapter patched with canned records; live only via `integration` |
| WeasyPrint (PDF) | Optional. Without Pango/HarfBuzz OS libraries, reports ship JSON-only (`pdf_uri=null`) |

## Scoring vectors

The frozen FRIES oracle (veto, optimal, golden Π≈5.04, two-risk 5.895→5.89, Table 8 T=5.06, weight rules) is documented in [SCORING.md](SCORING.md). `test_fries_scorer.py` asserts it from `shared/scoring/fixtures/fries_test_vectors.json`.

## Footguns

1. **Migration tests wipe the database.** `test_migrations.py` downgrades to base and back, deleting every row in the target DB. It always targets the isolated `TEST_DATABASE_URL` database, never the dev or Compose database. Don't point `TEST_DATABASE_URL` at a database you care about, or use `-m "not slow"`.
2. **No-DB mode returns 503.** Without `DATABASE_URL`, any `/v1` call fails with `503 DATABASE_UNCONFIGURED`. A "broken API" against a fresh stack is usually this.
3. **Ruff is pinned to the classic default rules** (`E4,E7,E9,F`; `E741` ignored because `O` is the FRIES paper's Occurrence field and a public API name). Newer ruff majors widened their defaults, so the pin keeps local and CI lint identical. Known debt outside the pinned set (for example B008, `Depends(...)` in a default, which is FastAPI house style) is left on purpose.
4. **huggingface_hub majors differ.** Hub 1.x error constructors require a `response=` argument; `test_hf_adapter_unit.py` builds errors through a version-agnostic factory. Verified on hub 0.35 (global `make test` path) and 1.27 (`uv run pytest`, `.venv`).
