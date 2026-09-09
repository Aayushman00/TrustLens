# Placeholder / mock fixtures

Everything in this directory is **visual placeholder data only** — it exists
so in-progress screens have realistic density before the corresponding
backend telemetry exists. Per the placeholder-data contract:

- Nothing here is ever presented as a real measurement.
- Every place a fixture from this directory is rendered, the UI shows a
  `MockTag`/`MockBanner` (see `src/components/MockTag.tsx`) next to it.
- When real backend data already exists for a field (e.g. model counts,
  probe status, model revision), the page reads it from the API instead of
  from here — these fixtures only fill genuine backend gaps (e.g. per-batch
  execution telemetry, which TrustLens does not currently record).

When the corresponding backend capability ships, delete the fixture, remove
its `MockTag`, and wire the real field — the surrounding component structure
is designed not to need other changes.
