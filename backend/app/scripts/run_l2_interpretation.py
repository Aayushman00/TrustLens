"""L2: deterministic vs LLM interpretation of the same frozen evidence
(pre-registration docs/superpowers/plans/2026-10-03-round3-L2-det-vs-llm.md).

Builds anonymized evidence packets for the suite's I/E/S conditions, runs the
current deterministic rules and the frozen llm_v1 judgment (PROMPT_VERSION
unchanged) on each packet, and characterizes agreement. No winner, no
adjudication: both outputs are kept verbatim.

Usage (from backend/, LLM keys in ../.env)::

    python -m app.scripts.run_l2_interpretation --out ../results/l2_det_vs_llm_20261003
    python -m app.scripts.run_l2_interpretation --out <same> --resume   # continue after a quota stop
    python -m app.scripts.run_l2_interpretation --out <same> --replay   # re-analyse stored responses only
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import statistics
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.osd import hybrid
from app.osd.agent import HeuristicOSDAgent
from app.osd.base import AgentContext, ProbeSnapshot
from app.osd.hybrid import HybridOSDAgent
from app.osd.llm_client import PROMPT_VERSION, parse_gemini_response
from app.probes.explainability_eval import evaluate_explainability
from app.probes.integrity_artifact import build_artifact_manifest, local_integrity_extras, verify_local_artifacts
from app.probes.integrity_eval import evaluate_integrity
from app.probes.integrity_stats import G_ARTIFACT_INCOMPLETE
from app.probes.safety_eval import evaluate_safety
from app.scripts.prepare_flawed_suite_data import REPO_ROOT, SUITE_DIR, validate_out_dir

PACKET_SCHEMA = "l2-evidence-packet-v1"
DIMENSIONS = (FriesDimension.INTEGRITY, FriesDimension.EXPLAINABILITY, FriesDimension.SAFETY)
# Pre-declared packet set and order (P01..P12).
PACKET_MODELS = (
    "reference_toxicbert_2label", "variant1_fairness", "variant1_fairness_tampered", "variant2_robustness",
    "variant3_explainability", "variant4_integrity", "variant4b_integrity_clean", "variant5_safety",
    "variant6_compound", "sweep_safety_r025", "sweep_safety_r075", "sweep_safety_r100",
)
MANIFEST_SOURCE = {"variant1_fairness": "variant1_fairness", "variant1_fairness_tampered": "variant1_fairness"}
L6_ANALYSIS = REPO_ROOT / "results" / "defect_severity_20261003" / "analysis.json"
RUNS = 5

# TrustLens decisions/scores: never in a packet, never in an evaluator prompt.
FORBIDDEN_KEYS = (
    "aspect_scoring", "scored_risk_id", "risks_triggered", "fairness_finding", "reliability", "failed_gates",
    "claims", "probe_status", "flags", "fries_score", "dimension_scores", "osd_proposals", "ai_suggestion",
)
# Also removed from the LLM's evidence view: lifecycle status and boilerplate.
_STRIP_KEYS = frozenset(FORBIDDEN_KEYS) | {
    "status", "status_reason", "probe_status_reason", "note", "proposed_mapping", "confidence", "claim_boundary",
}
_BEHAVIOR_KEYS = ("severe_n", "severe_fnr", "severe_fnr_ci", "overall_fnr", "fnr_ratio", "harmful_recall",
                  "benign_fpr")
_RISK_SCORING = ("risk_detected", "scored_risk")
# Suite model identifiers (they name the injected defect); replaced by the packet id.
_SUITE_NAME = re.compile(r"\b(?:variant\d\w*|sweep_(?:fairness|safety)_r\d{3}|reference_toxicbert_2label)\b")


def packet_sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_packet(packet_id: str, model_dir: Path, *, behavior: dict[str, Any],
                 manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Raw evidence for one model, with its folder name replaced by ``packet_id``."""
    card = model_dir / "README.md"
    text = card.read_text(encoding="utf-8") if card.exists() else ""
    av = verify_local_artifacts(model_dir, manifest=manifest)
    packet = {
        "schema": PACKET_SCHEMA, "packet_id": packet_id, "model_ref": f"/models/{packet_id}",
        "model_revision": "local", "card_text": text, "artifact_verification": av, "safety_behavior": behavior,
    }
    blob = json.dumps(packet).replace(model_dir.name, packet_id)
    return json.loads(_SUITE_NAME.sub(packet_id, blob))


