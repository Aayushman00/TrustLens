"""Report-vs-artifact consistency checks (audit 2026-10-23).

These catch drift between the thesis source and the frozen result folders / code. They check that
numbers *agree*, not that the science is valid. Skipped when report/ or results/ are absent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.osd.agent import OSD_MAP_V4
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION

ROOT = Path(__file__).resolve().parents[2]
CH = ROOT / "report" / "chapters"
RES = ROOT / "results"
pytestmark = pytest.mark.skipif(not (CH.is_dir() and RES.is_dir()), reason="report/results not present")


def _tex(name: str) -> str:
    return (CH / name).read_text(encoding="utf-8")


def _json(*parts: str):
    return json.loads(RES.joinpath(*parts).read_text(encoding="utf-8"))


def test_current_methodology_version_is_listed_in_reproduction_guide() -> None:
    assert CURRENT_METHODOLOGY_VERSION in (ROOT / "docs" / "REPRODUCING_THESIS_RESULTS.md").read_text(encoding="utf-8")


def test_v4_anchors_match_frozen_file_and_report_table() -> None:
    frozen = _json("osd_calibration_20261003", "calibration", "frozen_mapping.json")
    assert frozen["calibration_sha256"] == OSD_MAP_V4["calibration_sha256"]
    ch4 = _tex("ch4_fries.tex")
    for dim, (a, b) in OSD_MAP_V4["anchors"].items():
        assert tuple(frozen["anchors"][dim]) == (a, b)
        assert f"{a:.6f}" in ch4 and f"{b:.6f}" in ch4, dim


def test_l2_headline_numbers_match_analysis_files() -> None:
    ch7 = _tex("ch7_results.tex")
    official = _json("l2_det_vs_llm_20261003", "analysis.json")["summary"]
    assert (official["llm_answered_pairs"], official["exact_status_agreement"]) == (18, 0.2778)
    assert "11/36 (0.306)" in ch7
    pooled = _json("l2_det_vs_llm_20261022_r4", "analysis.json")["summary"]
    assert pooled["exact_status_agreement"] == 0.3056
    assert pooled["llm_runs"] == 60 and pooled["llm_fallbacks"] == 0

def test_fairness_confirmation_h1_failure_is_reported_as_failure() -> None:
    hyp = _json("fairness_confirm_20261003", "analysis", "analysis.json")
    h = hyp.get("hypotheses", hyp)
    assert h["H1"]["holds"] is False and h["H2"]["holds"] is True
    assert re.search(r"no control would be flagged \\textbf\{failed\}", _tex("ch7_results.tex"))


def test_human_study_counts() -> None:
    agree = _json("l10_human_analysis_20261005", "agreement.json")
    assert set(agree) >= {"all7", "R0_only"}
    ch7 = _tex("ch7_results.tex")
    assert "seven submissions" in ch7 and "six share the code R0" in ch7
