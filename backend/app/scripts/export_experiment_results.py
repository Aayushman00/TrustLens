"""Phase 25 export — build results/ CSVs from Postgres + the runner manifest.

Joins ``results/manifest_v1.jsonl`` (written by ``run_experiments``) with the
DB rows the pipeline persisted, and emits:

- ``results/mode_c_runs.csv``    — one row per Mode C run (raw results table)
- ``results/mode_c_summary.csv`` — per-model mean/std (repeatability) + determinism check
- ``results/mode_b_reviews.csv`` — one row per (assisted run, aspect): agent vs approved O/S/D

Usage (host or api container; DATABASE_URL is resolved like the test suite —
``@postgres:`` is retried as ``@127.0.0.1:`` when unreachable)::

    cd backend
    python -m app.scripts.export_experiment_results
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.db import get_session
from app.db.enums import FriesDimension
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.final_score import FinalScoreRepository
from app.db.repositories.human_review import HumanReviewRepository
from app.db.repositories.osd_agent_output import OsdAgentOutputRepository
from app.db.repositories.probe_result import ProbeResultRepository

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = REPO_ROOT / "results"
MANIFEST_PATH = RESULTS_DIR / "manifest_v1.jsonl"

ASPECTS = [d.value for d in FriesDimension]  # FAIRNESS, ROBUSTNESS, INTEGRITY, EXPLAINABILITY, SAFETY
DEFAULT_DB = "postgresql+psycopg2://trustlens:trustlens@127.0.0.1:5432/trustlens"


def _resolve_database_url() -> str:
    url = os.environ.get("DATABASE_URL") or get_settings().database_url or DEFAULT_DB
    candidates = [url]
    if "@postgres:" in url:
        # Host-side runs can't resolve the Compose service name — try the
        # published port first (the documented workflow), original second.
        candidates.insert(0, url.replace("@postgres:", "@127.0.0.1:"))
    for candidate in candidates:
        try:
            engine = create_engine(candidate, connect_args={"connect_timeout": 5})
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            return candidate
        except Exception:  # noqa: BLE001 — fall through to the next candidate
            continue
    raise SystemExit(f"cannot connect to Postgres — tried: {candidates}")


def _load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"manifest not found: {MANIFEST_PATH} — run run_experiments first")
    return [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _round(value: Any, digits: int = 4) -> Any:
    return round(value, digits) if isinstance(value, (int, float)) else value


def _osd_by_aspect(finalized_osd: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    if not finalized_osd:
        return {}
    return {a["aspect"]: a for a in finalized_osd.get("aspects", [])}


def _confidence_by_aspect(ai_suggestion: dict[str, Any] | None) -> dict[str, float]:
    if not ai_suggestion:
        return {}
    return {
        a["aspect"]: a["confidence"]
        for a in ai_suggestion.get("aspects", [])
        if a.get("confidence") is not None
    }


def _mode_c_rows(session: Any, manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    entries = sorted(
        (m for m in manifest if m["mode"] == "C"),
        key=lambda m: (m["hf_repo_id"], m["seed"], m["repeat"]),
    )
    for entry in entries:
        eval_id = uuid.UUID(entry["evaluation_id"])
        evaluation = EvaluationRepository(session).get_by_id(eval_id)
        final = FinalScoreRepository(session).get_for_evaluation(eval_id)
        osd = OsdAgentOutputRepository(session).latest_for_evaluation(eval_id)
        probes = {
            p.dimension.value: p
            for p in ProbeResultRepository(session).list_for_evaluation(eval_id)
        }

        row: dict[str, Any] = {
            "hf_repo_id": entry["hf_repo_id"],
            "model_revision": entry.get("model_revision"),
            "evaluation_id": str(eval_id),
            "repeat": entry["repeat"],
            "seed": entry["seed"],
            "status": evaluation.status.value if evaluation else entry["status"],
            "fries_score": _round(final.fries_score) if final else None,
            "overall_confidence": _round(final.overall_confidence) if final else None,
        }
        aspects = _osd_by_aspect(final.finalized_osd if final else None)
        confidences = _confidence_by_aspect(osd.ai_suggestion if osd else None)
        dimension_scores = final.dimension_scores if final else {}
        for aspect in ASPECTS:
            triple = aspects.get(aspect, {})
            row[f"{aspect}_O"] = triple.get("O")
            row[f"{aspect}_S"] = triple.get("S")
            row[f"{aspect}_D"] = triple.get("D")
            row[f"{aspect}_Ti"] = _round(dimension_scores.get(aspect))
            row[f"{aspect}_confidence"] = _round(confidences.get(aspect))

        fairness_metrics = probes.get("FAIRNESS").metric_values if probes.get("FAIRNESS") else {}
        robustness_metrics = (
            probes.get("ROBUSTNESS").metric_values if probes.get("ROBUSTNESS") else {}
        )
        row["fairness_skip_reason"] = fairness_metrics.get("skip_reason")
        row["robustness_skip_reason"] = robustness_metrics.get("skip_reason")
        row["fairness_dp_diff"] = _round(fairness_metrics.get("demographic_parity_difference"))
        row["fairness_eo_diff"] = _round(fairness_metrics.get("equalized_odds_difference"))
        row["robustness_clean_acc"] = _round(robustness_metrics.get("clean_accuracy"))
        row["robustness_robust_acc"] = _round(robustness_metrics.get("robust_accuracy"))
        row["robustness_attack_success_rate"] = _round(
            robustness_metrics.get("attack_success_rate")
        )

        row["wall_s"] = entry.get("wall_s")
        db_duration = None
        if final is not None and evaluation is not None:
            db_duration = round((final.created_at - evaluation.created_at).total_seconds(), 2)
        row["db_duration_s"] = db_duration
        row["trustlens_version"] = evaluation.trustlens_version if evaluation else None
        row["created_at"] = (
            evaluation.created_at.isoformat(timespec="seconds") if evaluation else None
        )
        rows.append(row)
    return rows


def _stdev(values: list[float]) -> float | None:
    return round(statistics.stdev(values), 4) if len(values) >= 2 else None


def _mode_c_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-model repeatability over FINALIZED seeded runs + determinism verdict."""
    by_model: dict[str, list[dict[str, Any]]] = {}
    det_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["status"] != "FINALIZED":
            continue
        if row["repeat"] == "det-check":
            det_rows[row["hf_repo_id"]] = row
        elif str(row["repeat"]).startswith("seed-"):
            by_model.setdefault(row["hf_repo_id"], []).append(row)

    summary: list[dict[str, Any]] = []
    for model, runs in sorted(by_model.items()):
        fries = [r["fries_score"] for r in runs if r["fries_score"] is not None]
        out: dict[str, Any] = {
            "hf_repo_id": model,
            "n_runs": len(runs),
            "seeds": ";".join(str(r["seed"]) for r in runs),
            "fries_mean": round(statistics.mean(fries), 4) if fries else None,
            "fries_std": _stdev(fries),
        }
        for aspect in ASPECTS:
            for component in ("O", "S", "D"):
                values = [
                    r[f"{aspect}_{component}"]
                    for r in runs
                    if r[f"{aspect}_{component}"] is not None
                ]
                out[f"{aspect}_{component}_std"] = _stdev([float(v) for v in values])

        det = det_rows.get(model)
        verdict = None
        if det is not None:
            base = next((r for r in runs if r["seed"] == det["seed"]), None)
            if base is not None:
                keys = ["fries_score"] + [
                    f"{a}_{c}" for a in ASPECTS for c in ("O", "S", "D")
                ]
                diffs = [k for k in keys if base.get(k) != det.get(k)]
                verdict = "identical" if not diffs else f"differs: {','.join(diffs)}"
        out["determinism_check"] = verdict
        summary.append(out)
    return summary