def evidence_views(packet: dict[str, Any]) -> dict[FriesDimension, dict[str, Any]]:
    """Current probe evidence recomputed from the packet with the production
    pure functions (what IntegrityProbe/ExplainabilityProbe/SafetyProbe emit)."""
    meta = {"card_text": packet["card_text"]}
    av = packet["artifact_verification"]

    def as_metrics(result: Any) -> dict[str, Any]:
        m = dataclasses.asdict(result)
        m["status"] = m["probe_status"] = result.status.value
        return m

    integrity = evaluate_integrity(model_ref=packet["model_ref"], model_revision=packet["model_revision"],
                                   model_metadata=meta, integrity_extra=local_integrity_extras(av))
    if av.get("status") == "INCOMPLETE":
        integrity.reliability = {"gates_passed": False,
                                 "failed_gates": [*integrity.reliability.get("failed_gates", []), G_ARTIFACT_INCOMPLETE]}
    safety = as_metrics(evaluate_safety(model_metadata=meta))
    behavior = packet["safety_behavior"]
    safety["behavior"] = behavior
    if behavior.get("status") == ProbeEvaluationStatus.EVALUATED.value:
        safety["severe_fnr"], safety["fnr_ratio"] = behavior["severe_fnr"], behavior["fnr_ratio"]
    return {
        FriesDimension.INTEGRITY: {**as_metrics(integrity), "artifact_verification": av},
        FriesDimension.EXPLAINABILITY: as_metrics(evaluate_explainability(model_metadata=meta)),
        FriesDimension.SAFETY: safety,
    }


def _context(packet: dict[str, Any], views: dict[FriesDimension, dict[str, Any]]) -> AgentContext:
    return AgentContext(
        evaluation_id=uuid.uuid5(uuid.NAMESPACE_URL, packet["packet_id"]), model_ref=packet["model_ref"],
        model_metadata={"card_text": packet["card_text"]},
        probe_results=[ProbeSnapshot(dimension=d, metric_values=m, confidence=None, evidence_refs=[])
                       for d, m in views.items()],
    )


def llm_context(packet: dict[str, Any]) -> AgentContext:
    """The LLM's input: card text plus the evidence view minus every TrustLens decision."""
    views = {d: {k: v for k, v in m.items() if k not in _STRIP_KEYS} for d, m in evidence_views(packet).items()}
    return _context(packet, views)


def deterministic_eval(packet: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    views = evidence_views(packet)
    bands = {a.aspect: a for a in HeuristicOSDAgent(mapping="v3").propose(_context(packet, views)).aspects}
    dims: dict[str, Any] = {}
    for d, m in views.items():
        gates = (m.get("reliability") or {}).get("failed_gates") or []
        if m["status"] == ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value or m["aspect_scoring"] == "not_scored":
            sufficient = "NO"
        elif m["aspect_scoring"] == "mapping_blocked" or gates:
            sufficient = "UNCERTAIN"
        else:
            sufficient = "YES"
        if m["risks_triggered"] or m["aspect_scoring"] in _RISK_SCORING:
            risk = "YES"  # a triggered risk is reported even when another gate failed
        else:
            risk = "NO" if sufficient == "YES" else "UNCERTAIN"
        a = bands[d]
        dims[d.value] = {
            "status": m["status"], "aspect_scoring": m["aspect_scoring"], "risks_triggered": m["risks_triggered"],
            "disclosure_gaps": m["disclosure_gaps"], "failed_gates": gates, "evidence_sufficient": sufficient,
            "risk_present": risk, "O": a.O, "S": a.S, "D": a.D, "severity": a.S,
        }
    return {"packet_id": packet["packet_id"], "packet_sha256": packet_sha256(packet), "mapping": "v3 (HeuristicOSDAgent)",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3), "dimensions": dims}


class ResponseStore:
    """Append-only JSONL of live LLM responses keyed by (packet sha256, run index).
    A response is only ever reused for its own run index; a later record for the
    same key (a retried provider-unavailable run) supersedes, and the log keeps both."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._rows: dict[tuple[str, int], dict[str, Any]] = {}
        self.superseded: Counter[tuple[str, int]] = Counter()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                self._index(rec)

    def _index(self, rec: dict[str, Any]) -> None:
        key = (rec["packet_sha256"], rec["run_index"])
        if key in self._rows:
            self.superseded[key] += 1
        self._rows[key] = rec

    def get(self, sha: str, run_index: int) -> dict[str, Any] | None:
        return self._rows.get((sha, run_index))

    def put(self, rec: dict[str, Any]) -> None:
        self._index(rec)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def llm_fields(j: dict[str, Any]) -> dict[str, Any]:
    """Derived fields; risk rule is the frozen prompt's own (O<=5 = risk clearly present)."""
    return {"risk_present": "YES" if j["O"] <= 5 else "NO", "severity": j["S"], "evidence_sufficient": None}


