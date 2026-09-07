"""HeuristicOSDAgent unit tests (Phase 16) — pure, no DB/S3."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import LEGACY_HEURISTIC_METHODOLOGY_STATUS, AgentContext, ProbeSnapshot
from app.osd.serialize import (
    to_ai_suggestion,
    to_evidence_used,
    to_finalized_osd,
    to_rationale,
)
from app.scoring.fries import score_from_finalized_osd

_REF = {"evidence_id": "e1", "uri": "s3://trustlens/evidence/x.json"}


def _snap(
    dimension: FriesDimension,
    metric_values: dict[str, Any],
    confidence: float | None = 0.8,
) -> ProbeSnapshot:
    return ProbeSnapshot(
        dimension=dimension,
        metric_values=metric_values,
        confidence=confidence,
        evidence_refs=[{**_REF, "probe_name": dimension.value.lower()}],
    )


def _full_context() -> AgentContext:
    return AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=[
            _snap(
                FriesDimension.FAIRNESS,
                {
                    "demographic_parity_difference": 0.08,
                    "equalized_odds_difference": 0.05,
                    "min_group_n": 30,
                    "min_group_n_observed": 45,
                },
                0.85,
            ),
            _snap(
                FriesDimension.ROBUSTNESS,
                {
                    "clean_accuracy": 0.9,
                    "robust_accuracy": 0.8,
                    "degradation_ratio": 0.889,
                },
                0.9,
            ),
            _snap(
                FriesDimension.INTEGRITY,
                {
                    "checks": {n: {"pass": True} for n in "abcdef"},
                    "pass_count": 6,
                    "fail_count": 0,
                },
                1.0,
            ),
            _snap(
                FriesDimension.EXPLAINABILITY,
                {"coverage_ratio": 0.8, "card_chars": 3000},
                0.9,
            ),
            _snap(
                FriesDimension.SAFETY,
                {"coverage_ratio": 0.75, "card_chars": 3000, "high_impact_claims": []},
                0.7,
            ),
        ],
    )


def test_output_shape_and_labeling() -> None:
    result = HeuristicOSDAgent().propose(_full_context())

    assert result.methodology_status == LEGACY_HEURISTIC_METHODOLOGY_STATUS
    assert result.model_ref == "org/model"
    assert [a.aspect for a in result.aspects] == list(FriesDimension)
    for aspect in result.aspects:
        assert isinstance(aspect.O, int) and 0 <= aspect.O <= 10
        assert isinstance(aspect.S, int) and 0 <= aspect.S <= 10
        assert isinstance(aspect.D, int) and 0 <= aspect.D <= 10
        assert "PROPOSED" in aspect.rationale
        assert "REQUIRES VALIDATION" in aspect.rationale
        assert 0.0 <= aspect.confidence <= 1.0
        assert aspect.evidence_refs
    expected_overall = round(
        sum(a.confidence for a in result.aspects) / len(result.aspects), 4
    )
    assert result.overall_confidence == expected_overall


def test_heuristic_bands_never_propose_veto_or_optimal() -> None:
    result = HeuristicOSDAgent().propose(_full_context())
    for aspect in result.aspects:
        assert 1 <= aspect.O <= 9
        assert 1 <= aspect.S <= 9
        assert 1 <= aspect.D <= 9


def test_skipped_probes_abstain_from_osd() -> None:
    ctx = AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=[
            _snap(
                FriesDimension.FAIRNESS,
                {
                    "demographic_parity_difference": None,
                    "probe_status": "SKIPPED",
                },
                0.5,
            ),
            _snap(
                FriesDimension.ROBUSTNESS,
                {
                    "clean_accuracy": None,
                    "probe_status": "NOT_APPLICABLE",
                },
                0.56,
            ),
            _snap(
                FriesDimension.INTEGRITY,
                {
                    "checks": {n: {"pass": True} for n in "abcdef"},
                    "pass_count": 6,
                    "fail_count": 0,
                },
                1.0,
            ),
            _snap(FriesDimension.EXPLAINABILITY, {"coverage_ratio": 0.0, "card_chars": 0}, 0.3),
            _snap(FriesDimension.SAFETY, {"coverage_ratio": 0.0, "card_chars": 0}, 0.3),
        ],
    )
    result = HeuristicOSDAgent().propose(ctx)
    by_aspect = {a.aspect: a for a in result.aspects}

    integrity = by_aspect[FriesDimension.INTEGRITY]
    assert (integrity.O, integrity.S, integrity.D) == (9, 9, 8)
    for dim in (FriesDimension.FAIRNESS, FriesDimension.ROBUSTNESS):
        skipped = by_aspect[dim]
        assert skipped.O is None and skipped.S is None and skipped.D is None
        assert "abstained because evidence is unavailable" in skipped.rationale
    assert by_aspect[FriesDimension.FAIRNESS].status.value == "SKIPPED"
    assert by_aspect[FriesDimension.ROBUSTNESS].status.value == "NOT_APPLICABLE"
    for dim in (FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY):
        empty = by_aspect[dim]
        assert (empty.O, empty.S, empty.D) == (2, 2, 3)

    suggestion = to_ai_suggestion(result)
    assert suggestion["scoring_withheld"] is True
    assert suggestion["scoring_complete"] is False
    assert suggestion["complete_aspect_count"] == 3
    fairness_payload = next(a for a in suggestion["aspects"] if a["aspect"] == "FAIRNESS")
    assert fairness_payload["O"] is None
    assert fairness_payload["status"] == "SKIPPED"

    finalized = to_finalized_osd(result)
    assert finalized["scoring_withheld"] is True
    assert {a["aspect"] for a in finalized["aspects"]} == {
        "INTEGRITY",
        "EXPLAINABILITY",
        "SAFETY",
    }
    assert all(a["O"] is not None for a in finalized["aspects"])


def test_fairness_proxy_abstains_osd_even_with_metrics() -> None:
    ctx = AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=[
            _snap(
                FriesDimension.FAIRNESS,
                {
                    "demographic_parity_difference": 0.08,
                    "equalized_odds_difference": 0.05,
                    "min_group_n": 30,
                    "min_group_n_observed": 45,
                    "probe_status": ProbeEvaluationStatus.PROXY.value,
                    "fairness_mode": "proxy_lr",
                },
                0.85,
            ),
            _snap(
                FriesDimension.INTEGRITY,
                {
                    "checks": {n: {"pass": True} for n in "abcdef"},
                    "pass_count": 6,
                    "fail_count": 0,
                },
                1.0,
            ),
        ],
    )
    result = HeuristicOSDAgent().propose(ctx)
    fairness = next(a for a in result.aspects if a.aspect == FriesDimension.FAIRNESS)
    assert fairness.O is None and fairness.S is None and fairness.D is None
    assert fairness.status is ProbeEvaluationStatus.SKIPPED
    assert "fairness status is PROXY" in fairness.rationale


def test_safety_high_impact_with_gaps_lowers_severity_and_detection() -> None:
    ctx = AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=[
            _snap(
                FriesDimension.SAFETY,
                {
                    "coverage_ratio": 0.75,
                    "card_chars": 900,
                    "high_impact_claims": ["healthcare"],
                },
                0.6,
            ),
        ],
    )
    result = HeuristicOSDAgent().propose(ctx)
    safety = next(a for a in result.aspects if a.aspect == FriesDimension.SAFETY)
    assert safety.O == 8  # scale(0.75)
    assert safety.S == 6  # -2 for high-impact gaps
    assert safety.D == 7  # -1 for high-impact gaps


def test_missing_coverage_ratio_abstains_without_fake_band() -> None:
    ctx = AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=[
            _snap(FriesDimension.EXPLAINABILITY, {"card_chars": 900}, 0.4),
            _snap(FriesDimension.SAFETY, {"card_chars": 900}, 0.4),
        ],
    )
    result = HeuristicOSDAgent().propose(ctx)
    by_aspect = {a.aspect: a for a in result.aspects}
    for dim in (FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY):
        aspect = by_aspect[dim]
        assert aspect.O is None and aspect.S is None and aspect.D is None
        assert "abstained because evidence is unavailable" in aspect.rationale
    finalized = to_finalized_osd(result)
    assert finalized["aspects"] == []


def test_missing_probe_rows_abstain_from_osd() -> None:
    ctx = AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=[],
    )
    result = HeuristicOSDAgent().propose(ctx)
    assert len(result.aspects) == 5
    for aspect in result.aspects:
        assert aspect.O is None and aspect.S is None and aspect.D is None
        assert "abstained because evidence is unavailable" in aspect.rationale
        assert aspect.status.value == "INSUFFICIENT_EVIDENCE"

    finalized = to_finalized_osd(result)
    assert finalized["aspects"] == []
    assert finalized["scoring_withheld"] is True
    assert finalized["complete_aspect_count"] == 0


def test_serialization_shapes() -> None:
    result = HeuristicOSDAgent().propose(_full_context())

    suggestion = to_ai_suggestion(result)
    assert suggestion["methodology_status"] == LEGACY_HEURISTIC_METHODOLOGY_STATUS
    assert suggestion["assessment_engine"] == "legacy_heuristic"
    assert suggestion["schema_version"] == "osd-agent-v1"
    assert len(suggestion["aspects"]) == 5
    assert {a["aspect"] for a in suggestion["aspects"]} == {
        d.value for d in FriesDimension
    }
    assert suggestion["scoring_complete"] is True
    assert suggestion["scoring_withheld"] is False
    assert all(a["status"] == "EVALUATED" for a in suggestion["aspects"])
    assert all(isinstance(a["O"], int) for a in suggestion["aspects"])

    rationale = to_rationale(result)
    assert "LEGACY HEURISTIC" in rationale

    evidence = to_evidence_used(result)
    assert len(evidence) == 5
    assert all("aspect" in ref and "evidence_id" in ref for ref in evidence)

    finalized = to_finalized_osd(result)
    assert finalized["methodology_status"] == LEGACY_HEURISTIC_METHODOLOGY_STATUS
    assert finalized["source"] == "osd_agent_autonomous"
    # Phase 17: mode disclosure persists with the finalized document.
    assert finalized["human_reviewed"] is False
    assert finalized["evaluation_mode"] == "AI_AUTONOMOUS"
    assert "not human-reviewed" in finalized["disclaimer"]
    fries = score_from_finalized_osd(finalized)
    assert 0.0 < fries.fries_score <= 10.0
    assert set(fries.dimension_scores) == {d.value for d in FriesDimension}
    assert finalized["scoring_complete"] is True
    assert len(finalized["aspects"]) == 5
