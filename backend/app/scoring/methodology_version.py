"""Single source of truth for the methodology_version stamped onto every
Evaluation at creation time (immutable thereafter) and copied verbatim into
every newly generated ReportV1. Legacy evaluations/reports predating this
field carry LEGACY_METHODOLOGY_VERSION (backend) or None (ReportRead, since
old stored report.json blobs genuinely never recorded any value at all —
see docs/superpowers/plans/2026-09-10-v1-dataset-contract-redesign.md
Global Constraints)."""

# v6-eod-fairness-risk-2026 (round 3, L4.1): the binary fairness risk
# (F-FAIR-EOPP, tl-fairness-binary-v1.2) is triggered by the equal-opportunity
# difference (max_g TPR_g - min_g TPR_g) and its bootstrap CI; G-FAIR-CI-WIDE
# now applies to that CI; every eligible group needs >= 1 positive label.
# Replaces v5's excess_dpd_v2 trigger, an exploratory candidate rejected after
# inspection for its base-rate dependence (EOD was chosen after that
# inspection, not pre-registered before it).
# v5-binary-fairness-risk-2026 (round 3, L4, rejected): binary fairness emits
# aspect_scoring / risks_triggered (F-FAIR-EXCESS-DPD) from bootstrapped
# excess_dpd_v2 under the pre-declared EPSILON rule (tl-fairness-binary-v1.1);
# fewer than 2 groups with n >= min_group_n now abstains (INSUFFICIENT_EVIDENCE).
# Previous below.
# v4-disclosure-gaps-2026 (round 3, L3): documentation/disclosure gaps
# (S-GOV-DISCLOSURE-GAP, E-DOC-INCOMPLETE, I-INT-REV-UNPINNED,
# I-INT-MANIFEST-MISSING, I-INT-LICENSE-UNDISCLOSED) move from risks_triggered
# to disclosure_gaps with aspect_scoring="disclosure_gap"; local model folders
# are identified by their weight-file sha256 (checked against train_manifest.json).
# Previous: "v3-hardening-2026" — robustness band from accuracy drop,
# constant-predictor gate, behavioural safety band (stored evaluations keep their stamp).
CURRENT_METHODOLOGY_VERSION = "v6-eod-fairness-risk-2026"
LEGACY_METHODOLOGY_VERSION = "pre-v1-fixed-5dim"