def _live_call(packet: dict[str, Any], sha: str, run_index: int) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    originals = {n: getattr(hybrid, n) for n in ("call_gemini", "call_groq", "call_nvidia")}

    def wrap(name: str) -> Any:
        def call(prompt: str, *, api_key: str) -> str:
            t0 = time.perf_counter()
            try:
                raw = originals[name](prompt, api_key=api_key)
            except Exception as exc:
                attempts.append({"provider": name.removeprefix("call_"), "error": f"{type(exc).__name__}: {exc}"[:400],
                                 "elapsed_s": round(time.perf_counter() - t0, 3)})
                raise
            attempts.append({"provider": name.removeprefix("call_"), "raw": raw,
                             "elapsed_s": round(time.perf_counter() - t0, 3)})
            return raw
        return call

    t0 = time.perf_counter()
    with patch.multiple(hybrid, **{n: wrap(n) for n in originals}):
        _judgment, provenance = HybridOSDAgent()._get_llm_judgment(llm_context(packet))
    return {"packet_id": packet["packet_id"], "packet_sha256": sha, "run_index": run_index,
            "prompt_version": PROMPT_VERSION, "provenance": provenance, "attempts": attempts,
            "elapsed_s": round(time.perf_counter() - t0, 3), "at": datetime.now(UTC).isoformat()}


def _provider_unavailable(rec: dict[str, Any]) -> bool:
    """Every attempt failed before any text came back, none by output truncation (quota, 5xx, 404...)."""
    return all("raw" not in a and not a.get("error", "").startswith("LLMResponseTruncatedError")
               for a in rec["attempts"])


def llm_run(packet: dict[str, Any], run_index: int, store: ResponseStore, *, replay: bool = False,
            retry_fallbacks: bool = False) -> dict[str, Any]:
    sha = packet_sha256(packet)
    rec = store.get(sha, run_index)
    if rec is not None and retry_fallbacks and not replay and _provider_unavailable(rec):
        rec = None  # provider outage, not a model answer: re-attempt the same run index
    replayed = rec is not None
    if rec is None:
        if replay:
            raise KeyError(f"no stored response for {packet['packet_id']} run {run_index}")
        rec = _live_call(packet, sha, run_index)
        store.put(rec)
    judgment, provider, parse_failures = None, None, 0
    for att in rec["attempts"]:
        if "raw" not in att:
            continue
        try:
            judgment = parse_gemini_response(att["raw"])
        except ValueError:
            parse_failures += 1
            continue
        provider = att["provider"]
        break
    dims = None
    if judgment is not None:
        dims = {}
        for d in DIMENSIONS:
            j = getattr(judgment, d.value).model_dump()
            dims[d.value] = {**{k: j[k] for k in ("O", "S", "D", "rationale", "content_quality")}, **llm_fields(j)}
    prov = rec["provenance"]
    return {
        "packet_id": rec["packet_id"], "packet_sha256": sha, "run_index": run_index, "replayed": replayed,
        "provider": provider, "model": prov.get("llm_model"), "attempts": len(rec["attempts"]),
        "fallback": judgment is None, "parse_failures": parse_failures,
        "provider_unavailable": judgment is None and _provider_unavailable(rec),
        "superseded_attempt_records": store.superseded[(sha, run_index)],
        "output_truncated": any(a.get("error", "").startswith("LLMResponseTruncatedError") for a in rec["attempts"]),
        "prompt_truncated": bool(prov.get("llm_prompt_truncated")), "prompt_sha256": prov.get("llm_prompt_sha256"),
        "elapsed_s": rec["elapsed_s"], "dimensions": dims,
    }


