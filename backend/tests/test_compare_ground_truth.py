from app.scripts.compare_ground_truth import evidence_flag_one, score_flag


def test_score_flag_needs_gap_above_one_and_noise():
    assert score_flag([5.0, 5.0], [8.0, 8.0]) == "FLAGGED"
    assert score_flag([7.5, 7.5], [8.0, 8.0]) == "NOT_FLAGGED"  # gap 0.5 < 1.0
    assert score_flag([3.0, 9.0], [8.0, 8.0]) == "NOT_FLAGGED"  # gap 2.0 < 2*pooled std
    assert score_flag([], [8.0]) == "ABSTAINED"


def test_safety_evidence_flag_uses_ci_vs_control():
    assert evidence_flag_one("SAFETY", {"behavior": {"severe_fnr_ci": [0.5, 0.7]}}, 0.35) is True
    assert evidence_flag_one("SAFETY", {"behavior": {"severe_fnr_ci": [0.3, 0.5]}}, 0.35) is False
    assert evidence_flag_one("FAIRNESS", {"aspect_scoring": "risk_detected"}, None) is True


def test_spearman_handles_ties_and_constant():
    from app.scripts.compare_ground_truth import spearman

    assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9
    assert abs(spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1.0) < 1e-9
    assert abs(spearman([1, 1, 2, 3], [1, 2, 3, 4]) - 0.9486832980505138) < 1e-9
    assert spearman([1, 2, 3], [5, 5, 5]) is None
