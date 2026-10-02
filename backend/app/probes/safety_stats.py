"""Safety probe constants (tl-safety-v1.1)."""

from __future__ import annotations

METHODOLOGY_VERSION = "tl-safety-v1.1"
METHODOLOGY_BASIS = "TRUSTLENS_FIVE_PROBE_METHODOLOGY_AUDIT.md"

RISK_GOV_DISCLOSURE_GAP = "S-GOV-DISCLOSURE-GAP"

G_CARD_EMPTY = "G-SAFE-CARD-EMPTY"

# aspect_scoring = risk_detected means evidence-layer detection only — not FRIES.
ASPECT_NOT_SCORED = "not_scored"
ASPECT_RISK_DETECTED = "risk_detected"
ASPECT_NO_MATERIAL_RISK = "no_material_risk"
# v1.1: a missing disclosure section is an absence of documentation, not
# evidence of a model defect — recorded under disclosure_gaps, never risks_triggered.
ASPECT_DISCLOSURE_GAP = "disclosure_gap"

CLAIM_SUPPORTED = (
    "Required safety-disclosure model-card sections were checked for presence with "
    "non-trivial body text; documentation completeness counts and lexical presence "
    "of listed high-impact phrases were recorded as documentation metadata flags."
)
CLAIM_NOT_ESTABLISHED = (
    "This does not establish model safety or unsafety, actual deployment risk, "
    "mitigation effectiveness, harm severity, policy compliance, medical/financial "
    "fitness, or refusal capability. Phrase matches (high_impact_claims) are lexical "
    "documentation evidence only — not evidence that the model is high-risk, "
    "unsafe, harmful, or safety-critical."
)

NOTE = (
    "Layer A safety-governance disclosure evidence only — not O/S/D, not behavioral "
    "safety, not FRIES2 caps"
)

LIMITATIONS: tuple[str, ...] = (
    "Safety v1 measures model-card safety-disclosure completeness and lexical phrase "
    "matches, not runtime refusal or harm behavior.",
    "Named S-GOV-DISCLOSURE-GAP is a documentation gap recorded under "
    "disclosure_gaps, not risks_triggered; it is not evidence of unsafe behaviour.",
    "aspect_scoring=disclosure_gap means required disclosure sections are missing — "
    "not a FRIES-scored risk.",
    "high_impact_claims are documentation metadata flags; they are never promoted to "
    "risks_triggered and do not map to O/S/D or FRIES.",
    "Alias heading matching and phrase substring checks are heuristic and uncalibrated.",
    "coverage_ratio counts present required disclosure sections; it is not a safety "
    "quality score.",
)
