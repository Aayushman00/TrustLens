"""Round 3 / L3 replay: control flag rates before vs after the disclosure-gap split.

No new experiment. For each model in the frozen run directories it
- takes the stored (v3-hardening-2026 / probe v1.0) probe evidence as "before";
- re-runs the v1.1 card/identity evaluators on the exact same inputs as "after":
  local card README, the license recorded in the stored integrity evidence,
  the real local weight file (+ train_manifest.json), or for Hub models the
  model card at the pinned revision, verified against the stored
  documentation_content_hash;
- applies the frozen evidence-level rule (compare_ground_truth.evidence_flag_one)
  unchanged, with the stored behavioural safety evidence.

Every input file is recorded with its sha256. Read-only on results/; output
goes to a fresh directory.

Usage (from backend/)::
    python -m app.scripts.replay_l3_disclosure_gaps <new_out_dir>
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.probes import explainability_stats, integrity_stats, safety_stats
from app.probes.explainability_eval import evaluate_explainability
from app.probes.integrity_artifact import local_weight_hashes
from app.probes.integrity_eval import evaluate_integrity
from app.probes.safety_eval import evaluate_safety
from app.scoring.methodology_version import CURRENT_METHODOLOGY_VERSION
from app.scripts.compare_ground_truth import CONTROL, _load_runs, _probe_metrics, evidence_flag_one
from app.scripts.run_flawed_suite_eval import SUITE_DIR, WORKER_MODEL_ROOT, fresh_out_dir

DIMS = ("SAFETY", "EXPLAINABILITY", "INTEGRITY")
# The run directories behind final_20261002_analysis_with_sweep/analysis.md.
FROZEN_RUN_DIRS = [
    "final_20261002_repeat5", "final_20261002_repeat5_part2",
    "final_20261002_repeat5_part3a", "final_20261002_repeat5_part3b",
    "sweep_20261002_sweep_fairness_r020", "sweep_20261002_sweep_fairness_r070",
    "sweep_20261002_sweep_fairness_r100", "sweep_20261002_sweep_safety_r025",
    "sweep_20261002_sweep_safety_r075", "sweep_20261002_sweep_safety_r100",
]
BEFORE = {"methodology_version": "v3-hardening-2026", "tl-safety": "tl-safety-v1.0",
          "tl-explainability": "tl-explainability-v1.0", "tl-integrity": "tl-integrity-v1.0",
          "source": "stored probe evidence in the run directories"}
AFTER = {"methodology_version": CURRENT_METHODOLOGY_VERSION, "tl-safety": safety_stats.METHODOLOGY_VERSION,
         "tl-explainability": explainability_stats.METHODOLOGY_VERSION,
         "tl-integrity": integrity_stats.METHODOLOGY_VERSION,
         "source": "v1.1 evaluators re-run offline on the same inputs"}

HubCardLoader = Callable[[str, str], bytes]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pinned_hub_card(repo: str, revision: str) -> bytes:
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download(repo, "README.md", revision=revision)).read_bytes()


def _card(suite: Path, model: str, stored: dict[str, Any], loader: HubCardLoader) -> tuple[str, dict[str, Any]]:
    doc = stored.get("documentation_source") or {}
    if doc.get("retrieval_status") == "ok":
        repo, rev = doc["source_model_ref"], doc["documentation_revision"]
        data = loader(repo, rev)
        want = str(doc["documentation_content_hash"]).removeprefix("sha256:")
        if _sha256(data) != want:
            raise ValueError(f"{model}: Hub card {repo}@{rev} hash {_sha256(data)} != stored {want}")
        return data.decode("utf-8"), {"source": f"hub:{repo}@{rev}", "sha256": want}
    path = suite / "cards" / model / "README.md"
    if not path.exists():
        path = suite / "models" / model / "README.md"
    data = path.read_bytes()
    return data.decode("utf-8"), {"source": path.relative_to(suite).as_posix(), "sha256": _sha256(data)}


def _replay_model(suite: Path, model: str, ev: dict[str, Any], control_fnr: float | None,
                  loader: HubCardLoader) -> dict[str, Any]:
    pm = _probe_metrics(ev)
    card_text, card_input = _card(suite, model, pm["SAFETY"], loader)
    lic = (pm["INTEGRITY"].get("disclosure") or {}).get("license_structured")
    meta: dict[str, Any] = {"card_text": card_text, "card_data": {"license": lic} if lic else {}}
    inputs: dict[str, Any] = {"card": card_input, "license": lic}

    if card_input["source"].startswith("hub:"):
        # Hub identity is re-evaluated from the stored snapshot; the live
        # listing re-check is not replayed (drift is a risk, not a gap).
        ident = pm["INTEGRITY"].get("identity") or {}
        extra = {k: ident[k] for k in ("trusted_reference",) if ident.get(k)}
        if ident.get("weight_hash"):
            extra["local_artifact_hash"] = ident["weight_hash"]
        integ = evaluate_integrity(model_ref=card_input["source"].split("@")[0][4:], model_revision=ident.get("revision"),
                                   model_metadata={**meta, "files": ident.get("hub_files") or []}, integrity_extra=extra)
        inputs["identity"] = "stored integrity identity snapshot"
    else:
        hashes = local_weight_hashes(str(suite / "models" / model))
        integ = evaluate_integrity(model_ref=f"{WORKER_MODEL_ROOT}/{model}", model_revision="local",
                                   model_metadata=meta, integrity_extra=hashes)
        inputs["weights"] = {"file": f"models/{model}/{hashes['file']}",
                             "sha256": hashes["local_artifact_hash"]["value"],
                             "train_manifest_sha256": (hashes.get("trusted_reference") or {}).get("value")}

    s = evaluate_safety(model_metadata=meta)
    x = evaluate_explainability(model_metadata=meta)
    after_metrics = {
        "SAFETY": {"risks_triggered": s.risks_triggered, "aspect_scoring": s.aspect_scoring,
                   "behavior": pm["SAFETY"].get("behavior")},
        "EXPLAINABILITY": {"risks_triggered": x.risks_triggered, "aspect_scoring": x.aspect_scoring},
        "INTEGRITY": {"risks_triggered": integ.risks_triggered, "aspect_scoring": integ.aspect_scoring},
    }
    gaps = {"SAFETY": s.disclosure_gaps, "EXPLAINABILITY": x.disclosure_gaps, "INTEGRITY": integ.disclosure_gaps}
    return {
        "inputs": inputs,
        "coverage_reproduced": (pm["SAFETY"].get("coverage_ratio"), pm["EXPLAINABILITY"].get("coverage_ratio"))
        == (s.coverage_ratio, x.coverage_ratio),
        "before": {d: evidence_flag_one(d, pm[d], control_fnr) for d in DIMS},
        "after": {d: evidence_flag_one(d, after_metrics[d], control_fnr) for d in DIMS},
        "risks_after": {d: after_metrics[d]["risks_triggered"] for d in DIMS},
        "disclosure_gaps_after": gaps,
        "identity": {"hash_comparison": integ.identity["hash_comparison"]},
    }


def replay(suite: Path, run_dirs: list[Path], hub_card_loader: HubCardLoader = _pinned_hub_card) -> dict[str, Any]:
    truth = json.loads((suite / "ground_truth.json").read_text(encoding="utf-8"))
    controls = list(truth.get("controls") or [CONTROL])
    runs = {m: [e for e in evs if e.get("status") == "FINALIZED"] for m, evs in _load_runs(run_dirs).items()}
    fnr_model = CONTROL if CONTROL in runs else controls[0]
    fnrs = [(_probe_metrics(e).get("SAFETY", {}).get("behavior") or {}).get("severe_fnr") for e in runs.get(fnr_model, [])]
    fnrs = [f for f in fnrs if f is not None]
    control_fnr = statistics.fmean(fnrs) if fnrs else None

    # Card/identity evidence is deterministic per model, so the first finalized run stands for all.
    models = {m: _replay_model(suite, m, evs[0], control_fnr, hub_card_loader) for m, evs in sorted(runs.items()) if evs}
    ctrl = [models[m] for m in controls if m in models]
    rate = {d: {k: sum(r[k][d] for r in ctrl) / len(ctrl) if ctrl else None for k in ("before", "after")} for d in DIMS}
    detection = {}
    for d in DIMS:
        others = [m for m in models if m not in controls]
        inj = [m for m in others if d in truth["models"].get(m, {}).get("injected_defects", [])]
        clean = [m for m in others if m not in inj]
        detection[d] = {f"{k}_{w}": [sum(models[m][w][d] for m in group), len(group)]
                        for k, group in (("recall", inj), ("non_injected_flags", clean)) for w in ("before", "after")}
    return {
        "inputs": {"suite_dir": suite.name, "ground_truth": "ground_truth.json",
                   "ground_truth_sha256": _sha256((suite / "ground_truth.json").read_bytes()),
                   "run_dirs": [d.name for d in run_dirs], "controls": controls,
                   "control_severe_fnr_model": fnr_model, "control_severe_fnr_mean": control_fnr,
                   "rule": "compare_ground_truth.evidence_flag_one (frozen evidence-level rule, unchanged)"},
        "methodology": {"before": BEFORE, "after": AFTER},
        "control_flag_rate": rate,
        "detection": detection,
        "models": models,
    }


def to_markdown(r: dict[str, Any]) -> str:
    f = lambda x: "—" if x is None else f"{x:.2f}"  # noqa: E731
    frac = lambda p: f"{p[0]}/{p[1]}"  # noqa: E731
    b, a = r["methodology"]["before"], r["methodology"]["after"]
    out = ["# L3 replay: control flag rate before vs after the disclosure-gap split", "",
           f"Before: `{b['methodology_version']}` ({b['tl-safety']}, {b['tl-explainability']}, {b['tl-integrity']}), {b['source']}.",
           f"After: `{a['methodology_version']}` ({a['tl-safety']}, {a['tl-explainability']}, {a['tl-integrity']}), {a['source']}.",
           f"Rule: {r['inputs']['rule']}. Ground truth sha256 `{r['inputs']['ground_truth_sha256']}`.",
           f"Runs: {', '.join(r['inputs']['run_dirs'])}.", "",
           "| dimension | control flag rate before | after | injected recall before | after | non-injected flags before | after |",
           "|---|---|---|---|---|---|---|"]
    for d in DIMS:
        c, t = r["control_flag_rate"][d], r["detection"][d]
        out.append(f"| {d} | {f(c['before'])} | {f(c['after'])} | {frac(t['recall_before'])} | {frac(t['recall_after'])} | "
                   f"{frac(t['non_injected_flags_before'])} | {frac(t['non_injected_flags_after'])} |")
    out += ["", "| model | flagged before | flagged after | coverage reproduced | card input | weights / identity |",
            "|---|---|---|---|---|---|"]
    for m, v in r["models"].items():
        flags = lambda w: ", ".join(d for d in DIMS if v[w][d]) or "—"  # noqa: E731
        w = v["inputs"].get("weights")
        ident = f"`{w['file']}` {w['sha256'][:12]}… ({v['identity']['hash_comparison']})" if w else v["inputs"]["identity"]
        out.append(f"| {m} | {flags('before')} | {flags('after')} | {v['coverage_reproduced']} | "
                   f"`{v['inputs']['card']['source']}` {v['inputs']['card']['sha256'][:12]}… | {ident} |")
    return "\n".join(out) + "\n"


def main() -> None:
    out_dir = fresh_out_dir(SUITE_DIR / sys.argv[1])
    r = replay(SUITE_DIR, [SUITE_DIR / d for d in FROZEN_RUN_DIRS])
    (out_dir / "replay.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    (out_dir / "replay.md").write_text(to_markdown(r), encoding="utf-8")
    print(to_markdown(r))


if __name__ == "__main__":
    main()
