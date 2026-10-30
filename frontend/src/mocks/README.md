# Placeholder and mock fixtures

> [!WARNING]
> Everything in this directory is **visual placeholder data only**. It exists so in-progress screens have realistic density before the matching backend telemetry exists.

## The placeholder-data contract

- Nothing here is ever presented as a real measurement.
- Wherever a fixture from this directory is rendered, the UI shows a `MockTag` or `MockBanner` next to it (see [`src/components/MockTag.tsx`](../components/MockTag.tsx)).
- When real backend data already exists for a field (model counts, probe status, model revision), the page reads it from the API instead. These fixtures only fill genuine backend gaps, for example per-batch execution telemetry, which TrustLens does not currently record.

## Removing a fixture

When the matching backend capability ships:

1. Delete the fixture.
2. Remove its `MockTag`.
3. Wire the real field.

The surrounding component structure is designed not to need other changes.
