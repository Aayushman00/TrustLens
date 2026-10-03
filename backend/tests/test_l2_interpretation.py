"""L2: deterministic vs LLM interpretation of the same frozen evidence packets."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.osd.llm_client import LLMResponseTruncatedError, build_prompt
from app.probes.integrity_artifact import build_artifact_manifest
from app.scripts import run_l2_interpretation as l2

_CARD = """---
license: apache-2.0
---
# demo_model — toxicity classifier

## Intended Use
Classifies English comments as toxic or not, for offline benchmarking only.

## Limitations
demo_model under-flags severe toxicity; do not use for moderation.
"""


def _raw(o: int = 7, s: int = 6, d: int = 8) -> str:
    dim = {"O": o, "S": s, "D": d, "rationale": "The evidence block and card text support this judgment in detail."}
    return json.dumps({"INTEGRITY": dim, "EXPLAINABILITY": {**dim, "content_quality": "generic"},
                       "SAFETY": {**dim, "content_quality": "generic"}})


def _model_dir(tmp_path: Path, name: str = "demo_model", card: str = _CARD) -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "config.json").write_text("{}", encoding="utf-8")
    (d / "model.safetensors").write_bytes(b"weights-v1")
    (d / "README.md").write_text(card, encoding="utf-8")
    return d


_BEHAVIOR = {"status": "EVALUATED", "severe_n": 260, "severe_fnr": 0.5, "severe_fnr_ci": [0.44, 0.56],
             "overall_fnr": 0.5, "fnr_ratio": 1.0, "harmful_recall": 0.5, "benign_fpr": 0.02}


def _packet(tmp_path: Path, **kw) -> dict:
    return l2.build_packet("P01", _model_dir(tmp_path), behavior=kw.pop("behavior", _BEHAVIOR), **kw)


def _settings(mock_settings, gemini="g", groq=None, nvidia=None) -> None:
    mock_settings.return_value.gemini_api_key = gemini
    mock_settings.return_value.groq_api_key = groq
    mock_settings.return_value.nvidia_api_key = nvidia


# --- packets and leakage -------------------------------------------------


def test_packet_hash_is_canonical_and_order_independent(tmp_path: Path) -> None:
    p = _packet(tmp_path)
    shuffled = dict(reversed(list(p.items())))
    assert l2.packet_sha256(p) == l2.packet_sha256(shuffled)
    assert l2.packet_sha256(p) != l2.packet_sha256({**p, "card_text": p["card_text"] + " "})


def test_packet_is_anonymized_and_holds_no_decisions(tmp_path: Path) -> None:
    p = _packet(tmp_path)
    blob = json.dumps(p)
    assert "demo_model" not in blob and "P01" in p["card_text"]
    assert p["model_ref"] == "/models/P01"
    for key in l2.FORBIDDEN_KEYS:
        assert f'"{key}"' not in blob


def test_other_suite_identifiers_are_anonymized(tmp_path: Path) -> None:
    card = _CARD + "\nTrained like variant1_fairness and sweep_safety_r075.\n"
    p = l2.build_packet("P04", _model_dir(tmp_path, card=card), behavior={"status": "NOT_APPLICABLE"})
    assert "variant1_fairness" not in p["card_text"] and "sweep_safety_r075" not in p["card_text"]


def test_llm_prompt_has_no_trustlens_decision_score_or_osd(tmp_path: Path) -> None:
    prompt = build_prompt(l2.llm_context(_packet(tmp_path)))
    for key in l2.FORBIDDEN_KEYS:
        assert f'"{key}"' not in prompt
    assert "demo_model" not in prompt
    assert "fries" not in prompt.lower().replace("fries convention", "")


def test_both_evaluators_receive_the_identical_packet(tmp_path: Path) -> None:
    p = _packet(tmp_path)
    det = l2.deterministic_eval(p)
    store = l2.ResponseStore(tmp_path / "r.jsonl")
    with patch("app.osd.hybrid.get_settings") as s, patch("app.osd.hybrid.call_gemini", return_value=_raw()):
        _settings(s)
        run = l2.llm_run(p, 1, store)
    assert det["packet_sha256"] == run["packet_sha256"] == l2.packet_sha256(p)


# --- deterministic evaluator ---------------------------------------------


def test_deterministic_output_preserves_production_decisions(tmp_path: Path) -> None:
    good = _model_dir(tmp_path, "good")
    manifest = build_artifact_manifest(good)
    tampered = _model_dir(tmp_path, "bad")
    (tampered / "model.safetensors").write_bytes(b"weights-v2")
    p = l2.build_packet("P02", tampered, behavior={"status": "NOT_APPLICABLE"}, manifest=manifest)
    det = l2.deterministic_eval(p)["dimensions"]
    assert p["artifact_verification"]["status"] == "MISMATCH"
    assert "I-INT-BYTES-DIVERGE" in det["INTEGRITY"]["risks_triggered"]
    assert det["INTEGRITY"]["risk_present"] == "YES"
    # Card-based sections missing -> disclosure gap, which L3 says is not a risk.
    assert det["SAFETY"]["disclosure_gaps"] and det["SAFETY"]["risk_present"] == "NO"
    assert det["SAFETY"]["O"] is not None and det["SAFETY"]["severity"] == det["SAFETY"]["S"]


def test_deterministic_empty_card_is_insufficient_evidence(tmp_path: Path) -> None:
    p = l2.build_packet("P03", _model_dir(tmp_path, card=""), behavior={"status": "NOT_APPLICABLE"})
    det = l2.deterministic_eval(p)["dimensions"]["EXPLAINABILITY"]
    assert det["evidence_sufficient"] == "NO" and det["risk_present"] == "UNCERTAIN"


def test_deterministic_safety_band_uses_frozen_behaviour(tmp_path: Path) -> None:
    det = l2.deterministic_eval(_packet(tmp_path))["dimensions"]["SAFETY"]
    assert (det["O"], det["S"], det["D"]) == (5, 6, 8)  # v3: O=scale(1-0.5), S=6 (ratio<=1.5)


# --- LLM evaluator: parsing, cache, fallback ------------------------------


def test_llm_fields_follow_the_frozen_prompts_definition() -> None:
    assert l2.llm_fields({"O": 5, "S": 4, "D": 6})["risk_present"] == "YES"
    f = l2.llm_fields({"O": 6, "S": 7, "D": 8})
    assert f["risk_present"] == "NO" and f["severity"] == 7 and f["evidence_sufficient"] is None


def test_llm_run_parses_structured_output(tmp_path: Path) -> None:
    store = l2.ResponseStore(tmp_path / "r.jsonl")
    with patch("app.osd.hybrid.get_settings") as s, patch("app.osd.hybrid.call_gemini", return_value=_raw(4, 3, 5)):
        _settings(s)
        run = l2.llm_run(_packet(tmp_path), 1, store)
    assert run["fallback"] is False and run["provider"] == "gemini"
    assert run["dimensions"]["SAFETY"] == {"O": 4, "S": 3, "D": 5, "risk_present": "YES", "severity": 3,
                                           "evidence_sufficient": None, "content_quality": "generic",
                                           "rationale": run["dimensions"]["SAFETY"]["rationale"]}


def test_cache_is_keyed_by_run_index_and_replay_never_calls_the_api(tmp_path: Path) -> None:
    p = _packet(tmp_path)
    store = l2.ResponseStore(tmp_path / "r.jsonl")
    with patch("app.osd.hybrid.get_settings") as s, \
            patch("app.osd.hybrid.call_gemini", side_effect=[_raw(7, 7, 8), _raw(3, 3, 3)]) as call:
        _settings(s)
        r1 = l2.llm_run(p, 1, store)
        r2 = l2.llm_run(p, 2, store)
        assert call.call_count == 2  # run 2 is a new call, not a copy of run 1
    assert r1["dimensions"]["SAFETY"]["O"] == 7 and r2["dimensions"]["SAFETY"]["O"] == 3
    reread = l2.ResponseStore(tmp_path / "r.jsonl")
    with patch("app.osd.hybrid.call_gemini", side_effect=AssertionError("no API in replay")):
        again = l2.llm_run(p, 2, reread, replay=True)
    assert again["replayed"] is True and again["dimensions"]["SAFETY"]["O"] == 3
    with pytest.raises(KeyError):
        l2.llm_run(p, 3, reread, replay=True)


def test_output_truncation_falls_back_and_is_counted(tmp_path: Path) -> None:
    store = l2.ResponseStore(tmp_path / "r.jsonl")
    with patch("app.osd.hybrid.get_settings") as s, \
            patch("app.osd.hybrid.call_gemini", side_effect=LLMResponseTruncatedError("MAX_TOKENS")):
        _settings(s)
        run = l2.llm_run(_packet(tmp_path), 1, store)
    assert run["fallback"] is True and run["output_truncated"] is True and run["dimensions"] is None


def test_provider_unavailable_fallback_can_be_retried_later(tmp_path: Path) -> None:
    p = _packet(tmp_path)
    store = l2.ResponseStore(tmp_path / "r.jsonl")
    with patch("app.osd.hybrid.get_settings") as s, \
            patch("app.osd.hybrid.call_gemini", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")):
        _settings(s)
        first = l2.llm_run(p, 1, store)
    assert first["fallback"] and first["provider_unavailable"] and first["parse_failures"] == 0
    with patch("app.osd.hybrid.get_settings") as s, patch("app.osd.hybrid.call_gemini", return_value=_raw()):
        _settings(s)
        assert l2.llm_run(p, 1, store)["fallback"] is True  # without the flag the stored record stands
        again = l2.llm_run(p, 1, store, retry_fallbacks=True)
    assert again["fallback"] is False and again["superseded_attempt_records"] == 1
    lines = (tmp_path / "r.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # the failed record is kept in the log


def test_parser_failure_is_recorded(tmp_path: Path) -> None:
    store = l2.ResponseStore(tmp_path / "r.jsonl")
    with patch("app.osd.hybrid.get_settings") as s, patch("app.osd.hybrid.call_gemini", return_value="not json"):
        _settings(s)
        run = l2.llm_run(_packet(tmp_path), 1, store)
    assert run["fallback"] is True and run["parse_failures"] == 1


def test_repeatability_summary() -> None:
    runs = [{"fallback": False, "dimensions": {"SAFETY": {"O": o, "S": 3, "D": 4, "risk_present": rp}}}
            for o, rp in ((4, "YES"), (4, "YES"), (6, "NO"))] + [{"fallback": True, "dimensions": None}]
    rep = l2.llm_modal(runs, "SAFETY")
    assert rep["risk_present"] == "YES" and rep["risk_agreement"] == pytest.approx(2 / 3)
    assert rep["O_range"] == 2 and rep["valid_runs"] == 3 and rep["O"] == 4


# --- disagreement categories ---------------------------------------------


def _det(rp: str, s: int = 5) -> dict:
    return {"risk_present": rp, "S": s}


def _llm(rp: str | None, s: int | None = 5, **kw) -> dict:
    return {"risk_present": rp, "S": s, "valid_runs": 0 if rp is None else 5, **kw}


@pytest.mark.parametrize(
    ("det", "llm", "category"),
    [
        ({"SAFETY": _det("NO")}, {"SAFETY": _llm(None, parse_failures=5)}, "parser_format_failure"),
        ({"SAFETY": _det("NO")}, {"SAFETY": _llm(None, parse_failures=0)}, "truncation_fallback"),
        ({"SAFETY": _det("UNCERTAIN")}, {"SAFETY": _llm("YES")}, "insufficient_evidence"),
        ({"SAFETY": _det("NO"), "INTEGRITY": _det("YES")}, {"SAFETY": _llm("YES"), "INTEGRITY": _llm("NO")},
         "localization"),
        ({"SAFETY": _det("NO")}, {"SAFETY": _llm("YES")}, "evidence_interpretation"),
        ({"SAFETY": _det("NO", 3)}, {"SAFETY": _llm("NO", 6)}, "severity"),
        ({"SAFETY": _det("NO", 5)}, {"SAFETY": _llm("NO", 6)}, "agree"),
    ],
)
def test_disagreement_category(det: dict, llm: dict, category: str) -> None:
    assert l2.categorize(det, llm, "SAFETY") == category


def test_localization_ignores_packets_without_llm_answers() -> None:
    det = {"P01": {"elapsed_ms": 1.0, "dimensions": {d: {"risk_present": "NO", "O": 7, "S": 7, "D": 8}
                                                     for d in ("INTEGRITY", "EXPLAINABILITY", "SAFETY")}}}
    runs = {"P01": [{"fallback": True, "dimensions": None, "parse_failures": 0, "elapsed_s": 1.0,
                     "output_truncated": False, "prompt_truncated": False, "replayed": False, "provider": None,
                     "provider_unavailable": True, "superseded_attempt_records": 0}]}
    cmp = l2.compare(det, runs)
    assert cmp["localization"] == [] and cmp["summary"]["localization_exact_match"] is None


def _run(o: int | None, provider: str | None = "groq", elapsed: float = 2.0) -> dict:
    dims = None if o is None else {d: {"O": o, "S": o, "D": o, "risk_present": "YES" if o <= 5 else "NO"}
                                   for d in ("INTEGRITY", "EXPLAINABILITY", "SAFETY")}
    return {"fallback": o is None, "dimensions": dims, "parse_failures": 0, "elapsed_s": elapsed,
            "output_truncated": False, "prompt_truncated": False, "replayed": False, "provider": provider,
            "provider_unavailable": o is None, "superseded_attempt_records": 0}


def test_repeatability_counts_only_pairs_with_two_or_more_answers_and_latency_only_successes() -> None:
    det = {p: {"elapsed_ms": 1.0, "dimensions": {d: {"risk_present": "NO", "O": 7, "S": 7, "D": 8}
                                                 for d in ("INTEGRITY", "EXPLAINABILITY", "SAFETY")}}
           for p in ("P01", "P02")}
    runs = {"P01": [_run(3, "groq", 4.0), _run(7, "gemini", 6.0)], "P02": [_run(4), _run(None, None, 100.0)]}
    s = l2.compare(det, runs)["summary"]
    assert s["llm_repeatability_pairs"] == 3  # P02 has a single answer: not a repeatability observation
    assert s["llm_risk_repeatable_pairs"] == 0 and s["llm_osd_repeatable_pairs"] == 0
    assert s["llm_s_per_successful_call_mean"] == pytest.approx(4.0)
    assert s["provider_variation"]["SAFETY"]["groq"]["n"] == 2
    assert s["provider_variation"]["SAFETY"]["gemini"]["O_mean"] == 7


def test_attempt_stats_count_every_provider_attempt(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    recs = [{"attempts": [{"provider": "gemini", "error": "ClientError: 429"}, {"provider": "groq", "raw": "{}"}]},
            {"attempts": [{"provider": "groq", "error": "HTTPStatusError: 429"}]}]
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    assert l2.attempt_stats(path) == {"gemini": {"ok": 0, "ClientError": 1}, "groq": {"ok": 1, "HTTPStatusError": 1}}
