# 06 — Architecture and migration

## Design constraints

- Keep what works: FastAPI + Celery + Postgres + Redis + React, local-first, append-only sha256 evidence store, versioned JSON reports, human-review step.
- Replace, don't layer: v1's `confidence/engine.py`, `osd/*` heuristics and `scoring/fries.py` become a legacy view, not the main path.
- Pure cores: statistics, posteriors and the decision rule are pure functions (stdlib/numpy), importable without DB or Celery, as v1's `fairness_stats` already shows.

## Target module layout

```
backend/app/
  adapters/        model + dataset adapters (hf_hub, local, endpoint)      # extend
  inference/       backends per rung (text, tabular, image)                # extend
  perturb/         perturbation library with invariance contracts          # new
  probes/          property + disclosure probes, EvidenceItem emitters     # refactor
  evidence/        EvidenceItem schema, store (sha256), provenance         # from storage/
  posterior/       Beta (Jeffreys), Newcombe differences, paired bootstrap # new
  decision/        UseCaseProfile, Tier A gate, Bayes rule, interval view,
                   sensitivity, EVPI display, doubling rule + α budget     # new (no VOI planner)
  legacy/          confidence/, osd/{agent,deterministic,review}, scoring/fries.py (frozen v1 view)   # moved
                   (osd/hybrid.py and osd/llm_client.py are REMOVED, not moved: no LLMs in v2)
  reports/         builder: Decision + evidence tables + methodology       # extend
trustbench/        corpus manifest, generators (promoted from scripts/train_flawed_suite.py),
                   independent-reference runner, scorer                    # new top-level
```

Module fates for v1 code are listed in DESIGN_SYNTHESIS 5.7.

`legacy/` remains importable so v1 fixtures (`shared/scoring/fixtures`) keep passing until the legacy view is retired.

## API changes (additive first)

| Endpoint | Change |
| -------- | ------ |
| `POST /v1/evaluations` | Accepts `profile` (id or inline); returns applicability matrix preview |
| `GET /v1/evaluations/{id}` | Adds `evidence_items`, `decision`, `followup_plan` (unresolved dimensions, look index, α spent); keeps v1 fields until removal |
| `POST /v1/evaluations/{id}/followups` | Run the next look: double rows on the unresolved dimensions (≤ 3 looks) |
| `GET/POST /v1/profiles` | CRUD for use-case profiles with presets |
| Review endpoints | Reviewer can override a non-hard-fail action with a required justification, stored as a separate labelled record that never mutates machine output. Tier A hard fails have no override; only an `acknowledged_risk` annotation (ADR 0014) |

Versioning: `methodology_version` becomes a tuple (probes, posterior, profile-schema). Reports pin all three. Old reports remain readable; v2 never re-scores them silently.

## Database migration

- Alembic migration adds `evidence_items`, `posteriors`, `decisions`, `profiles`, `followup_runs`; v1 tables are untouched in the first release.
- Backfill is optional and explicit: a script may recompute v2 decisions for archived v1 evaluations *only when* their stored evidence is sufficient, marking the result `backfilled`.
- Reversible migrations with a test that upgrades and downgrades on a populated snapshot.

## Reliability requirements

| Area | Requirement |
| ---- | ----------- |
| Install | `make up` from a clean clone works on Windows/macOS/Linux with CPU-only compose; GPU optional. First run downloads nothing implicitly beyond the requested model |
| Failures | Every failure state is typed, shown in the UI with a next step; partial progress is kept (v1 already persists per probe) |
| Resource limits | Per-probe time and memory budgets; clear `budget_exceeded` evidence status instead of a crash |
| Determinism | Seeds recorded; two runs on different machines give identical evidence hashes (S6) or the difference is explained by recorded device nondeterminism |
| Security | SSRF guard on dataset URLs, redirect and size limits, no `trust_remote_code`, safe pickle scanning without execution, secrets only via env, path-traversal tests on the evidence store, dependency audit in CI |
| Observability | Structured logs with evaluation id, probe id, durations; `/healthz` and `/readyz` |
| Docs | README claims checked in CI against the registry (supported pairings, probe list); every probe has a method card (formula, assumptions, limits, references) generated from code docstrings |

## Testing strategy

- Unit + property tests for pure cores (spec 02/03 properties).
- Contract tests for API schemas (OpenAPI snapshot).
- Golden-file tests for `Decision` JSON and report JSON.
- Integration tests with tiny models on CPU in CI (≤ 10 min).
- TrustBench smoke subset in CI (3 models); full TrustBench on demand.
- Frontend: component tests exist; add Playwright happy path (draft → run → decision → follow-up).
- Mutation spot checks on `posterior/` and `decision/`.

## Repository hygiene (done / to do)

Done in this cleanup:
- v1 docs, plans, audits, ADR-excluded notes moved to `archive/v1/docs/`; root notes, UI mock-ups, zips, backups and the form CSV moved to `archive/v1/legacy/`. Nothing was deleted.
- Code comments that cited `docs/superpowers/plans/…` were repointed to `archive/v1/docs/superpowers/plans/…`.

To do:
- Decide what leaves git entirely (large binaries in `archive/v1/legacy/`) via `.gitignore` or a release asset.
- Remove `graphify-out/` and `.cursor/` from tracked scope if present (both ignored or local-only).
- Single `CONTRIBUTING.md` and `docs/adr/` index; new ADRs for: decision-theoretic core (0014), TrustBench protocol (0015), capability ladder (0016), legacy-view retirement (0017).
- Rewrite `README.md` once M3 lands; until then it links to `docs/v2/`.

## Branching

`Main` stays at v1 (tagged `v1.0-thesis`). Work on `v2/*` branches off Main; each milestone merges only when its exit criteria (spec 07) pass. No Claude attribution trailers in commits (project rule).
