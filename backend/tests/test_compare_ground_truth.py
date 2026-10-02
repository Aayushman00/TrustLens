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


def _ev(status_by_dim, scores, metrics=None):
    return {
        "status": "FINALIZED",
        "final_score": {"fries_score": 5.0, "dimension_scores": scores},
        "probes": [{"dimension": d, "status": s, "metric_values": (metrics or {}).get(d, {})} for d, s in status_by_dim.items()],
    }


def test_evidence_abstains_on_insufficient_probe_and_controls_are_excluded(tmp_path):
    import json

    from app.scripts.compare_ground_truth import analyze

    dims = ["FAIRNESS", "ROBUSTNESS", "INTEGRITY", "EXPLAINABILITY", "SAFETY"]
    ok = {d: "EVALUATED" for d in dims}
    risky = {d: {"risks_triggered": ["R"]} for d in dims}
    raw = tmp_path / "run" / "raw"
    raw.mkdir(parents=True)
    (raw / "reference_toxicbert_2label__run1.json").write_text(json.dumps(_ev(ok, {d: 8.0 for d in dims}, risky)))
    calm = {d: {"aspect_scoring": "no_material_risk"} for d in dims}
    m = _ev({**ok, "FAIRNESS": "INSUFFICIENT_EVIDENCE"}, {d: 8.0 for d in dims if d != "FAIRNESS"}, calm)
    (raw / "v__run1.json").write_text(json.dumps(m))
    truth = {"models": {"reference_toxicbert_2label": {"injected_defects": []}, "v": {"injected_defects": ["FAIRNESS"]}},
             "detection_rules": {}, "severity_levels": "", "controls": ["reference_toxicbert_2label"]}
    a = analyze([tmp_path / "run"], truth)
    assert a["models"]["v"]["dimensions"]["FAIRNESS"]["evidence_state"] == "ABSTAINED"
    ev = a["evidence_level"]
    assert ev["abstained"] == 1 and ev["tp"] + ev["fn"] == 0  # abstention is neither hit nor miss
    assert ev["fp"] == 0  # control's own risk flags are not counted as false positives
    assert a["control_flag_rate"]["INTEGRITY"] == 1.0
    assert "precision" not in a["per_dimension_detection"]["FAIRNESS"]["evidence"]
