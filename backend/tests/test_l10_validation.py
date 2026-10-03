"""L10: independent evidence validation (packets, blinding, reviewer schema, agreement)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.scripts import run_l10_validation as l10

_ANSWER = {"risk_present": "YES", "dimension": "SAFETY", "severity": 3, "evidence_sufficient": "YES",
           "rationale": "Severe-harm miss rate is far above the reference on the same data."}


@pytest.fixture(scope="module")
def built() -> tuple[dict, dict]:
    return l10.build_packets()


# --- packets ---------------------------------------------------------------


def test_twelve_packets_cover_every_fries_dimension(built) -> None:
    packets, refs = built
    assert len(packets) == 12 and set(refs) == set(packets)
    assert {p["dimension"] for p in packets.values()} == {"FAIRNESS", "ROBUSTNESS", "INTEGRITY",
                                                          "EXPLAINABILITY", "SAFETY"}


def test_packet_hash_is_stable_and_content_sensitive(built) -> None:
    packets, _ = built
    again, _ = l10.build_packets()
    for pid, p in packets.items():
        assert l10.packet_sha256(p) == l10.packet_sha256(again[pid])
    p = packets["L10-01"]
    assert l10.packet_sha256(p) != l10.packet_sha256({**p, "dimension": "SAFETY"})


@pytest.mark.parametrize("needle", l10.LEAK_STRINGS)
def test_evaluator_packets_hold_no_trustlens_answer_or_hidden_label(built, needle: str) -> None:
    packets, _ = built
    for pid, p in packets.items():
        assert needle.lower() not in json.dumps(p).lower(), (pid, needle)


def test_no_trustlens_answer_keys_anywhere(built) -> None:
    packets, _ = built

    def keys(x):
        if isinstance(x, dict):
            for k, v in x.items():
                yield k
                yield from keys(v)
        elif isinstance(x, list):
            for v in x:
                yield from keys(v)

    for p in packets.values():
        assert not set(keys(p)) & set(l10.FORBIDDEN_KEYS)


def test_raw_evidence_is_preserved_from_the_frozen_source(built) -> None:
    packets, _ = built
    src = json.loads((l10.L5 / "analysis" / "raw" / "fairness_r070__run1.json").read_text(encoding="utf-8"))
    m, ev = src["metric_values"], packets["L10-01"]["evidence"]
    assert ev["equal_opportunity_difference"] == m["equal_opportunity_difference"]
    assert ev["equal_opportunity_difference_ci95"] == [m["eopp_ci"]["ci_lower"], m["eopp_ci"]["ci_upper"]]
    assert ev["groups"]["1"]["n"] == m["groups"]["1"]["n"]
    sev = packets["L10-06"]["evidence"]
    assert sev["severe_n"] == 260 and sev["severe_fnr"] == pytest.approx(0.6461538, abs=1e-6)
    assert packets["L10-08"]["evidence"]["artifact_verification"]["status"] == "MISMATCH"


def test_provenance_hashes_match_the_untouched_sources(built) -> None:
    packets, refs = built
    for pid in packets:
        assert "provenance" not in packets[pid]
        for prov in refs[pid]["provenance"]:
            path = l10.REPO_ROOT / prov["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == prov["sha256"]


def test_card_redactions_are_recorded(built) -> None:
    packets, _ = built
    card = packets["L10-11"]["evidence"]["card_text"]
    assert "(research artifact)" in card and "L10-11" in card
    assert packets["L10-11"]["redactions"]


def test_building_does_not_mutate_sources(tmp_path: Path) -> None:
    files = [l10.L5 / "analysis" / "raw" / "fairness_r070__run1.json", l10.L6, l10.L6_A2]
    before = [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]
    l10.build_packets()
    assert before == [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]


def test_trustlens_reference_keeps_the_automated_answer(built) -> None:
    _, refs = built
    assert refs["L10-01"]["risk_present"] == "YES" and refs["L10-01"]["risk_ids"] == ["F-FAIR-EOPP"]
    assert refs["L10-02"]["risk_present"] == "UNCERTAIN" and refs["L10-02"]["evidence_sufficient"] != "YES"
    assert refs["L10-05"]["evidence_sufficient"] == "NO"
    assert refs["L10-08"]["risk_present"] == "YES" and refs["L10-08"]["dimension"] == "INTEGRITY"
    assert refs["L10-06"]["risk_present"] == "NO"  # behavioural safety has no risk ID
    assert all(r["severity"] == r["S"] for r in refs.values())


# --- reviewer schema ---------------------------------------------------------


def test_valid_review_passes() -> None:
    assert l10.validate_review({**_ANSWER, "packet_id": "L10-06"}) == []


@pytest.mark.parametrize(("field", "value"), [
    ("risk_present", "MAYBE"), ("dimension", "PRIVACY"), ("evidence_sufficient", "yes please"),
    ("severity", 0), ("severity", 10), ("severity", "high"), ("rationale", ""), ("packet_id", "X-1")])
def test_invalid_review_values_are_rejected(field: str, value) -> None:
    assert l10.validate_review({**_ANSWER, "packet_id": "L10-06", field: value})


def test_uncertain_and_missing_evidence_answers_are_allowed() -> None:
    row = {"packet_id": "L10-05", "risk_present": "UNCERTAIN", "dimension": "UNCERTAIN", "severity": None,
           "evidence_sufficient": "NO", "rationale": "One row could not be perturbed; accuracies are missing."}
    assert l10.validate_review(row) == []
    assert l10.validate_review({**row, "risk_present": "NO", "dimension": "NONE"}) == []
    assert l10.validate_review({**row, "risk_present": "NO", "severity": 4})  # severity only when not NO


def test_csv_template_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "r1.csv"
    l10.write_template(path, ["L10-01", "L10-02"])
    rows = l10.load_reviews(path)
    assert [r["packet_id"] for r in rows] == ["L10-01", "L10-02"] and rows[0]["severity"] is None


# --- comparison --------------------------------------------------------------


def _a(rp: str, dim: str = "SAFETY", sev: int | None = 3, suff: str = "YES") -> dict:
    return {"risk_present": rp, "dimension": dim, "severity": sev, "evidence_sufficient": suff}


@pytest.mark.parametrize(("a", "b", "cat"), [
    (_a("YES"), None, "provider_infrastructure"),
    (_a("YES"), {"parse_error": "bad json"}, "parser_format"),
    (_a("YES"), _a("UNCERTAIN"), "abstention_mismatch"),
    (_a("NO", sev=None), _a("NO", sev=None, suff="NO"), "insufficient_evidence"),
    (_a("YES", "SAFETY"), _a("YES", "FAIRNESS"), "localization"),
    (_a("YES"), _a("NO", sev=None), "evidence_interpretation"),
    (_a("YES", sev=2), _a("YES", sev=6), "severity"),
    (_a("YES", sev=3), _a("YES", sev=4), "agree"),
])
def test_disagreement_categories(a: dict, b: dict | None, cat: str) -> None:
    assert l10.categorize(a, b) == cat


def test_layer_of_disagreement_with_trustlens() -> None:
    assert l10.disagreement_layer(_a("YES", sev=2), _a("YES", sev=6)) == "score"
    assert l10.disagreement_layer(_a("YES"), _a("NO", sev=None)) == "risk"
    assert l10.disagreement_layer(_a("NO", sev=None), _a("UNCERTAIN", suff="NO")) == "evidence"
    assert l10.disagreement_layer(_a("YES", sev=3), _a("YES", sev=3)) is None


def test_cohen_kappa_and_small_sample_guard() -> None:
    a = ["YES", "NO", "YES", "NO", "YES", "NO", "YES", "NO"]
    assert l10.cohen_kappa(a, a) == pytest.approx(1.0)
    assert l10.cohen_kappa(a, ["YES"] * 8) == pytest.approx(0.0)
    assert l10.cohen_kappa(a[:4], a[:4]) is None  # fewer than 8 common packets


def test_fleiss_kappa_perfect_and_chance() -> None:
    perfect = [["YES"] * 3, ["NO"] * 3] * 4
    assert l10.fleiss_kappa(perfect) == pytest.approx(1.0)
    assert l10.fleiss_kappa(perfect[:4]) is None


def test_pair_summary_uses_only_common_answered_packets() -> None:
    a = {"L10-01": _a("YES", sev=3), "L10-02": _a("NO", sev=None)}
    b = {"L10-01": _a("YES", sev=4)}
    s = l10.pair_summary(a, b)
    assert s["n_common"] == 1 and s["risk_agreement"] == 1.0 and s["severity_within_1"] == 1.0
    assert s["categories"] == {"agree": 1, "provider_infrastructure": 1}


# --- independent LLM ---------------------------------------------------------


def test_llm_prompt_is_separate_and_blind(built) -> None:
    packets, refs = built
    prompt = l10.review_prompt(packets["L10-01"])
    assert l10.L10_REVIEW_PROMPT_VERSION in prompt and "osd-llm" not in prompt
    assert "F-FAIR-EOPP" not in prompt and json.dumps(refs["L10-01"]) not in prompt


def test_llm_review_parses_and_logs_provider(tmp_path: Path, built) -> None:
    packets, _ = built
    with patch("app.scripts.run_l10_validation.get_settings") as s, \
            patch("app.scripts.run_l10_validation.call_gemini", return_value=json.dumps(_ANSWER)):
        s.return_value.gemini_api_key, s.return_value.groq_api_key, s.return_value.nvidia_api_key = "k", None, None
        rec = l10.llm_review(packets["L10-06"])
    assert rec["answer"]["risk_present"] == "YES" and rec["provider"] == "gemini" and rec["model"]
    assert rec["packet_sha256"] == l10.packet_sha256(packets["L10-06"])


def test_llm_outage_is_not_a_judgment(built) -> None:
    packets, _ = built
    with patch("app.scripts.run_l10_validation.get_settings") as s, \
            patch("app.scripts.run_l10_validation.call_gemini", side_effect=RuntimeError("429")), \
            patch("app.scripts.run_l10_validation.call_groq", return_value="not json"):
        s.return_value.gemini_api_key, s.return_value.groq_api_key, s.return_value.nvidia_api_key = "k", "k", None
        rec = l10.llm_review(packets["L10-06"])
    assert rec["answer"] is None and rec["parse_error"] and len(rec["attempts"]) == 2
