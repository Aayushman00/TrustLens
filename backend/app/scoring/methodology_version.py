"""Single source of truth for the methodology_version stamped onto every
Evaluation at creation time (immutable thereafter) and copied verbatim into
every newly generated ReportV1. Legacy evaluations/reports predating this
field carry LEGACY_METHODOLOGY_VERSION (backend) or None (ReportRead, since
old stored report.json blobs genuinely never recorded any value at all —
see docs/superpowers/plans/2026-09-10-v1-dataset-contract-redesign.md
Global Constraints)."""

CURRENT_METHODOLOGY_VERSION = "v2-per-dimension-2026"
LEGACY_METHODOLOGY_VERSION = "pre-v1-fixed-5dim"
