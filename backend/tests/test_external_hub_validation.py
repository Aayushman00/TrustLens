"""External Hub validation: selection is pinned to full SHAs; profiles are descriptive copies of the evaluation."""

import re

from app.scripts import run_external_hub_validation as ext


def test_selection_is_pinned_to_full_commit_shas() -> None:
    assert 5 <= len(ext.SELECTION) <= 8
    assert len({repo for repo, _, _ in ext.SELECTION}) == len(ext.SELECTION)
    for _repo, sha, why in ext.SELECTION:
        assert re.fullmatch(r"[0-9a-f]{40}", sha)
        assert why


def test_profile_copies_reported_values_without_ranking() -> None:
    ev = {
        "status": "FINALIZED", "model_revision": "a" * 40,
        "probes": [{"dimension": "ROBUSTNESS", "status": "EVALUATED",
                    "metric_values": {"aspect_scoring": "scored_risk", "risks_triggered": ["R-ROB-PERT"],
                                      "accuracy_drop": 0.07, "reliability": {"failed_gates": []}}}],
        "osd_agent": {"ai_suggestion": None},  # null suggestion must not crash
        "final_score": {"fries_score": 3.2}, "mode_disclosure": {"fries_status": "scored"},
    }
    p = ext.profile_one(ev)
    rob = p["dimensions"]["ROBUSTNESS"]
    assert rob["risks_triggered"] == ["R-ROB-PERT"] and rob["accuracy_drop"] == 0.07
    assert p["fries_score_as_reported"] == 3.2
    assert "rank" not in str(p).lower()
