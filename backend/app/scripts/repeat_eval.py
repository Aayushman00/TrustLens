"""Run each suite model N times and report mean/std per dimension (LLM noise).

Usage (from backend/, stack up)::
    python -m app.scripts.repeat_eval --runs 5 --out eval_results_repeat
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.scripts import run_flawed_suite_eval as r


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None}
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": statistics.fmean(values), "std": std, "min": min(values), "max": max(values)}


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [x for x in runs if x.get("status") == "FINALIZED" and x.get("fries_score") is not None]
    dims = sorted({d for x in ok for d in x["dimension_scores"]})
    return {
        "n_total": len(runs),
        "n_ok": len(ok),
        "n_failed": len(runs) - len(ok),
        "fries": _stats([x["fries_score"] for x in ok]),
        "dimensions": {
            d: _stats([x["dimension_scores"][d] for x in ok if d in x["dimension_scores"]])
            for d in dims
        },
    }


def run_once(
    evaluate: Any, client: Any, model_id: int, dataset_id: str, *, save_to: Path | None = None, **kwargs: Any
) -> dict[str, Any]:
    """One evaluation as a run record; an exception becomes status ERROR so a
    single timeout or HTTP failure never loses the other runs. ``save_to``
    keeps the full evaluation response (probe evidence, O/S/D, LLM metadata)."""
    try:
        ev = evaluate(client, model_id, dataset_id, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"[:500],
                "fries_score": None, "dimension_scores": {}}
    if save_to is not None:
        save_to.write_text(json.dumps(ev, indent=2), encoding="utf-8")
    fs = ev.get("final_score") or {}
    return {
        "evaluation_id": ev.get("id"),
        "status": ev["status"],
        "fries_score": fs.get("fries_score"),
        "dimension_scores": fs.get("dimension_scores") or {},
    }


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=r.REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", default="eval_results_repeat")
    ap.add_argument("--only", nargs="*", help="subset of target names")
    args = ap.parse_args()
    out = r.fresh_out_dir(r.SUITE_DIR / args.out)
    meta = {"code_commit": _git_commit(), "runs": args.runs, "started_at": datetime.now(UTC).isoformat()}
    with r._client() as c:
        ds = r.upload_eval_dataset(c)
        targets = [(v, r.register_local_model(c, v)) for v in r.LOCAL_VARIANTS]
        targets.append(("reference_hub", r.register_hf_model(c, r.TRUSTWORTHY_HF_REPO)))
        ref2 = r.SUITE_DIR / "models" / "reference_toxicbert_2label"
        if ref2.exists():
            from app.scripts.run_reference_2label_eval import NAME

            body = {
                "hf_repo_id": f"{r.WORKER_MODEL_ROOT}/{NAME}",
                "model_metadata": {
                    "card_text": (ref2 / "README.md").read_text(encoding="utf-8"),
                    "card_data": {"license": "apache-2.0"},
                },
                "revision": "local",
            }
            resp = c.post("/models", json=body)
            mid = (
                r._find_existing_model(c, body["hf_repo_id"])["id"]
                if resp.status_code == 409
                else resp.json()["id"]
            )
            targets.append((NAME, mid))
        summary: dict[str, Any] = {"_meta": meta}
        for name, mid in targets:
            if args.only and name not in args.only:
                continue
            kwargs = r.REFERENCE_EVAL_KWARGS if name == "reference_hub" else {}
            (out / "raw").mkdir(exist_ok=True)
            runs = [
                run_once(r.create_and_run_evaluation, c, mid, ds, save_to=out / "raw" / f"{name}__run{i + 1}.json", **kwargs)
                for i in range(args.runs)
            ]
            summary[name] = {"runs": runs, **summarize_runs(runs)}
            (out / f"{name}.json").write_text(json.dumps(summary[name], indent=2), encoding="utf-8")
    (out / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
