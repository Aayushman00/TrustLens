"""DeterministicOSDMapper tests — consumer-only, no metric recompute."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.osd.base import METHODOLOGY_STATUS_DETERMINISTIC, AgentContext, ProbeSnapshot
from app.osd.deterministic import DeterministicOSDMapper
from app.osd.serialize import osd_triple_complete, to_ai_suggestion
from app.probes.fairness_stats import SCORED_RISK_ID as FAIR_SCORED_RISK_ID
from app.probes.robustness_stats import SCORED_RISK_ID as ROB_SCORED_RISK_ID

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


def _ctx(probe_results: list[ProbeSnapshot]) -> AgentContext:
    return AgentContext(
        evaluation_id=uuid.uuid4(),
        model_ref="org/model",
        model_metadata={},
        probe_results=probe_results,
    )


def test_mapper_abstains_o_s_d_for_all_aspects() -> None:
    result = DeterministicOSDMapper().propose(
        _ctx(
            [
                _snap(
                    FriesDimension.FAIRNESS,
                    {
                        "demographic_parity_difference": 0.2,
                        "aspect_scoring": "scored_risk",
                        "scored_risk_id": FAIR_SCORED_RISK_ID,
                        "probe_status": ProbeEvaluationStatus.EVALUATED.value,
                    },
                ),
                _snap(
                    FriesDimension.ROBUSTNESS,
                    {"clean_accuracy": 0.9, "robust_accuracy": 0.8},
                ),
                _snap(
                    FriesDimension.INTEGRITY,
                    {"pass_count": 5, "fail_count": 1},
                ),
                _snap(
                    FriesDimension.EXPLAINABILITY,
                    {"coverage_ratio": 0.8, "card_chars": 100},
                ),
                _snap(
                    FriesDimension.SAFETY,
                    {"coverage_ratio": 0.7, "card_chars": 100},
                ),
            ]
        )
    )
    assert result.methodology_status == METHODOLOGY_STATUS_DETERMINISTIC
    assert result.assessment_engine == "deterministic"
    assert len(result.aspects) == 5
    for aspect in result.aspects:
        assert aspect.O is None
        assert aspect.S is None
        assert aspect.D is None
        assert aspect.O_source == "unavailable"
        assert aspect.D_source == "unavailable"
        assert aspect.S_source is None
        assert not osd_triple_complete(aspect)


def test_f_fair_perf_visible_with_o_null() -> None:
    fairness_metrics = {
        "aspect_scoring": "scored_risk",
        "scored_risk_id": FAIR_SCORED_RISK_ID,
        "gap": 0.12,
        "gap_ci_lower": 0.08,
        "gap_ci_upper": 0.16,
        "probe_status": ProbeEvaluationStatus.EVALUATED.value,
    }
    result = DeterministicOSDMapper().propose(
        _ctx([_snap(FriesDimension.FAIRNESS, fairness_metrics)])
    )
    fairness = result.aspects[0]
    assert fairness.O is None
    assert fairness.osd_metadata["scored_risk_id"] == FAIR_SCORED_RISK_ID
    assert fairness.osd_metadata["aspect_scoring"] == "scored_risk"
    assert FAIR_SCORED_RISK_ID in fairness.rationale
    suggestion = to_ai_suggestion(result)
    assert suggestion["scoring_withheld"] is True
    assert suggestion["complete_aspect_count"] == 0


def test_r_rob_pert_visible_with_o_null() -> None:
    robustness_metrics = {
        "aspect_scoring": "scored_risk",
        "scored_risk_id": ROB_SCORED_RISK_ID,
        "risks_triggered": [ROB_SCORED_RISK_ID],
        "accuracy_drop": 0.12,
        "drop_ci_lower": 0.07,
        "drop_ci_upper": 0.17,
        "clean_accuracy": 0.9,
        "robust_accuracy": 0.78,
        "probe_status": ProbeEvaluationStatus.EVALUATED.value,
    }
    result = DeterministicOSDMapper().propose(
        _ctx([_snap(FriesDimension.ROBUSTNESS, robustness_metrics)])
    )
    robustness = next(a for a in result.aspects if a.aspect == FriesDimension.ROBUSTNESS)
    assert robustness.O is None
    assert robustness.S is None
    assert robustness.D is None
    assert robustness.osd_metadata["scored_risk_id"] == ROB_SCORED_RISK_ID
    assert ROB_SCORED_RISK_ID in robustness.rationale
    assert robustness.osd_metadata["accuracy_drop"] == 0.12
    suggestion = to_ai_suggestion(result)
    assert suggestion["scoring_withheld"] is True


def test_mapper_preserves_mapping_blocked_without_o() -> None:
    metrics = {
        "aspect_scoring": "mapping_blocked",
        "failed_gates": ["G-FAIR-CI-WIDE"],
        "probe_status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
    }
    result = DeterministicOSDMapper().propose(
        _ctx([_snap(FriesDimension.FAIRNESS, metrics)])
    )
    aspect = result.aspects[0]
    assert aspect.O is None
    assert aspect.osd_metadata["aspect_scoring"] == "mapping_blocked"
    assert aspect.osd_metadata["failed_gates"] == ["G-FAIR-CI-WIDE"]


def test_mapper_does_not_recompute_gap_or_trigger() -> None:
    """Probe gap/trigger fields are copied verbatim; mapper does not derive O."""
    metrics = {
        "aspect_scoring": "scored_risk",
        "scored_risk_id": FAIR_SCORED_RISK_ID,
        "gap": 0.25,
        "demographic_parity_difference": 0.99,
    }
    result = DeterministicOSDMapper().propose(
        _ctx([_snap(FriesDimension.FAIRNESS, metrics)])
    )
    aspect = result.aspects[0]
    assert aspect.osd_metadata["gap"] == 0.25
    assert aspect.osd_metadata["demographic_parity_difference"] == 0.99
    assert aspect.O is None


def test_mapper_copies_integrity_risk_metadata() -> None:
    integrity_metrics = {
        "aspect_scoring": "scored_risk",
        "scored_risk_id": None,
        "risks_triggered": ["I-INT-LICENSE-UNDISCLOSED"],
        "probe_status": ProbeEvaluationStatus.EVALUATED.value,
        "methodology_version": "tl-integrity-v1.0",
        "identity": {
            "hash_comparison": "not_performed",
            "files_listing_fingerprint": "sha256:abc",
            "sha_like": True,
        },
        "claim_boundary": {"cryptographic_identity": "unverified"},
        "reliability": {"failed_gates": ["I-INT-HASH-UNVERIFIED"]},
    }
    result = DeterministicOSDMapper().propose(
        _ctx([_snap(FriesDimension.INTEGRITY, integrity_metrics)])
    )
    integrity = next(a for a in result.aspects if a.aspect == FriesDimension.INTEGRITY)
    assert integrity.O is None
    assert integrity.S is None
    assert integrity.D is None
    assert integrity.osd_metadata["risks_triggered"] == ["I-INT-LICENSE-UNDISCLOSED"]
    assert integrity.osd_metadata["identity"]["hash_comparison"] == "not_performed"
    assert result.assessment_engine == "deterministic"


def test_human_s_merge_withheld_fries() -> None:
    from app.osd.review import merge_review_aspects, to_finalized_osd_assisted

    suggestion = to_ai_suggestion(
        DeterministicOSDMapper().propose(
            _ctx([_snap(FriesDimension.FAIRNESS, {"aspect_scoring": "no_material_risk"})])
        )
    )
    approved, human_changed = merge_review_aspects(
        suggestion,
        [{"aspect": "FAIRNESS", "S": 7}],
        accept_all=False,
    )
    assert human_changed is True
    assert approved == [{"aspect": "FAIRNESS", "O": None, "S": 7, "D": None}]
    finalized = to_finalized_osd_assisted(
        approved,
        human_review_id=1,
        human_changed=human_changed,
        agent_suggestion=suggestion,
    )
    assert finalized["scoring_withheld"] is True
    assert finalized["complete_aspect_count"] == 0


def test_deterministic_accepts_human_o_and_d() -> None:
    """O and D are independently human-enterable, same as S — the agent itself
    still never proposes any of the three (it always abstains)."""
    from app.osd.review import merge_review_aspects

    suggestion = {
        "assessment_engine": "deterministic",
        "methodology_status": METHODOLOGY_STATUS_DETERMINISTIC,
        "aspects": [
            {"aspect": name.value, "O": None, "S": None, "D": None}
            for name in FriesDimension
        ],
    }
    approved_o, changed_o = merge_review_aspects(
        suggestion, [{"aspect": "FAIRNESS", "O": 5, "S": 7}], accept_all=False
    )
    assert changed_o is True
    assert approved_o == [{"aspect": "FAIRNESS", "O": 5, "S": 7, "D": None}]

    approved_d, changed_d = merge_review_aspects(
        suggestion, [{"aspect": "FAIRNESS", "S": 7, "D": 5}], accept_all=False
    )
    assert changed_d is True
    assert approved_d == [{"aspect": "FAIRNESS", "O": None, "S": 7, "D": 5}]


def test_deterministic_accept_all_no_fabricated_triples() -> None:
    from app.osd.review import merge_review_aspects

    suggestion = {
        "assessment_engine": "deterministic",
        "methodology_status": METHODOLOGY_STATUS_DETERMINISTIC,
        "aspects": [
            {"aspect": name.value, "O": None, "S": None, "D": None}
            for name in FriesDimension
        ],
    }
    approved, human_changed = merge_review_aspects(suggestion, None, accept_all=True)
    assert approved == []
    assert human_changed is False
