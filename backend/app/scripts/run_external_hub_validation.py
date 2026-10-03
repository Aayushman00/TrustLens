"""External validation: audit deliberately selected, revision-pinned Hugging Face
text-classification models with the current TrustLens methodology, unchanged.

Descriptive audit profiles only: no ranking, no trustworthy/untrustworthy label
(no ground truth exists for these models). Evaluations go through the running
stack (``docker compose up``; images rebuilt from the commit recorded in the
output) with the same contract as the suite runs
(``run_flawed_suite_eval.create_and_run_evaluation``), one model at a time.

Usage (from backend/)::

    python -m app.scripts.run_external_hub_validation select   # pin + verify revisions, write selection.json
    python -m app.scripts.run_external_hub_validation run      # sequential evaluations
    python -m app.scripts.run_external_hub_validation profile  # profiles.json, PROFILES.md, SHA256SUMS
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.scripts import run_flawed_suite_eval as r
from app.scripts.extra_models_eval import positive_output

OUT = r.REPO_ROOT / "results" / "external_hub_validation_20261003"
# Fixed before any evaluation. Each model is chosen for one property that varies
# across the set; the order is the selection order, not a ranking.
SELECTION = (
    ("unitary/toxic-bert", "4d6c22e74ba2fdd26bc4f7238f50766b045a0d94",
     "widely used multi-label Jigsaw classifier (BERT-base); toxicity head of a 6-label output"),
    ("unitary/unbiased-toxic-roberta", "36295dd80b422dc49f40052021430dae76241adc",
     "multi-label model trained on Civil Comments with identity-bias mitigation (fairness-relevant claim)"),
    ("s-nlp/roberta_toxicity_classifier", "048c25bb1e199b98802784f96325f4840f22145d",
     "binary RoBERTa-large classifier from a research group (Jigsaw data)"),
    ("martin-ha/toxic-comment-model", "9842c08b35a4687e7b211187d676986c8c96256d",
     "small binary DistilBERT fine-tune by an individual author; no license in card metadata"),
    ("textdetox/xlmr-large-toxicity-classifier", "b9c7c563427c591fc318d91eb592381ae2fbde66",
     "multilingual XLM-R large binary classifier (9 declared languages incl. en)"),
    ("facebook/roberta-hate-speech-dynabench-r4-target", "391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6",
     "hate-speech (not general toxicity) model, adversarially collected data: label-scope mismatch with the task"),
    ("gravitee-io/bert-tiny-toxicity", "8377eb9a344d74b9d12e656dc3f3632b74f33673",
     "very small (bert-tiny, ~17 MB) multilingual binary classifier: low-capacity end"),
)
TASK = "Binary toxicity classification of English comments (suite eval_set.csv: Civil Comments, identity_ref, severe)."


def _write(path: Path, obj: Any) -> None:
    text = obj if isinstance(obj, str) else json.dumps(obj, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")  # LF on every OS: SHA256SUMS must match a checkout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select() -> None:
    from huggingface_hub import HfApi
    from transformers import AutoConfig

    out = r.fresh_out_dir(OUT)
    api = HfApi()
    models = []
    for repo, sha, why in SELECTION:
        info = api.model_info(repo, revision=sha, files_metadata=True)
        if info.sha != sha:
            raise RuntimeError(f"{repo}: pinned {sha} resolved to {info.sha}")
        cfg = AutoConfig.from_pretrained(repo, revision=sha)
        labels = {int(k): str(v) for k, v in (cfg.id2label or {}).items()}
        idx, mode = positive_output(labels, getattr(cfg, "problem_type", None))
        if idx is None:
            raise RuntimeError(f"{repo}: {mode}")
        card = info.card_data.to_dict() if info.card_data else {}
        models.append({
            "repo": repo, "revision": sha, "selection_reason": why,
            "architectures": cfg.architectures, "model_type": cfg.model_type, "id2label": labels,
            "positive_index": idx, "head": mode, "license": card.get("license"), "language": card.get("language"),
            "downloads_at_selection": info.downloads,
            "weights": [{"file": s.rfilename, "size": s.size, "lfs_sha256": s.lfs.sha256 if s.lfs else None}
                        for s in info.siblings or [] if s.rfilename.endswith((".safetensors", ".bin"))],
        })
    _write(out / "selection.json", {
        "selected_at": datetime.now(UTC).isoformat(), "task": TASK,
        "rule": "deliberate selection for spread (architecture, size, head type, training data, label scope, "
                "documentation, language scope); fixed before any evaluation; not a sample of the Hub, not a ranking",
        "models": models,
    })
    print(f"{len(models)} models pinned and verified -> {out / 'selection.json'}")


def _stack_info(c: Any) -> dict[str, Any]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=r.REPO_ROOT).stdout.strip()
    images = {}
    for svc in ("api", "worker"):
        res = subprocess.run(["docker", "compose", "images", svc, "--format", "json"], capture_output=True, text=True,
                             cwd=r.REPO_ROOT)
        images[svc] = res.stdout.strip() or res.stderr.strip()
    health = c.get("/health") if hasattr(c, "get") else None
    return {"git_head": head, "images": images,
            "api_health": health.json() if health is not None and health.status_code == 200 else None}


def run() -> None:
    sel = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
    evals = OUT / "evaluations"
    evals.mkdir(exist_ok=False)
    log: list[dict[str, Any]] = []
    with r._client() as c:
        stack = _stack_info(c)
        ds = r.upload_eval_dataset(c)
        for m in sel["models"]:  # sequential: one model loaded in the worker at a time
            row: dict[str, Any] = {"repo": m["repo"], "revision": m["revision"], "started_at": datetime.now(UTC).isoformat()}
            t0 = time.perf_counter()
            try:
                resp = c.post("/models/import-hf", json={"repo_id": m["repo"], "revision": m["revision"]})
                resp.raise_for_status()
                model = resp.json()
                row["model_id"] = model["id"]
                k = m["positive_index"] if m["head"] == "multi_label" else None
                pos = 1 if k is not None else m["positive_index"]
                ev = r.create_and_run_evaluation(c, model["id"], ds, multilabel_target_index=k, positive_index=pos)
                row.update({"evaluation_id": ev["id"], "status": ev["status"], "model_revision": ev.get("model_revision")})
                _write(evals / f"{m['repo'].replace('/', '__')}.json", ev)
            except Exception as exc:  # noqa: BLE001 — an operational failure is a result too
                row.update({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"[:500]})
            row["elapsed_s"] = round(time.perf_counter() - t0, 1)
            log.append(row)
            print(row["repo"], row["status"], row["elapsed_s"], flush=True)
    _write(OUT / "run_log.json", {"stack": stack, "dataset_content_id": ds, "runs": log})


# --- descriptive profiles ------------------------------------------------------------


def _pick(d: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: d.get(k) for k in keys if k in d}


_COMMON = ("probe_status", "aspect_scoring", "scored_risk_id", "risks_triggered", "disclosure_gaps")
_METRICS = {
    "FAIRNESS": ("n_evaluated", "equal_opportunity_difference", "eopp_ci", "equalized_odds_difference", "eo_ci",
                 "demographic_parity_difference", "label_rate_gap", "excess_dpd", "subgroup_f1_spread",
                 "fairness_finding"),
    "ROBUSTNESS": ("n_evaluated", "clean_accuracy", "robust_accuracy", "accuracy_drop", "attack_success_rate",
                   "perturbation_coverage", "max_changes"),
    "SAFETY": ("severe_fnr", "fnr_ratio", "coverage_ratio", "checks_present", "high_impact_claims"),
    "INTEGRITY": (),
    "EXPLAINABILITY": ("coverage_ratio", "sections_present", "contradictions", "card_chars", "documentation_source"),
}


def profile_one(ev: dict[str, Any]) -> dict[str, Any]:
    probes = {p["dimension"]: p for p in ev.get("probes") or []}
    aspects = {a.get("aspect"): a for a in ((ev.get("osd_agent") or {}).get("ai_suggestion") or {}).get("aspects") or []}
    dims: dict[str, Any] = {}
    for dim, keys in _METRICS.items():
        p = probes.get(dim) or {}
        mv = p.get("metric_values") or {}
        a = aspects.get(dim) or {}
        d = {"status": p.get("status"), **_pick(mv, _COMMON), **_pick(mv, keys),
             "failed_gates": (mv.get("reliability") or {}).get("failed_gates"),
             "flags": mv.get("flags"),
             "osd": {k: a.get(k) for k in ("O", "S", "D")},
             "osd_source": a.get("O_source"), "osd_provider": (a.get("osd_metadata") or {}).get("llm_provider")}
        if dim == "SAFETY":
            d["behavior"] = _pick(mv.get("behavior") or {}, ("status", "severe_n", "severe_fnr", "severe_fnr_ci",
                                                              "overall_fnr", "harmful_recall", "benign_fpr", "fnr_ratio"))
        if dim == "INTEGRITY":
            ident = mv.get("identity") or {}
            d["identity"] = _pick(ident, ("revision_pinned", "hash_comparison", "resolved_sha", "listing_verified"))
            d["artifact_verification_status"] = (mv.get("artifact_verification") or {}).get("status")
        dims[dim] = d
    fs = ev.get("final_score") or {}
    md = ev.get("mode_disclosure") or {}
    return {"status": ev.get("status"), "model_revision": ev.get("model_revision"),
            "trustlens_version": ev.get("trustlens_version"),
            "methodology_status": md.get("methodology_status"), "assessment_engine": md.get("assessment_engine"),
            "fries_status": md.get("fries_status"), "fries_score_as_reported": fs.get("fries_score"),
            "dimension_scores_as_reported": fs.get("dimension_scores"), "dimensions": dims}


def _md(sel: dict[str, Any], profiles: dict[str, Any], log: dict[str, Any]) -> str:
    lines = ["# External Hub validation — descriptive audit profiles (2026-10-03)", "",
             "Descriptive only. **No ranking and no trustworthy/untrustworthy label**: there is no ground truth for",
             "these models, and the FRIES numbers are TrustLens's own outputs, reproduced as reported. Models are",
             "listed in selection order. Methodology unchanged; see `README.md` for the protocol.", ""]
    for m in sel["models"]:
        p = profiles.get(m["repo"])
        lines += [f"## {m['repo']} @ `{m['revision'][:12]}`", "", f"Selected for: {m['selection_reason']}.", ""]
        if p is None:
            run = next((x for x in log["runs"] if x["repo"] == m["repo"]), {})
            lines += [f"**No evaluation output** — {run.get('status')}: {run.get('error')}", ""]
            continue
        lines += [f"- run status {p['status']}; revision evaluated `{p['model_revision']}`; engine "
                  f"{p['assessment_engine']} ({p['methodology_status']}); FRIES {p['fries_status']}",
                  "", "| dimension | probe | aspect scoring | risks | gaps | O/S/D (source) | key evidence |",
                  "|---|---|---|---|---|---|---|"]
        for dim, d in p["dimensions"].items():
            ev = {k: v for k, v in d.items() if k not in ("status", "probe_status", "aspect_scoring", "risks_triggered",
                                                         "disclosure_gaps", "osd", "osd_source", "osd_provider",
                                                         "scored_risk_id", "flags", "failed_gates")}
            osd = "/".join(str(d["osd"].get(k)) for k in "OSD")
            lines.append(f"| {dim} | {d.get('status')} | {d.get('aspect_scoring')} | {d.get('risks_triggered')} | "
                         f"{d.get('disclosure_gaps')} | {osd} ({d.get('osd_source')}"
                         f"{', ' + d['osd_provider'] if d.get('osd_provider') else ''}) | "
                         f"`{json.dumps(ev, separators=(',', ':'))}` |")
        lines += ["", f"FRIES as reported: {p['fries_score_as_reported']}; per dimension "
                      f"`{json.dumps(p['dimension_scores_as_reported'])}`", ""]
    return "\n".join(lines) + "\n"


def profile() -> None:
    sel = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
    log = json.loads((OUT / "run_log.json").read_text(encoding="utf-8"))
    profiles: dict[str, Any] = {}
    checks: dict[str, Any] = {}
    for m in sel["models"]:
        f = OUT / "evaluations" / f"{m['repo'].replace('/', '__')}.json"
        if not f.exists():
            checks[m["repo"]] = {"evaluation_file": False}
            continue
        ev = json.loads(f.read_text(encoding="utf-8"))
        profiles[m["repo"]] = profile_one(ev)
        dims = {p["dimension"] for p in ev.get("probes") or []}
        checks[m["repo"]] = {"evaluation_file": True, "revision_matches_pin": ev.get("model_revision") == m["revision"],
                             "all_five_probes": dims == set(_METRICS), "status": ev.get("status")}
    _write(OUT / "profiles.json", {"note": "descriptive; no ranking; selection order", "completeness": checks,
                                   "profiles": profiles})
    _write(OUT / "PROFILES.md", _md(sel, profiles, log))
    files = sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    _write(OUT / "SHA256SUMS", "".join(f"{_sha256(p)}  ./{p.relative_to(OUT).as_posix()}\n" for p in files))
    print(json.dumps(checks, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["select", "run", "profile"])
    {"select": select, "run": run, "profile": profile}[ap.parse_args(argv).stage]()


if __name__ == "__main__":
    main()
