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


def test_current_methodology_version_is_listed_in_report_table() -> None:
    assert CURRENT_METHODOLOGY_VERSION.replace("_", r"\_") in _tex("ch4_fries.tex")


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
    assert "5/18 (0.278)" in ch7
    pooled = _json("l2_det_vs_llm_20261022_r4", "analysis.json")["summary"]
    assert pooled["exact_status_agreement"] == 0.3056 and "0.306" in ch7
    assert pooled["llm_runs"] == 60 and pooled["llm_fallbacks"] == 0


def test_l2_stratified_table_matches_recomputation() -> None:
    folder = RES / "l2_stratified_audit_20261023_baseline_v9" / "stratified.json"
    if not folder.exists():
        pytest.skip("stratified audit folder missing")
    s = json.loads(folder.read_text(encoding="utf-8"))
    prov, claude, pooled = (s[k] for k in ("providers_only(gemini+groq)", "claude_supplement_only", "combined(heterogeneous)"))
    assert (prov["valid_runs"], claude["valid_runs"], pooled["valid_runs"]) == (22, 38, 60)
    assert round(prov["exact_status_agreement"] * 18) == 5
    assert round(claude["exact_status_agreement"] * 24) == 7
    assert round(pooled["exact_status_agreement"] * 36) == 11
    assert claude["llm_osd_repeatable_pairs"] == 3 and prov["llm_osd_repeatable_pairs"] == 0
    assert "Triple-ident." in _tex("ch7_results.tex")


def test_fairness_confirmation_h1_failure_is_reported_as_failure() -> None:
    hyp = _json("fairness_confirm_20261003", "analysis", "analysis.json")
    h = hyp.get("hypotheses", hyp)
    assert h["H1"]["holds"] is False and h["H2"]["holds"] is True
    assert re.search(r"H1\}.*fails", _tex("ch7_results.tex"))


def test_human_study_counts() -> None:
    agree = _json("l10_human_analysis_20261005", "agreement.json")
    assert set(agree) >= {"all7", "R0_only"}
    ch7 = _tex("ch7_results.tex")
    assert "Seven submissions" in ch7 and "Six submissions carry the shared code" in ch7
