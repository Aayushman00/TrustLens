"""L1: evidence -> O/S/D calibration (v4 mapping, frozen anchors, held-out evaluation)."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from app.db.enums import FriesDimension
from app.osd import agent
from app.osd.agent import HeuristicOSDAgent, calibrated_level
from app.osd.base import AgentContext, ProbeSnapshot
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION
from app.scripts import run_osd_calibration as cal


def _ctx(dim: FriesDimension, m: dict) -> AgentContext:
    return AgentContext(evaluation_id=uuid.uuid4(), model_ref="m", model_metadata={},
                        probe_results=[ProbeSnapshot(dimension=dim, metric_values=m, confidence=0.9, evidence_refs=[])])


def _band(dim: FriesDimension, m: dict, mapping: str = "v4") -> tuple:
    a = next(x for x in HeuristicOSDAgent(mapping=mapping).propose(_ctx(dim, m)).aspects if x.aspect == dim)
    return a.O, a.S, a.D


# --- the mapping ---------------------------------------------------------


def test_calibrated_level_clips_and_rounds_half_up() -> None:
    assert calibrated_level(0.0, (0.1, 0.5)) == 9
    assert calibrated_level(0.9, (0.1, 0.5)) == 1
    assert calibrated_level(0.3, (0.1, 0.5)) == 5
    assert calibrated_level(0.1 + 0.5625 * 0.4, (0.1, 0.5)) == 5  # 9 - 4.5 = 4.5 -> 5, not banker's 4


def test_calibrated_level_is_monotone_non_increasing() -> None:
    levels = [calibrated_level(i / 200, (0.05, 0.6)) for i in range(201)]
    assert all(b <= a for a, b in zip(levels, levels[1:]))
    assert set(levels) == set(range(1, 10))


def test_fit_anchors_is_ols_and_rejects_no_ordering() -> None:
    assert cal.fit_anchors([(0.0, 0.1), (0.5, 0.3), (1.0, 0.5)]) == pytest.approx((0.1, 0.5))
    assert cal.fit_anchors([(0.0, 0.3), (1.0, 0.3)]) is None
    assert cal.fit_anchors([(0.0, 0.5), (1.0, 0.1)]) is None


# --- frozen parameters, versions, hashes ---------------------------------


def test_code_constants_equal_the_frozen_mapping_file() -> None:
    frozen = json.loads(cal.FROZEN_PATH.read_text(encoding="utf-8"))
    cal.check_frozen(frozen)  # raises on any difference
    evidence = cal.FROZEN_PATH.parent / "calibration_evidence.json"
    assert frozen["calibration_sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert agent.OSD_MAP_V4["calibration_sha256"] == frozen["calibration_sha256"]


def test_check_frozen_refuses_drift() -> None:
    frozen = json.loads(cal.FROZEN_PATH.read_text(encoding="utf-8"))
    fam = next(iter(frozen["anchors"]))
    frozen["anchors"][fam] = [0.0, 0.99]
    with pytest.raises(RuntimeError):
        cal.check_frozen(frozen)


def test_versions_bumped() -> None:
    assert CURRENT_METHODOLOGY_VERSION == "v8-osd-calibrated-map-2026"
    assert agent.OSD_MAP_V4["version"] == "osd-map-v4-calibrated-2026-10-03"


# --- v4 vs v3 behaviour --------------------------------------------------

_ROB = {"clean_accuracy": 0.9, "robust_accuracy": 0.8}
_FAIR = {"demographic_parity_difference": 0.1, "equalized_odds_difference": 0.2,
         "min_group_n": 30, "min_group_n_observed": 45}
_SAFE = {"severe_fnr": 0.5, "fnr_ratio": 1.0, "behavior": {"status": "EVALUATED"}}


def test_v3_baseline_is_preserved() -> None:
    assert _band(FriesDimension.ROBUSTNESS, _ROB, "v3") == (9, 1, 8)
    assert _band(FriesDimension.FAIRNESS, _FAIR, "v3") == (8, 8, 8)
    assert _band(FriesDimension.SAFETY, _SAFE, "v3") == (5, 6, 8)


@pytest.mark.parametrize(("dim", "m", "e"), [
    (FriesDimension.ROBUSTNESS, _ROB, 0.1), (FriesDimension.FAIRNESS, _FAIR, 0.2),
    (FriesDimension.SAFETY, _SAFE, 0.5)])
def test_v4_replaces_o_and_s_only_and_keeps_d(dim: FriesDimension, m: dict, e: float) -> None:
    anchors = agent.OSD_MAP_V4["anchors"].get(dim.value)
    v3 = _band(dim, m, "v3")
    if anchors is None:  # family failed calibration -> keeps v3
        assert _band(dim, m) == v3
        return
    level = calibrated_level(e, tuple(anchors))
    assert _band(dim, m) == (level, level, v3[2])


def test_v4_abstains_where_v3_abstains() -> None:
    blocked = {**_FAIR, "aspect_scoring": "mapping_blocked"}
    assert _band(FriesDimension.FAIRNESS, blocked) == (None, None, None)
    unmeasured = {"behavior": {"status": "INSUFFICIENT_EVIDENCE"}, "coverage_ratio": 0.5, "card_chars": 10}
    assert _band(FriesDimension.SAFETY, unmeasured) == (None, None, None)
    assert _band(FriesDimension.ROBUSTNESS, {"clean_accuracy": 0.9}) == (None, None, None)


def test_v4_without_behaviour_keeps_the_card_band() -> None:
    card = {"coverage_ratio": 0.5, "card_chars": 100}
    assert _band(FriesDimension.SAFETY, card) == _band(FriesDimension.SAFETY, card, "v3")
    assert _band(FriesDimension.EXPLAINABILITY, card) == _band(FriesDimension.EXPLAINABILITY, card, "v3")


def test_v4_thin_slice_lowers_o_and_s() -> None:
    if "FAIRNESS" not in agent.OSD_MAP_V4["anchors"]:
        pytest.skip("FAIRNESS calibration failed; v3 kept")
    thick = _band(FriesDimension.FAIRNESS, {**_FAIR, "equalized_odds_difference": 0.0, "demographic_parity_difference": 0.0})
    thin = _band(FriesDimension.FAIRNESS, {**_FAIR, "equalized_odds_difference": 0.0,
                                           "demographic_parity_difference": 0.0, "min_group_n_observed": 10})
    assert thin == (thick[0] - 1, thick[1] - 1, 7)


# --- split and held-out evaluation ---------------------------------------


def _row(text: str, tox: float, ident: float = 0.0, severe: float = 0.0) -> dict:
    return {"text": text, "toxicity": tox, "identity_attack": ident, "severe_toxicity": severe}


def test_calibration_split_is_disjoint_from_exclusions(tmp_path: Path) -> None:
    test_ds = [_row(f"t{i}", 0.9 if i % 3 == 0 else 0.0) for i in range(200)]
    train_ds = [_row(f"r{i}", 0.9 if i % 4 == 0 else 0.0, ident=0.5 * (i % 2), severe=0.5 * (i % 8 == 0))
                for i in range(400)] + [_row("t3", 0.9), _row("held", 0.0)]
    res = cal.prepare_calibration(test_ds, train_ds, seed=43, out=tmp_path / "c", exclude_texts={"held", "t0"},
                                  eval_size=20, train_size=60)
    data = tmp_path / "c" / "data"
    ev = {json.loads(x)["text"] for x in (data / "eval_set.jsonl").read_text(encoding="utf-8").splitlines()}
    tr = {json.loads(x)["text"] for x in (data / "clean_train.jsonl").read_text(encoding="utf-8").splitlines()}
    assert not ev & tr and not ({"held", "t0"} & (ev | tr))
    assert res["seed"] == 43 and set(res["models"]) == {"clean", "fairness_r030", "fairness_r060", "fairness_r100",
                                                        "safety_r030", "safety_r060", "safety_r100"}
    manifest = json.loads((data / "fairness_r060_data_manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 43 and manifest["flip_rate"] == 0.6


def test_family_metrics_counts_violations_ties_and_abstentions() -> None:
    fm = cal.family_metrics([0.0, 0.25, 0.5, 1.0], [8.6, None, 8.6, 5.0])
    assert fm["abstentions"] == 1 and fm["ties"] == 1 and fm["violations"] == 0
    assert fm["spearman_rho"] < 0 and fm["range"] == pytest.approx(3.6)


def test_heldout_records_map_frozen_evidence_with_both_mappings() -> None:
    m = {"severe_fnr": 0.6, "fnr_ratio": 0.9, "behavior": {"status": "EVALUATED"}}
    rec = cal.map_both("SAFETY", m)
    assert rec["v3"]["band"] == [4, 6, 8] and rec["v3"]["aspect_score"] is not None
    assert set(rec) == {"v3", "v4"} and rec["v4"]["band"][2] == 8