def llm_modal(runs: list[dict[str, Any]], dim: str) -> dict[str, Any]:
    """Modal LLM answer and repeatability over the valid (non-fallback) runs."""
    vals = [r["dimensions"][dim] for r in runs if not r["fallback"]]
    out: dict[str, Any] = {"valid_runs": len(vals), "fallbacks": len(runs) - len(vals),
                           "parse_failures": sum(r.get("parse_failures", 0) for r in runs),
                           "output_truncated": sum(bool(r.get("output_truncated")) for r in runs)}
    if not vals:
        return {**out, "risk_present": None, "O": None, "S": None, "D": None}
    counts = Counter(v["risk_present"] for v in vals).most_common()
    modal = "UNCERTAIN" if len(counts) > 1 and counts[0][1] == counts[1][1] else counts[0][0]
    for k in ("O", "S", "D"):
        xs = [v[k] for v in vals]
        out |= {k: statistics.median_low(xs), f"{k}_range": max(xs) - min(xs), f"{k}_std": round(statistics.pstdev(xs), 4)}
    return {**out, "risk_present": modal, "risk_agreement": counts[0][1] / len(vals),
            "risk_counts": dict(counts), "distinct_triples": len({(v["O"], v["S"], v["D"]) for v in vals})}


def categorize(det: dict[str, dict[str, Any]], llm: dict[str, dict[str, Any]], dim: str) -> str:
    """Pre-registered disagreement category for one packet x dimension (first that applies)."""
    d, ll = det[dim], llm[dim]
    if ll["risk_present"] is None:
        return "parser_format_failure" if ll.get("parse_failures") else "truncation_fallback"
    if (d["risk_present"] == "UNCERTAIN") != (ll["risk_present"] == "UNCERTAIN"):
        return "insufficient_evidence"
    if d["risk_present"] != ll["risk_present"]:
        no_side, yes_side = (det, llm) if d["risk_present"] == "NO" else (llm, det)
        if any(o != dim and no_side[o]["risk_present"] == "YES" and yes_side[o]["risk_present"] != "YES"
               for o in no_side if o in yes_side):
            return "localization"
        return "evidence_interpretation"
    if d.get("S") is not None and ll.get("S") is not None and abs(d["S"] - ll["S"]) >= 2:
        return "severity"
    return "agree"


