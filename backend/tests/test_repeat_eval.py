import math

from app.scripts.repeat_eval import summarize_runs


def _run(f, **dims):
    return {"status": "FINALIZED", "fries_score": f, "dimension_scores": dims}


def test_mean_and_sample_std():
    s = summarize_runs([_run(4.0, SAFETY=2.0), _run(6.0, SAFETY=4.0)])
    assert s["n_ok"] == 2 and s["n_failed"] == 0
    assert s["fries"]["mean"] == 5.0
    assert math.isclose(s["fries"]["std"], math.sqrt(2.0))
    assert s["dimensions"]["SAFETY"]["min"] == 2.0


def test_failed_runs_are_counted_and_excluded():
    s = summarize_runs([_run(5.0, SAFETY=1.0), {"status": "FAILED", "fries_score": None, "dimension_scores": {}}])
    assert s["n_total"] == 2 and s["n_ok"] == 1 and s["n_failed"] == 1
    assert s["fries"]["std"] == 0.0


def test_all_failed_returns_none_stats():
    s = summarize_runs([{"status": "FAILED", "fries_score": None, "dimension_scores": {}}])
    assert s["n_ok"] == 0 and s["fries"]["mean"] is None