def _mode_b_rows(session: Any, manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    entries = sorted(
        (m for m in manifest if m["mode"] == "B"), key=lambda m: m["hf_repo_id"]
    )
    for entry in entries:
        eval_id = uuid.UUID(entry["evaluation_id"])
        evaluation = EvaluationRepository(session).get_by_id(eval_id)
        review = HumanReviewRepository(session).latest_for_evaluation(eval_id)
        final = FinalScoreRepository(session).get_for_evaluation(eval_id)
        if review is None:
            rows.append(
                {
                    "hf_repo_id": entry["hf_repo_id"],
                    "evaluation_id": str(eval_id),
                    "status": evaluation.status.value if evaluation else entry["status"],
                    "aspect": None,
                }
            )
            continue
        overrides = review.overrides or {}
        rationale = overrides.get("review_rationale") or ""
        reviewer_label = (
            "ai-provisional" if rationale.startswith("[ai-provisional]") else "human"
        )
        approved = {
            a["aspect"]: a
            for a in (overrides.get("approved_osd") or {}).get("aspects", [])
        }
        snapshot = {
            a["aspect"]: a
            for a in (overrides.get("agent_osd_snapshot") or {}).get("aspects", [])
        }
        for aspect in ASPECTS:
            agent = snapshot.get(aspect, {})
            human = approved.get(aspect, {})
            changed = any(agent.get(c) != human.get(c) for c in ("O", "S", "D"))
            rows.append(
                {
                    "hf_repo_id": entry["hf_repo_id"],
                    "evaluation_id": str(eval_id),
                    "status": evaluation.status.value if evaluation else entry["status"],
                    "reviewer_id": review.reviewer_id,
                    "reviewer_label": reviewer_label,
                    "accept_all": overrides.get("accept_all"),
                    "human_changed": review.human_changed,
                    "aspect": aspect,
                    "agent_O": agent.get("O"),
                    "agent_S": agent.get("S"),
                    "agent_D": agent.get("D"),
                    "approved_O": human.get("O"),
                    "approved_S": human.get("S"),
                    "approved_D": human.get("D"),
                    "aspect_changed": changed,
                    "final_fries": _round(final.fries_score) if final else None,
                    "review_rationale": rationale,
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print(f"skip {path.name}: no rows")
        return
    fieldnames: list[str] = []
    for row in rows:  # preserve first-seen order, union of keys
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(REPO_ROOT)} ({len(rows)} rows)")


def main() -> int:
    manifest = _load_manifest()
    url = _resolve_database_url()
    with get_session(url) as session:
        c_rows = _mode_c_rows(session, manifest)
        b_rows = _mode_b_rows(session, manifest)
    _write_csv(RESULTS_DIR / "mode_c_runs.csv", c_rows)
    _write_csv(RESULTS_DIR / "mode_c_summary.csv", _mode_c_summary(c_rows))
    _write_csv(RESULTS_DIR / "mode_b_reviews.csv", b_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
