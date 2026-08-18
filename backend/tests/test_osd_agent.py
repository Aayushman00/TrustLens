"""HeuristicOSDAgent unit tests (Phase 16) — pure, no DB/S3."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.enums import FriesDimension
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import METHODOLOGY_STATUS, AgentContext, ProbeSnapshot
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

    assert result.methodology_status == METHODOLOGY_STATUS
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


def test_skipped_probes_score_below_complete_integrity() -> None:
    ctx = AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=[
            _snap(FriesDimension.FAIRNESS, {"demographic_parity_difference": None}, 0.5),
            _snap(FriesDimension.ROBUSTNESS, {"clean_accuracy": None}, 0.56),
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
        assert (skipped.O, skipped.S, skipped.D) == (4, 4, 3)
        assert sum((skipped.O, skipped.S, skipped.D)) < sum(
            (integrity.O, integrity.S, integrity.D)
        )
    for dim in (FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY):
        empty = by_aspect[dim]
        assert (empty.O, empty.S, empty.D) == (2, 2, 3)


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


def test_missing_probe_rows_get_conservative_defaults() -> None:
    ctx = AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=[],
    )
    result = HeuristicOSDAgent().propose(ctx)
    assert len(result.aspects) == 5
    for aspect in result.aspects:
        assert (aspect.O, aspect.S, aspect.D) == (3, 3, 3)
        assert aspect.confidence == 0.2
        assert "PROPOSED" in aspect.rationale


def test_serialization_shapes() -> None:
    result = HeuristicOSDAgent().propose(_full_context())

    suggestion = to_ai_suggestion(result)
    assert suggestion["methodology_status"] == "PROPOSED_REQUIRES_VALIDATION"
    assert suggestion["schema_version"] == "osd-agent-v1"
    assert len(suggestion["aspects"]) == 5
    assert {a["aspect"] for a in suggestion["aspects"]} == {
        d.value for d in FriesDimension
    }
    assert "not ground truth" in suggestion["note"]

    rationale = to_rationale(result)
    assert "PROPOSED / REQUIRES VALIDATION" in rationale

    evidence = to_evidence_used(result)
    assert len(evidence) == 5
    assert all("aspect" in ref and "evidence_id" in ref for ref in evidence)

    finalized = to_finalized_osd(result)
    assert finalized["methodology_status"] == "PROPOSED_REQUIRES_VALIDATION"
    assert finalized["source"] == "osd_agent_autonomous"
    # Phase 17: mode disclosure persists with the finalized document.
    assert finalized["human_reviewed"] is False
    assert finalized["evaluation_mode"] == "AI_AUTONOMOUS"
    assert "not human-reviewed" in finalized["disclaimer"]
    fries = score_from_finalized_osd(finalized)
    assert 0.0 < fries.fries_score <= 10.0
    assert set(fries.dimension_scores) == {d.value for d in FriesDimension}
