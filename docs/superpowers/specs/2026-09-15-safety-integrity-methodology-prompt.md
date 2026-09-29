# Safety/Integrity methodology accuracy fixes — implementation record

Scope locked by user: targeted accuracy fixes to the existing `SAFETY` and `INTEGRITY`
FRIES probes. No new probe, no new `FriesDimension`, no new capability, no
SHAP/LIME work. Reuse existing infrastructure. Safety Track 2 (behavioral testing)
explicitly out of scope.

## Pre-implementation findings (changed the plan before any code was written)

1. **Item 1 (Safety boilerplate rejection) was already done.** `safety_card.py`'s
   `detect_safety_checks()` already calls the shared `card_markdown.nontrivial()`
   for every heading/body match (`safety_card.py:135`). Commit `bf79fa2` ("fix:
   reject HF placeholder boilerplate in card_markdown.nontrivial()") landed in
   the *shared* `card_markdown.py` module both Explainability and Safety import
   from — its own commit message says so explicitly ("This inverted... on
   EXPLAINABILITY/SAFETY coverage"). No production code change was needed;
   the original spike's claim that Safety didn't use `nontrivial()` was wrong.
   Action taken: added a regression test locking this in (§ Tests below) —
   nothing existed that named Safety specifically before this.

2. **Item 2 (self-computed weight hash) conflicts with a documented architectural
   invariant and was NOT implemented.** `backend/app/probes/integrity.py`'s own
   module docstring: *"Metadata-only: never downloads model weights."*
   `backend/app/adapters/hf_hub.py`'s `HfHubModelAdapter` docstring (ADR 0012):
   *"Never downloads model weight files, never crawls/searches the Hub, and
   never scrapes the website."* `README.md` states the same as current,
   correct, intentional behavior in three places (lines 107, 134, 147–148),
   including naming the absence of a resource/VRAM/RAM/disk gate as a known,
   accepted limitation — not an oversight. Fetching and hashing actual weight
   bytes (which can be many GB, unlike `url_fetch.py`'s 10MB dataset cap)
   would violate this invariant and reintroduce exactly the unbounded-download
   risk the architecture deliberately avoids. **This was not implemented.**
   It needs an explicit decision to amend ADR 0012 before any code changes —
   that decision was not requested or given in this task, so it stays out of
   scope here.

3. **Item 3 (file-listing re-verification) is unblocked and was implemented.**
   It only needs `list_repo_files` (already metadata-only, ADR-0012-compliant —
   the same call `HfHubModelAdapter` already makes at import time), never
   weight bytes.

## Files/functions changed

- `backend/app/probes/integrity_stats.py` — added `RISK_FILES_LISTING_DRIFT`,
  `G_LISTING_UNVERIFIED`, `CLAIM_LISTING_DRIFT`, `CLAIM_LISTING_CURRENT`,
  `CLAIM_LISTING_UNVERIFIED`, and one new `LIMITATIONS` entry.
- `backend/app/probes/integrity_eval.py` — `evaluate_integrity()` gained two
  new optional params (`live_files`, `live_files_error`); added the
  `files_listing_reverification` check block (match/drift/not_performed);
  extended `identity` (`live_files_fingerprint`, `files_listing_reverification`)
  and `claims`/`claim_boundary` (`files_listing_currency`) in both the normal
  path and the early `INSUFFICIENT_EVIDENCE` return, for shape consistency.
- `backend/app/adapters/hf_hub.py` — added `HfHubModelAdapter.list_current_files()`,
  a public, metadata-only (`list_repo_files` only) live re-fetch that raises
  on failure (unlike the import-time `_fetch_file_list`, which swallows
  errors into `[]` — a re-verification caller must distinguish "Hub
  unreachable" from "listing is now genuinely empty").
- `backend/app/probes/integrity.py` — `IntegrityProbe.run()` now attempts
  `HfHubModelAdapter().list_current_files(ctx.model_ref, ctx.model_revision)`
  when import-time `files` metadata is non-empty, catching any exception into
  `live_files_error` so the probe itself can never fail from this.

No schema or migration changes — all new fields live inside the existing
`metric_values`/evidence JSONB, same as every other probe's own evolution.

## Tests added/updated

- `backend/tests/test_safety_card.py` — new
  `test_placeholder_boilerplate_section_does_not_count_as_present`, locking in
  finding (1).
- `backend/tests/test_hf_adapter_unit.py` — `_FakeHfApi` gained a
  `list_files_error` param; six new tests for `list_current_files` (returns
  listing, never touches weight-download methods, and maps
  `RepositoryNotFoundError`/`RevisionNotFoundError`/`GatedRepoError`/generic
  failure to the same error classes `resolve()` already uses).
- `backend/tests/test_integrity_probe.py` — four new tests: not-performed on
  Hub-unreachable, not-performed when import-time `files` was empty (never
  even attempts the live call), match (no risk), drift (risk +
  `aspect_scoring="risk_detected"` + `files_listing_drift` flag).
- `backend/tests/fakes.py` — added `FakeUnavailableHubAdapter`, the shared
  Hub-unreachable stand-in.
- `backend/tests/conftest.py` — added an **autouse** fixture,
  `_integrity_hub_reverify_offline`, patching
  `app.probes.integrity.HfHubModelAdapter` to `FakeUnavailableHubAdapter` for
  every test in the suite by default.

### Why the autouse fixture was necessary (not just a local one)

`IntegrityProbe.run()` now makes a real network call whenever import-time
`files` metadata is non-empty. Several existing tests
(`test_evaluation_lifecycle.py`, `test_finalize_modes.py`,
`test_human_review.py`, `test_evaluation_events.py`, `test_api_reports.py`,
`test_report_builder.py`) exercise the real `IntegrityProbe` through
`run_evaluation_pipeline` using `conftest.fries_complete_model_payload()`,
which has a non-empty `files` list, with no per-file mocking. A fixture
scoped only to `test_integrity_probe.py` would not have protected them — they
would have started making live Hub calls in what are meant to be fully
offline unit tests. The fix is one shared, suite-wide autouse fixture in
`conftest.py`; the fake must raise (not return `[]` or a fixed list), since a
successful-but-different fake listing would silently inject a false
`RISK_FILES_LISTING_DRIFT` into every one of those tests' Integrity output.

## Verification

`pytest tests/test_integrity_probe.py tests/test_hf_adapter_unit.py
tests/test_safety_card.py` — 49 passed. `tests/test_evaluation_lifecycle.py`,
`tests/test_finalize_modes.py`, `tests/test_human_review.py`,
`tests/test_evaluation_events.py`, `tests/test_api_reports.py`,
`tests/test_report_builder.py`, `tests/test_probe_registry.py`,
`tests/test_confidence_engine.py` — no new failures; the pre-existing
`python-multipart`-missing collection errors reproduce identically on
`git stash` (confirmed), unrelated to this change.
`tests/test_e2e_draft_to_report.py` could not be collected in this
environment (`transformers` not installed) — pre-existing, unrelated.

## Not implemented (needs its own decision, separate from this task)

Item 2 — self-computed weight hash — requires either amending ADR 0012 to
permit a bounded, opt-in weight-file download (with a size cap and resource
gate this codebase currently has none of, per README's own named limitation),
or an alternative that doesn't touch weight bytes at all. That trade-off
needs to be brought back as its own decision before any code changes.
