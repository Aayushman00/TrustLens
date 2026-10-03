"""Explainability probe constants (tl-explainability-v1.1)."""

from __future__ import annotations

METHODOLOGY_VERSION = "tl-explainability-v1.1"
METHODOLOGY_BASIS = "TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md"

RISK_DOC_INCOMPLETE = "E-DOC-INCOMPLETE"
RISK_DOC_CONTRADICTION = "E-DOC-CONTRADICTION"

G_CARD_EMPTY = "G-EXP-CARD-EMPTY"

# aspect_scoring = risk_detected means evidence-layer detection only — not FRIES.
ASPECT_NOT_SCORED = "not_scored"
ASPECT_RISK_DETECTED = "risk_detected"
ASPECT_NO_MATERIAL_RISK = "no_material_risk"
# v1.1: missing card sections (E-DOC-INCOMPLETE) are an absence of documentation,
# recorded under disclosure_gaps; only E-DOC-CONTRADICTION stays in risks_triggered.
ASPECT_DISCLOSURE_GAP = "disclosure_gap"

CLAIM_SUPPORTED = (
    "Required model-card documentation sections were checked for presence with "
    "non-trivial body text; coverage counts and keyword-level contradiction flags "
    "were recorded."
)
CLAIM_NOT_ESTABLISHED = (
    "This does not establish explanation faithfulness, causal correctness, human "
    "usefulness, SHAP/attention availability, or general explainability quality. "
    "Documentation coverage is not proof that the model is explainable."
)

NOTE = (
    "Layer A documentation/transparency evidence only — not O/S/D or "
    "interpretability quality"
)

LIMITATIONS: tuple[str, ...] = (
    "Explainability v1 measures model-card documentation completeness and simple "
    "consistency flags, not runtime explanations or attribution quality.",
    "Named E-DOC-* values are evidence-layer detections only; scored_risk_id "
    "remains null and no FRIES occurrence is assigned.",
    "E-DOC-INCOMPLETE is a documentation gap (disclosure_gaps); only "
    "E-DOC-CONTRADICTION is a risk (aspect_scoring=risk_detected) — neither is a "
    "FRIES-scored risk.",
    "Alias heading matching and keyword contradiction checks are heuristic and "
    "uncalibrated.",
    "coverage_ratio counts present required sections; it is not an explainability "
    "quality score.",
)
