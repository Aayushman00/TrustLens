"""Single source of truth for the methodology_version stamped onto every
Evaluation at creation time (immutable thereafter) and copied verbatim into
every newly generated ReportV1. Legacy evaluations/reports predating this
field carry LEGACY_METHODOLOGY_VERSION (backend) or None (ReportRead, since
old stored report.json blobs genuinely never recorded any value at all —
see docs/superpowers/plans/2026-09-10-v1-dataset-contract-redesign.md
Global Constraints)."""

# v4-disclosure-gaps-2026 (round 3, L3): documentation/disclosure gaps
# (S-GOV-DISCLOSURE-GAP, E-DOC-INCOMPLETE, I-INT-REV-UNPINNED,
# I-INT-MANIFEST-MISSING, I-INT-LICENSE-UNDISCLOSED) move from risks_triggered
# to disclosure_gaps with aspect_scoring="disclosure_gap"; local model folders
# are identified by their weight-file sha256 (checked against train_manifest.json).
# Previous: "v3-hardening-2026" — robustness band from accuracy drop,
# constant-predictor gate, behavioural safety band (stored evaluations keep their stamp).
CURRENT_METHODOLOGY_VERSION = "v4-disclosure-gaps-2026"
LEGACY_METHODOLOGY_VERSION = "pre-v1-fixed-5dim"
