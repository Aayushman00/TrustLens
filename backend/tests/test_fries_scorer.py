"""FRIESScorer unit tests driven by frozen Phase 0 fixtures (Phase 16)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from app.scoring.fries import (
    OSDTriple,
    aspect_score,
    fries_total,
    risk_pi,
    score_from_finalized_osd,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "shared"
    / "scoring"
    / "fixtures"
    / "fries_test_vectors.json"
)
_FIXTURES = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

_DIMS = ("FAIRNESS", "ROBUSTNESS", "INTEGRITY", "EXPLAINABILITY", "SAFETY")


def _vector(case_id: int) -> dict[str, Any]:
    return next(c for c in _FIXTURES["test_cases"] if c["id"] == case_id)


def test_single_middling_risk_id1() -> None:
    case = _vector(1)
    inputs = case["inputs"]
    pi = risk_pi(inputs["O"], inputs["S"], inputs["D"])
    assert pi == pytest.approx(case["expected"]["Pi"])
    assert aspect_score([OSDTriple(5, 5, 5)]) == pytest.approx(
        case["expected"]["aspect_Ti"]
    )


def test_golden_fairness_risk_id2() -> None:
    case = _vector(2)
    inputs = case["inputs"]
    pi = risk_pi(inputs["O"], inputs["S"], inputs["D"])
    assert pi == pytest.approx(case["expected"]["Pi_exact"], abs=1e-6)
    assert round(pi, 2) == case["expected"]["Pi_paper_round"]  # ≈5.04


@pytest.mark.parametrize("case_id", [3, 4])
def test_veto_zero_component_ids3_4(case_id: int) -> None:
    case = _vector(case_id)
    inputs = case["inputs"]
    pi = risk_pi(inputs["O"], inputs["S"], inputs["D"])
    assert pi == 0.0
    assert aspect_score([OSDTriple(inputs["O"], inputs["S"], inputs["D"])]) == 0.0


def test_all_tens_optimal_id5() -> None:
    case = _vector(5)
    inputs = case["inputs"]
    assert risk_pi(inputs["O"], inputs["S"], inputs["D"]) == 10.0
    assert aspect_score([OSDTriple(10, 10, 10)]) == 10.0


def test_two_risk_average_id6() -> None:
    case = _vector(6)
    risks = [OSDTriple(r["O"], r["S"], r["D"]) for r in case["inputs"]["risks"]]
    pi1 = risk_pi(*risks[0])
    pi2 = risk_pi(*risks[1])
    assert pi1 == pytest.approx(case["expected"]["Pi1_exact"], abs=1e-6)
    assert pi2 == pytest.approx(case["expected"]["Pi2_exact"], abs=1e-6)
    assert round(pi1, 2) == case["expected"]["Pi1_paper_round"]
    assert round(pi2, 2) == case["expected"]["Pi2_paper_round"]
    # Paper pipeline rounds each Pi to 2 decimals before averaging:
    # (6.6 + 5.19) / 2 = 5.895 (the roadmap's multi-risk value), frozen to 5.89.
    assert (round(pi1, 2) + round(pi2, 2)) / 2 == pytest.approx(5.895)
    paper_mean = round((round(pi1, 2) + round(pi2, 2)) / 2, 2)
    assert paper_mean == case["expected"]["aspect_mean_paper"]
    assert aspect_score(risks) == pytest.approx((pi1 + pi2) / 2)


def test_full_table8_id7() -> None:
    case = _vector(7)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for risk in case["inputs"]["risks"]:
        grouped[risk["aspect"]].append({"O": risk["O"], "S": risk["S"], "D": risk["D"]})
    finalized_osd = {
        "aspects": [
            {"aspect": aspect, "risks": risks} for aspect, risks in grouped.items()
        ],
        "weights": case["inputs"]["weights"],
    }
    result = score_from_finalized_osd(finalized_osd)

    for aspect, paper_value in case["expected"]["aspect_scores_paper"].items():
        assert result.dimension_scores[aspect.upper()] == pytest.approx(
            paper_value, abs=0.01
        )
    assert result.fries_score == pytest.approx(
        case["expected"]["T_exact_approx"], abs=1e-3
    )
    assert result.fries_score == pytest.approx(case["expected"]["T_paper"], abs=0.02)
    assert len(result.per_risk) == len(case["inputs"]["risks"])


def test_equal_weight_sanity_id8() -> None:
    case = _vector(8)
    scores = dict(zip(_DIMS, case["inputs"]["Ti"], strict=True))
    assert fries_total(scores) == pytest.approx(case["expected"]["T"])


def test_zeroed_aspect_hidden_by_average_id9() -> None:
    case = _vector(9)
    scores = dict(zip(_DIMS, case["inputs"]["Ti"], strict=True))
    weights = dict(zip(_DIMS, case["inputs"]["wi"], strict=True))
    assert fries_total(scores, weights) == pytest.approx(case["expected"]["T"])


def test_minimum_weight_floor_id10() -> None:
    case = _vector(10)
    assert case["expected"]["valid"] is False
    scores = dict.fromkeys(_DIMS, 5.0)
    weights = {**dict.fromkeys(_DIMS, 0.25), "SAFETY": case["inputs"]["omega_S"]}
    with pytest.raises(ValueError, match="weight"):
        fries_total(scores, weights)


def test_weights_must_sum_to_one() -> None:
    scores = dict.fromkeys(_DIMS, 5.0)
    with pytest.raises(ValueError, match="sum to 1"):
        fries_total(scores, dict.fromkeys(_DIMS, 0.3))


def test_component_validation() -> None:
    with pytest.raises(ValueError):
        risk_pi(11, 5, 5)
    with pytest.raises(ValueError):
        risk_pi(-1, 5, 5)
    with pytest.raises(TypeError):
        risk_pi(True, 5, 5)  # bools rejected
    with pytest.raises(TypeError):
        risk_pi(5.0, 5, 5)  # type: ignore[arg-type]


def test_score_from_finalized_osd_single_risk_shape() -> None:
    result = score_from_finalized_osd(
        {
            "methodology_status": "PROPOSED_REQUIRES_VALIDATION",
            "aspects": [
                {"aspect": dim, "O": 4, "S": 4, "D": 8} for dim in _DIMS
            ],
        }
    )
    for dim in _DIMS:
        assert result.dimension_scores[dim] == pytest.approx(5.0397, abs=1e-4)
    assert result.fries_score == pytest.approx(5.0397, abs=1e-4)


def test_score_from_finalized_osd_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="aspects"):
        score_from_finalized_osd({"aspects": []})
    with pytest.raises(ValueError, match="missing O/S/D"):
        score_from_finalized_osd({"aspects": [{"aspect": "FAIRNESS", "O": 4, "S": 4}]})
    with pytest.raises(ValueError, match="duplicate aspect"):
        score_from_finalized_osd(
            {
                "aspects": [
                    {"aspect": "FAIRNESS", "O": 4, "S": 4, "D": 8},
                    {"aspect": "fairness", "O": 5, "S": 5, "D": 5},
                ]
            }
        )
