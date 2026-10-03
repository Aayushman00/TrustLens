from app.db.enums import ProbeEvaluationStatus
from app.probes.safety_behavior import evaluate_behavior


def test_misses_half_of_severe():
    y_true = [1] * 40 + [1] * 60 + [0] * 100
    severe = [1] * 40 + [0] * 160
    y_pred = [0] * 20 + [1] * 20 + [1] * 60 + [0] * 100  # misses 20 of 40 severe
    r = evaluate_behavior(y_true, y_pred, severe)
    assert r.status == ProbeEvaluationStatus.EVALUATED
    assert r.severe_n == 40 and abs(r.severe_fnr - 0.5) < 1e-9
    assert r.severe_fnr_ci[0] < 0.5 < r.severe_fnr_ci[1]
    assert abs(r.overall_fnr - 20 / 100) < 1e-9 and abs(r.fnr_ratio - 2.5) < 1e-9


def test_too_few_severe_rows_is_insufficient():
    r = evaluate_behavior([1, 0, 1], [1, 0, 1], [1, 0, 0])
    assert r.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE and r.severe_fnr is None


def test_zero_severe_rows_does_not_divide_by_zero():
    r = evaluate_behavior([1, 0] * 50, [1, 0] * 50, [0] * 100)
    assert r.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE


def test_no_positives_overall_is_insufficient():
    r = evaluate_behavior([0] * 100, [0] * 100, [1] * 50 + [0] * 50)
    assert r.status == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE


def test_benign_false_positive_rate_reported():
    y_true = [1] * 40 + [0] * 100
    severe = [1] * 40 + [0] * 100
    y_pred = [1] * 40 + [1] * 10 + [0] * 90
    r = evaluate_behavior(y_true, y_pred, severe)
    assert abs(r.benign_fpr - 0.10) < 1e-9 and r.harmful_recall == 1.0
