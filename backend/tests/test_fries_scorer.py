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


# --- audit 2026-10-23: edge cases beyond the frozen fixtures -------------------------------


def _doc(per_dim: dict[str, list[tuple[int, int, int]]], weights: dict[str, float] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "aspects": [
            {"aspect": d, "risks": [{"O": o, "S": s, "D": dd} for o, s, dd in rs]} for d, rs in per_dim.items()
        ]
    }
    if weights:
        doc["weights"] = weights
    return doc


def test_partial_dimension_set_is_rejected_not_reweighted() -> None:
    # fries_total alone would give 4 aspects weight 0.25 each; the document scorer must refuse.
    four = {d: [(5, 5, 5)] for d in _DIMS[:4]}
    with pytest.raises(ValueError, match="must cover exactly"):
        score_from_finalized_osd(_doc(four))


def test_empty_risk_list_is_an_error_not_a_zero() -> None:
    doc = _doc({d: [(5, 5, 5)] for d in _DIMS})
    doc["aspects"][0]["risks"] = []
    with pytest.raises(ValueError, match="non-empty"):
        score_from_finalized_osd(doc)


def test_vetoed_risk_drags_the_dimension_mean_but_is_not_a_missing_value() -> None:
    # (0,9,9) -> Pi 0 ; (9,9,9) -> Pi 9 ; mean 4.5. A veto is a numerical zero inside the mean.
    doc = _doc({**{d: [(5, 5, 5)] for d in _DIMS}, "SAFETY": [(0, 9, 9), (9, 9, 9)]})
    result = score_from_finalized_osd(doc)
    assert result.dimension_scores["SAFETY"] == pytest.approx(4.5)
    assert result.fries_score == pytest.approx(0.2 * (4 * 5.0 + 4.5), abs=1e-4)


def test_multi_risk_custom_weights_and_rounding_are_stable() -> None:
    w = {"FAIRNESS": 0.1, "ROBUSTNESS": 0.2, "INTEGRITY": 0.3, "EXPLAINABILITY": 0.15, "SAFETY": 0.25}
    doc = _doc({d: [(4, 4, 8), (7, 4, 5)] for d in _DIMS}, w)
    r = score_from_finalized_osd(doc)
    expected = (4 * 4 * 8) ** (1 / 3) / 2 + (7 * 4 * 5) ** (1 / 3) / 2
    assert r.fries_score == pytest.approx(expected, abs=1e-4)  # weights sum to 1 -> same for any split
    assert r.fries_score == round(r.fries_score, 4)
    assert all(v == round(v, 4) for v in r.dimension_scores.values())


def test_dimension_order_and_case_do_not_change_the_score() -> None:
    base = {d: [(3, 6, 9)] for d in _DIMS}
    a = score_from_finalized_osd(_doc(base))
    shuffled = {d.lower(): base[d] for d in reversed(_DIMS)}
    assert score_from_finalized_osd(_doc(shuffled)).fries_score == a.fries_score


@pytest.mark.parametrize("bad", [-1, 11, 4.0, True, None, "5"])
def test_invalid_components_raise(bad: Any) -> None:
    doc = _doc({d: [(5, 5, 5)] for d in _DIMS})
    doc["aspects"][1]["risks"][0]["D"] = bad
    with pytest.raises((TypeError, ValueError)):
        score_from_finalized_osd(doc)