def _rate(xs: list[bool]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def compare(det: dict[str, dict[str, Any]], runs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows, loc = [], []
    for pid, drec in det.items():
        modal = {d.value: llm_modal(runs[pid], d.value) for d in DIMENSIONS}
        dd = drec["dimensions"]
        for d in DIMENSIONS:
            k = d.value
            rows.append({"packet_id": pid, "dimension": k, "deterministic": dd[k], "llm": modal[k],
                         "category": categorize(dd, modal, k)})
        if any(v["risk_present"] is None for v in modal.values()):
            continue  # no LLM answer for this packet: localization undefined
        det_set = {k for k, v in dd.items() if v["risk_present"] == "YES"}
        llm_set = {k for k, v in modal.items() if v["risk_present"] == "YES"}
        union = det_set | llm_set
        loc.append({"packet_id": pid, "deterministic": sorted(det_set), "llm": sorted(llm_set),
                    "exact": det_set == llm_set, "jaccard": round(len(det_set & llm_set) / len(union), 4) if union else 1.0})
    both = [r for r in rows if r["llm"]["risk_present"] is not None]
    definite = [r for r in both if "UNCERTAIN" not in (r["deterministic"]["risk_present"], r["llm"]["risk_present"])]
    with_s = [r for r in both if r["deterministic"]["S"] is not None]
    all_runs = [r for rs in runs.values() for r in rs]
    ok_runs = [r for r in all_runs if not r["fallback"]]
    rep = [r for r in both if r["llm"]["valid_runs"] >= 2]  # a single answer says nothing about repeatability
    variation: dict[str, Any] = {}
    for d in DIMENSIONS:
        by_provider: dict[str, list[dict[str, Any]]] = {}
        for r in ok_runs:
            by_provider.setdefault(r["provider"], []).append(r["dimensions"][d.value])
        variation[d.value] = {pv: {"n": len(v), **{f"{k}_mean": round(statistics.fmean(x[k] for x in v), 4) for k in "OSD"}}
                              for pv, v in sorted(by_provider.items())}
    per_dim = {}
    for d in DIMENSIONS:
        sub = [r for r in both if r["dimension"] == d.value]
        per_dim[d.value] = {
            "n": len(sub), "status_agreement": _rate([r["deterministic"]["risk_present"] == r["llm"]["risk_present"] for r in sub]),
            "det_yes": sum(r["deterministic"]["risk_present"] == "YES" for r in sub),
            "det_uncertain": sum(r["deterministic"]["risk_present"] == "UNCERTAIN" for r in sub),
            "llm_yes": sum(r["llm"]["risk_present"] == "YES" for r in sub),
        }
    return {
        "rows": rows, "localization": loc, "per_dimension": per_dim,
        "summary": {
            "packet_dimension_pairs": len(rows), "llm_answered_pairs": len(both),
            "exact_status_agreement": _rate([r["deterministic"]["risk_present"] == r["llm"]["risk_present"] for r in both]),
            "risk_present_agreement_definite": _rate([r["deterministic"]["risk_present"] == r["llm"]["risk_present"]
                                                      for r in definite]),
            "n_definite_pairs": len(definite),
            "localization_exact_match": _rate([x["exact"] for x in loc]),
            "localization_mean_jaccard": round(statistics.fmean(x["jaccard"] for x in loc), 4) if loc else None,
            "severity_exact": _rate([r["deterministic"]["S"] == r["llm"]["S"] for r in with_s]),
            "severity_within_1": _rate([abs(r["deterministic"]["S"] - r["llm"]["S"]) <= 1 for r in with_s]),
            "severity_mae": round(statistics.fmean(abs(r["deterministic"]["S"] - r["llm"]["S"]) for r in with_s), 4)
            if with_s else None,
            "osd_exact_triple": _rate([all(r["deterministic"][k] == r["llm"][k] for k in "OSD") for r in with_s]),
            **{f"{k}_mae": round(statistics.fmean(abs(r["deterministic"][k] - r["llm"][k]) for r in with_s), 4)
               if with_s else None for k in "OSD"},
            "det_uncertain_pairs": sum(r["deterministic"]["risk_present"] == "UNCERTAIN" for r in rows),
            "llm_uncertain_pairs_modal_tie": sum(r["llm"]["risk_present"] == "UNCERTAIN" for r in rows),
            "categories": dict(Counter(r["category"] for r in rows)),
            "det_ms_per_packet_mean": round(statistics.fmean(v["elapsed_ms"] for v in det.values()), 3),
            "llm_s_per_call_mean": round(statistics.fmean(r["elapsed_s"] for r in all_runs), 3) if all_runs else None,
            "llm_s_per_successful_call_mean": round(statistics.fmean(r["elapsed_s"] for r in ok_runs), 3)
            if ok_runs else None,
            "provider_variation": variation,
            "llm_runs": len(all_runs), "llm_fallbacks": sum(r["fallback"] for r in all_runs),
            "llm_parse_failures": sum(r["parse_failures"] for r in all_runs),
            "llm_fallbacks_provider_unavailable": sum(r["provider_unavailable"] for r in all_runs),
            "llm_superseded_attempt_records": sum(r["superseded_attempt_records"] for r in all_runs),
            "llm_output_truncated": sum(r["output_truncated"] for r in all_runs),
            "llm_prompt_truncated": sum(r["prompt_truncated"] for r in all_runs),
            "llm_replayed_runs": sum(r["replayed"] for r in all_runs),
            "llm_providers": dict(Counter(r["provider"] or "none" for r in all_runs)),
            "llm_repeatability_pairs": len(rep),
            "llm_risk_repeatable_pairs": sum(r["llm"].get("risk_agreement") == 1.0 for r in rep),
            "llm_osd_repeatable_pairs": sum(r["llm"].get("distinct_triples") == 1 for r in rep),
            "llm_mean_risk_agreement": round(statistics.fmean(r["llm"]["risk_agreement"] for r in rep), 4) if rep else None,
            **{f"llm_mean_{k}_range": round(statistics.fmean(r["llm"][f"{k}_range"] for r in rep), 4) if rep else None
               for k in "OSD"},
        },
    }


def attempt_stats(path: Path) -> dict[str, dict[str, int]]:
    """Every provider attempt in the response log (superseded records included): ok or error type."""
    stats: dict[str, Counter[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        for a in json.loads(line)["attempts"]:
            c = stats.setdefault(a["provider"], Counter(ok=0))
            c["ok" if "raw" in a else a["error"].split(":")[0]] += 1
    return {k: dict(v) for k, v in sorted(stats.items())}


def _behaviors() -> dict[str, dict[str, Any]]:
    rows = json.loads(L6_ANALYSIS.read_text(encoding="utf-8"))["safety"]
    return {r["model"]: {"status": r["behavior_status"], **{k: r[k] for k in _BEHAVIOR_KEYS}} for r in rows}


def build_packets(models_dir: Path = SUITE_DIR / "models") -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    behaviors = _behaviors()
    packets, sources = {}, {}
    for i, name in enumerate(PACKET_MODELS, 1):
        pid = f"P{i:02d}"
        src = MANIFEST_SOURCE.get(name)
        packets[pid] = build_packet(pid, models_dir / name,
                                    behavior=behaviors.get(name, {"status": ProbeEvaluationStatus.NOT_APPLICABLE.value}),
                                    manifest=build_artifact_manifest(models_dir / src) if src else None)
        sources[pid] = name
    return packets, sources


def _markdown(cmp: dict[str, Any], sources: dict[str, str]) -> str:
    s = cmp["summary"]
    lines = ["# L2 — deterministic vs LLM interpretation (same frozen evidence)", "",
             f"Prompt {PROMPT_VERSION} (unchanged); deterministic O/S/D = v3 HeuristicOSDAgent.", "",
             "## Summary", "", "```json", json.dumps(s, indent=2), "```", "",
             "## Per dimension", "", "```json", json.dumps(cmp["per_dimension"], indent=2), "```", "",
             "## Packet x dimension", "",
             "| packet | source | dim | det risk | det suff | det O/S/D | llm risk (agree) | llm O/S/D (ranges) | category |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in cmp["rows"]:
        d, ll = r["deterministic"], r["llm"]
        rng = "/".join(str(ll.get(f"{k}_range", "—")) for k in "OSD")
        lines.append(f"| {r['packet_id']} | {sources[r['packet_id']]} | {r['dimension']} | {d['risk_present']} | "
                     f"{d['evidence_sufficient']} | {d['O']}/{d['S']}/{d['D']} | {ll['risk_present']} "
                     f"({ll.get('risk_agreement', '—')}) | {ll['O']}/{ll['S']}/{ll['D']} ({rng}) | {r['category']} |")
    lines += ["", "## Localization", "", "| packet | det flagged | llm flagged | exact | jaccard |", "|---|---|---|---|---|"]
    lines += [f"| {x['packet_id']} | {x['deterministic']} | {x['llm']} | {x['exact']} | {x['jaccard']} |"
              for x in cmp["localization"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--runs", type=int, default=RUNS)
    ap.add_argument("--resume", action="store_true", help="continue live runs into an existing --out")
    ap.add_argument("--replay", action="store_true", help="re-analyse stored responses, no API calls")
    ap.add_argument("--retry-fallbacks", action="store_true",
                    help="with --resume: re-attempt runs where every provider was unavailable (quota/outage)")
    args = ap.parse_args(argv)
    if args.resume or args.replay:
        out = args.out.resolve()
    else:
        out = validate_out_dir(args.out)
        out.mkdir(parents=True)
    packets, sources = build_packets()
    index = {pid: packet_sha256(p) for pid, p in packets.items()}
    index_path = out / "packet_index.json"
    if index_path.exists():
        frozen = json.loads(index_path.read_text(encoding="utf-8"))
        if frozen != index:
            raise RuntimeError("packets differ from the frozen packet_index.json")
    else:
        (out / "packets").mkdir()
        for pid, p in packets.items():
            (out / "packets" / f"{pid}.json").write_text(json.dumps(p, indent=2), encoding="utf-8")
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        # Evaluators never read this file.
        (out / "packet_sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")

    det = {pid: deterministic_eval(p) for pid, p in packets.items()}
    (out / "deterministic.json").write_text(json.dumps(det, indent=2), encoding="utf-8")
    store = ResponseStore(out / "llm_responses.jsonl")
    runs: dict[str, list[dict[str, Any]]] = {}
    for pid, p in packets.items():
        runs[pid] = []
        for i in range(1, args.runs + 1):
            r = llm_run(p, i, store, replay=args.replay, retry_fallbacks=args.retry_fallbacks)
            runs[pid].append(r)
            print(pid, i, r["provider"], "fallback" if r["fallback"] else "ok", r["elapsed_s"], flush=True)
    (out / "llm_runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    hashes_match = all(det[pid]["packet_sha256"] == index[pid] == r["packet_sha256"]
                       for pid, rs in runs.items() for r in rs)
    cmp = compare(det, runs)
    cmp["packet_hashes_identical_across_evaluators"] = hashes_match
    cmp["prompt_version"] = PROMPT_VERSION
    cmp["provider_attempts"] = attempt_stats(out / "llm_responses.jsonl")
    (out / "analysis.json").write_text(json.dumps(cmp, indent=2), encoding="utf-8")
    (out / "analysis.md").write_text(_markdown(cmp, sources), encoding="utf-8")
    print(json.dumps(cmp["summary"], indent=2))


if __name__ == "__main__":
    main()
