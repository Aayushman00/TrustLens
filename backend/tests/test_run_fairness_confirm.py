"""L5: wiring of the L4.1 confirmatory fairness run driver (frozen prereg)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db.enums import ProbeEvaluationStatus
from app.scripts import run_fairness_confirm as rc
from tests.fakes import FakeInferenceBackend


def _csv(spec: dict[str, tuple[int, int]]) -> tuple[bytes, list[int]]:
    """group -> (n, n_pos); identity_ref column carries the group."""
    lines = ["text,label,identity_ref,severe"]
    labels: list[int] = []
    for g, (n, pos) in spec.items():
        for i in range(n):
            y = int(i < pos)
            labels.append(y)
            lines.append(f"t{g}_{i},{y},{g},0")
    return ("\n".join(lines) + "\n").encode("utf-8"), labels


def _model_dir(tmp_path: Path) -> Path:
    d = tmp_path / "m"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"id2label": {"0": "LABEL_0", "1": "LABEL_1"}}), encoding="utf-8")
    return d


def test_probe_once_runs_the_production_binary_rule(tmp_path: Path) -> None:
    csv_bytes, labels = _csv({"0": (1000, 400), "1": (1000, 400)})
    # group 0: all positives caught; group 1: half the positives missed -> EOD 0.5.
    preds = list(labels[:1000]) + [1 if i < 200 else 0 for i in range(1000)]
    out = rc.probe_once(_model_dir(tmp_path), csv_bytes, backend=FakeInferenceBackend(predictions=preds))
    m = out.metric_values
    assert out.status == ProbeEvaluationStatus.EVALUATED
    assert m["sensitive_attribute"] == "identity_ref" and m["min_group_n"] == 30
    assert m["equal_opportunity_difference"] == pytest.approx(0.5)
    assert m["fairness_finding"] == "FAIRNESS_RISK" and m["risks_triggered"] == ["F-FAIR-EOPP"]
    assert m["fairness_rule"]["bootstrap"] == {"method": "percentile", "B": 1000, "seed": 42}


def _metrics(eod: float, finding: str, risks: list[str], aspect: str, lo: float = 0.1) -> dict:
    return {
        "groups": {"0": {"n": 2500, "tpr": 0.9, "fpr": 0.1, "f1": 0.8, "positive_rate": 0.2},
                   "1": {"n": 500, "tpr": 0.9 - eod, "fpr": 0.3, "f1": 0.7, "positive_rate": 0.6}},
        "eligibility": {"positives": {"0": 250, "1": 300}},
        "demographic_parity_difference": 0.4, "equal_opportunity_difference": eod,
        "eopp_ci": {"point": eod, "ci_lower": lo, "ci_upper": lo + 0.1}, "fpr_gap": 0.2,
        "subgroup_f1_spread": 0.1, "fairness_finding": finding, "risks_triggered": risks,
        "aspect_scoring": aspect, "excess_dpd_v1": 0.05, "label_rate_gap": 0.5,
        "dp_ci": {}, "methodology_version": "tl-fairness-binary-v1.2",
    }


class _Out:
    def __init__(self, m: dict, status: str = "EVALUATED") -> None:
        self.metric_values, self.status, self.status_reason, self.flags = m, status, None, []


def test_summarize_records_prereg_fields_and_majority_flag() -> None:
    risk = _metrics(0.3, "FAIRNESS_RISK", ["F-FAIR-EOPP"], "risk_detected")
    s = rc.summarize([_Out(risk), _Out(risk), _Out(_metrics(0.01, "NO_MATERIAL_DISPARITY", [], "no_material_risk"))])
    assert s["group_sizes"] == {"0": 2500, "1": 500}
    assert s["group_positive_label_rates"] == {"0": 0.1, "1": 0.6}
    for k in ("demographic_parity_difference", "equal_opportunity_difference", "eopp_ci", "fpr_gap",
              "subgroup_f1_spread", "fairness_finding", "status", "risks_triggered", "aspect_scoring"):
        assert k in s
    assert s["flags_per_run"] == [True, True, False]
    assert s["flagged"] is True
    assert s["repeatable"] is False


def _table(eods: dict[str, float], flagged: dict[str, bool], blocked: dict[str, str] | None = None) -> dict:
    blocked = blocked or {}
    return {
        n: {"equal_opportunity_difference": e, "flagged": flagged[n],
            "aspect_scoring_per_run": [blocked.get(n, "x")] * 3,
            "fairness_finding_per_run": ["INSUFFICIENT_EVIDENCE" if n in blocked else "Y"] * 3}
        for n, e in eods.items()
    }


RATES = {"clean_control": 0.0, "fairness_r020": 0.2, "fairness_r040": 0.4, "fairness_r070": 0.7, "fairness_r100": 1.0}


def test_hypotheses_all_hold() -> None:
    eods = {"clean_control": 0.01, "fairness_r020": 0.05, "fairness_r040": 0.1, "fairness_r070": 0.2,
            "fairness_r100": 0.3, "reference_toxicbert_2label": 0.0}
    flagged = {n: n in ("fairness_r040", "fairness_r070", "fairness_r100") for n in eods}
    h = rc.check_hypotheses(_table(eods, flagged), RATES)
    assert h["H1"]["holds"] and h["H2"]["holds"] and h["H3"]["holds"]
    assert h["H2"]["recall"] == 1.0
    assert h["H3"]["spearman_rho"] == pytest.approx(1.0) and h["H3"]["strictly_monotone"]
    assert h["H3"]["adjacent_decreases"] == 0
    assert h["H4"]["per_model"]["clean_control"] == {"insufficient_evidence": 0, "mapping_blocked": 0}


def test_hypotheses_fail_cases_are_reported_not_hidden() -> None:
    eods = {"clean_control": 0.2, "fairness_r020": 0.05, "fairness_r040": 0.1, "fairness_r070": 0.08,
            "fairness_r100": 0.02, "reference_toxicbert_2label": 0.0}
    flagged = {n: n in ("clean_control", "fairness_r040") for n in eods}
    h = rc.check_hypotheses(_table(eods, flagged, {"fairness_r100": "mapping_blocked"}), RATES)
    assert not h["H1"]["holds"] and h["H1"]["flagged_controls"] == ["clean_control"]
    assert not h["H2"]["holds"] and h["H2"]["recall"] == pytest.approx(1 / 3)
    assert not h["H3"]["holds"] and h["H3"]["adjacent_decreases"] == 3
    assert h["H4"]["per_model"]["fairness_r100"] == {"insufficient_evidence": 3, "mapping_blocked": 3}


def test_main_refuses_existing_analysis_dir(tmp_path: Path) -> None:
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "x.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        rc.main(["--root", str(tmp_path)])
