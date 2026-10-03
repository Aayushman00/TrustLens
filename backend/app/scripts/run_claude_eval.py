"""Supplemental L2/L10 review by Claude as an independent LLM evaluator (2026-10-03).

The API providers were unavailable, so Claude answered the *same frozen prompts*
the providers get: L2 prompt ``osd-llm-v3-decision-first-2026-10-03`` built from the
frozen L2 packets, L10 prompt ``l10-review-v1-2026-10-03`` on the frozen L10 packets.
Every prompt's sha256 is checked against the one the providers recorded. Answers are
parsed with the existing parsers and compared with the existing agreement code.
Nothing here changes TrustLens, the packets, or the official result folders, and
Claude's answers are never written into them.

Usage (from backend/)::

    python -m app.scripts.run_claude_eval export <prompt_dir>            # prompts only, no TrustLens answers
    python -m app.scripts.run_claude_eval analyze <prompt_dir> <response_dir> [--model ID]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.osd.llm_client import PROMPT_VERSION, build_prompt_with_truncation
from app.scripts import run_l2_interpretation as l2
from app.scripts import run_l10_validation as l10
from app.scripts.prepare_flawed_suite_data import REPO_ROOT, validate_out_dir

L2_SRC = REPO_ROOT / "results" / "l2_det_vs_llm_20261003"
L10_SRC = REPO_ROOT / "results" / "l10_independent_validation_20261003"
L2_OUT = REPO_ROOT / "results" / "l2_claude_eval_20261003"
L10_OUT = REPO_ROOT / "results" / "l10_claude_eval_20261003"
EVALUATOR = {"evaluator": "Claude", "evaluator_type": "independent_llm"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _frozen(folder: Path, index_name: str, key: str | None) -> dict[str, dict[str, Any]]:
    index = json.loads((folder / index_name).read_text(encoding="utf-8"))
    index = index[key] if key else index
    packets = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((folder / "packets").glob("*.json"))}
    if {k: l2.packet_sha256(v) for k, v in packets.items()} != index:
        raise RuntimeError(f"{folder.name}: packets differ from {index_name}")
    return packets


def l2_prompts() -> dict[str, str]:
    packets = _frozen(L2_SRC, "packet_index.json", None)
    recorded = {r["packet_id"]: r["prompt_sha256"] for rs in json.loads(
        (L2_SRC / "llm_runs.json").read_text(encoding="utf-8")).values() for r in rs}
    out = {}
    for pid, p in packets.items():
        prompt, _ = build_prompt_with_truncation(l2.llm_context(p))
        if _sha(prompt) != recorded[pid]:
            raise RuntimeError(f"L2 {pid}: prompt differs from the one the providers received")
        out[pid] = prompt
    return out


def l10_prompts() -> dict[str, str]:
    packets = _frozen(L10_SRC, "packet_hashes.json", "packets")
    recorded = {json.loads(x)["packet_id"]: json.loads(x)["prompt_sha256"]
                for x in (L10_SRC / "llm_reviews.jsonl").read_text(encoding="utf-8").splitlines()}
    out = {}
    for pid, p in packets.items():
        prompt = l10.review_prompt(p)
        if _sha(prompt) != recorded[pid]:
            raise RuntimeError(f"L10 {pid}: prompt differs from the one the providers received")
        out[pid] = prompt
    return out


def export(prompt_dir: Path) -> None:
    prompt_dir.mkdir(parents=True, exist_ok=False)
    for name, prompts in (("l2", l2_prompts()), ("l10", l10_prompts())):
        for pid, text in prompts.items():
            (prompt_dir / f"{name}_{pid}.txt").write_text(text, encoding="utf-8")
    print(f"exported {len(list(prompt_dir.iterdir()))} prompts -> {prompt_dir}")


def _response(response_dir: Path, name: str) -> str | None:
    path = response_dir / f"{name}.json"
    return path.read_text(encoding="utf-8") if path.exists() else None


def _record(pid: str, packet_sha: str, prompt: str, version: str, raw: str | None, model: str) -> dict[str, Any]:
    return {"packet_id": pid, "packet_sha256": packet_sha, **EVALUATOR, "model": model,
            "prompt_version": version, "prompt_sha256": _sha(prompt), "raw": raw,
            "recorded_at": datetime.now(UTC).isoformat()}


def _agree(a: list[Any], b: list[Any]) -> float | None:
    return round(sum(x == y for x, y in zip(a, b, strict=True)) / len(a), 4) if a else None


def analyze_l2(prompt_dir: Path, response_dir: Path, model: str) -> None:
    out = validate_out_dir(L2_OUT)
    out.mkdir(parents=True)
    packets = _frozen(L2_SRC, "packet_index.json", None)
    det = json.loads((L2_SRC / "deterministic.json").read_text(encoding="utf-8"))
    official = json.loads((L2_SRC / "llm_runs.json").read_text(encoding="utf-8"))
    records, runs = [], {}
    for pid, p in packets.items():
        prompt = (prompt_dir / f"l2_{pid}.txt").read_text(encoding="utf-8")
        raw = _response(response_dir, f"l2_{pid}")
        rec = _record(pid, l2.packet_sha256(p), prompt, PROMPT_VERSION, raw, model)
        dims, parse_error = None, None
        if raw is not None:
            try:
                judgment = l2.parse_gemini_response(raw)
                dims = {d.value: {**{k: (j := getattr(judgment, d.value).model_dump())[k]
                                     for k in ("O", "S", "D", "rationale", "content_quality")}, **l2.llm_fields(j)}
                        for d in l2.DIMENSIONS}
            except ValueError as exc:
                parse_error = str(exc)[:300]
        rec["parse_error"] = parse_error
        records.append(rec)
        runs[pid] = [{"packet_id": pid, "packet_sha256": rec["packet_sha256"], "run_index": 1, "replayed": False,
                      "provider": "claude" if dims else None, "model": model, "attempts": 1, "fallback": dims is None,
                      "parse_failures": int(parse_error is not None), "provider_unavailable": raw is None,
                      "superseded_attempt_records": 0, "output_truncated": False, "prompt_truncated": False,
                      "prompt_sha256": rec["prompt_sha256"], "elapsed_s": 0.0, "dimensions": dims}]
    cmp = l2.compare(det, runs)  # same agreement code as the official L2 analysis
    # The repeatability/latency fields are meaningless for one manual answer per packet.
    for k in [k for k in cmp["summary"] if k.startswith(("llm_s_", "llm_repeat", "llm_risk_rep", "llm_osd_rep",
                                                          "llm_mean_", "llm_replayed", "llm_superseded"))]:
        del cmp["summary"][k]
    # Claude vs the genuine provider answers in the official run (modal over valid runs).
    vs: list[dict[str, Any]] = []
    for pid, rs in official.items():
        for d in l2.DIMENSIONS:
            prov = l2.llm_modal(rs, d.value)
            cl = l2.llm_modal(runs[pid], d.value)
            if prov["risk_present"] is None or cl["risk_present"] is None:
                continue
            by_provider = Counter(r["provider"] for r in rs if not r["fallback"])
            vs.append({"packet_id": pid, "dimension": d.value, "provider_valid_runs": prov["valid_runs"],
                       "providers": dict(by_provider), "provider_modal": {k: prov[k] for k in ("risk_present", "O", "S", "D")},
                       "claude": {k: cl[k] for k in ("risk_present", "O", "S", "D")}})
    vs_summary = {
        "n_pairs": len(vs),
        "risk_present_agreement": _agree([x["provider_modal"]["risk_present"] for x in vs],
                                         [x["claude"]["risk_present"] for x in vs]),
        "osd_exact_triple": _agree([tuple(x["provider_modal"][k] for k in "OSD") for x in vs],
                                   [tuple(x["claude"][k] for k in "OSD") for x in vs]),
        **{f"{k}_mae": round(statistics.fmean(abs(x["provider_modal"][k] - x["claude"][k]) for x in vs), 4) if vs else None
           for k in "OSD"},
        "note": "provider side = modal (median_low O/S/D) over the official run's genuine answers; "
                "Gemini/Groq mixed per packet by the fallback chain",
    }
    meta = {**EVALUATOR, "model": model, "prompt_version": PROMPT_VERSION,
            "source": "results/l2_det_vs_llm_20261003 (frozen packets, deterministic.json, llm_runs.json; read-only)",
            "cases": f"{len(packets)} packets x {len(l2.DIMENSIONS)} dimensions = {len(packets) * len(l2.DIMENSIONS)}, "
                     "one Claude answer per packet (one prompt rates all three dimensions)",
            "answers": sum(r["dimensions"] is not None for rs in runs.values() for r in rs),
            "parse_failures": sum(r["parse_error"] is not None for r in records),
            "missing": sum(r["raw"] is None for r in records)}
    (out / "claude_responses.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    (out / "claude_runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    (out / "analysis.json").write_text(json.dumps({"meta": meta, "trustlens_deterministic_vs_claude": cmp,
                                                   "claude_vs_official_providers": {"summary": vs_summary, "pairs": vs}},
                                                  indent=2), encoding="utf-8")
    shutil.copytree(prompt_dir, out / "prompts", ignore=shutil.ignore_patterns("l10_*"))
    print(json.dumps({"meta": meta, "vs_trustlens": cmp["summary"], "vs_providers": vs_summary}, indent=2))


def analyze_l10(prompt_dir: Path, response_dir: Path, model: str) -> None:
    out = validate_out_dir(L10_OUT)
    out.mkdir(parents=True)
    packets = _frozen(L10_SRC, "packet_hashes.json", "packets")
    refs = json.loads((L10_SRC / "trustlens_reference.json").read_text(encoding="utf-8"))
    official: dict[str, dict[str, Any]] = {}
    for line in (L10_SRC / "llm_reviews.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec["answer"] is not None:
            official[rec["packet_id"]] = {**rec["answer"], "provider": rec["provider"], "model": rec["model"]}
    records, claude = [], {}
    for pid, p in packets.items():
        prompt = (prompt_dir / f"l10_{pid}.txt").read_text(encoding="utf-8")
        raw = _response(response_dir, f"l10_{pid}")
        rec = _record(pid, l10.packet_sha256(p), prompt, l10.L10_REVIEW_PROMPT_VERSION, raw, model)
        rec["answer"], rec["parse_error"] = None, None
        if raw is not None:
            try:
                rec["answer"] = l10._parse(raw)
            except ValueError as exc:
                rec["parse_error"] = str(exc)[:300]
        records.append(rec)
        claude[pid] = rec["answer"] or ({"parse_error": rec["parse_error"]} if rec["parse_error"] else None)
    tl = {pid: refs[pid] for pid in packets}
    pairs = {"trustlens_vs_claude": l10.pair_summary(tl, claude)}
    if official:
        pairs["official_llm_vs_claude"] = l10.pair_summary(
            {pid: official[pid] for pid in official}, {pid: claude[pid] for pid in official})
    layers = {pid: {"trustlens": {k: tl[pid][k] for k in ("risk_present", "risk_ids", "evidence_sufficient", "S")},
                    "claude": {k: (claude[pid] or {}).get(k) for k in ("risk_present", "dimension", "evidence_sufficient",
                                                                        "severity")},
                    "disagreement_layer": l10.disagreement_layer(tl[pid], claude[pid])} for pid in packets}
    meta = {**EVALUATOR, "model": model, "prompt_version": l10.L10_REVIEW_PROMPT_VERSION,
            "source": "results/l10_independent_validation_20261003 (frozen packets, trustlens_reference.json, "
                      "llm_reviews.jsonl; read-only)",
            "answers": sum(r["answer"] is not None for r in records),
            "parse_failures": sum(r["parse_error"] is not None for r in records),
            "missing": sum(r["raw"] is None for r in records),
            "official_provider_answers": {pid: f"{v['provider']} {v['model']}" for pid, v in official.items()},
            "human_reviews": "none collected; none fabricated"}
    (out / "claude_reviews.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    (out / "analysis.json").write_text(json.dumps({"meta": meta, "pairs": pairs, "layers": layers}, indent=2),
                                       encoding="utf-8")
    shutil.copytree(prompt_dir, out / "prompts", ignore=shutil.ignore_patterns("l2_*"))
    print(json.dumps({"meta": meta, **{k: {x: v[x] for x in v if x != "packets"} for k, v in pairs.items()}}, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export").add_argument("prompt_dir", type=Path)
    an = sub.add_parser("analyze")
    an.add_argument("prompt_dir", type=Path)
    an.add_argument("response_dir", type=Path)
    an.add_argument("--model", default="claude-opus-5-5")
    an.add_argument("--only", choices=["l2", "l10"])
    args = ap.parse_args(argv)
    if args.cmd == "export":
        export(args.prompt_dir)
        return
    if args.only in (None, "l2"):
        analyze_l2(args.prompt_dir, args.response_dir, args.model)
    if args.only in (None, "l10"):
        analyze_l10(args.prompt_dir, args.response_dir, args.model)


if __name__ == "__main__":
    main()
