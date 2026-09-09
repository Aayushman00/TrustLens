"""Phase 26 analysis — regenerate tables and figures from committed CSVs.

Does not talk to the API or database. Reads ``results/mode_*.csv`` and writes
``results/analysis/``. Root ``scripts/`` is gitignored; this lives with the
other experiment tools and is invoked as::

    cd backend
    python -m app.scripts.analyze_experiments
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS = REPO_ROOT / "results"
OUT = RESULTS / "analysis"

ASPECTS = ["FAIRNESS", "ROBUSTNESS", "INTEGRITY", "EXPLAINABILITY", "SAFETY"]
COMPONENTS = ("O", "S", "D")

SHORT = {
    "distilbert-base-uncased-finetuned-sst-2-english": "DistilBERT SST-2",
    "philschmid/tiny-bert-sst2-distilled": "TinyBERT SST-2",
    "textattack/roberta-base-SST-2": "RoBERTa SST-2",
    "textattack/bert-base-uncased-ag-news": "BERT AG News",
    "prajjwal1/bert-tiny": "BERT-tiny LM",
    "google/vit-base-patch16-224": "ViT-B/16",
}

REQUIRED_C_RUNS = {
    "hf_repo_id",
    "repeat",
    "seed",
    "status",
    "fries_score",
    "overall_confidence",
    "wall_s",
    "fairness_skip_reason",
    "robustness_skip_reason",
    *[f"{a}_{c}" for a in ASPECTS for c in (*COMPONENTS, "Ti", "confidence")],
}
REQUIRED_C_SUMMARY = {"hf_repo_id", "n_runs", "fries_mean", "fries_std", "determinism_check"}
REQUIRED_B = {
    "hf_repo_id",
    "aspect",
    "accept_all",
    "human_changed",
    "agent_O",
    "agent_S",
    "agent_D",
    "approved_O",
    "approved_S",
    "approved_D",
    "aspect_changed",
    "final_fries",
    "reviewer_label",
}
REQUIRED_A = {"reviewer", "model", "aspect", "O", "S", "D", "Pi", "minutes_spent"}


class AnalysisError(SystemExit):
    """Clear missing-input failure (exit code 1)."""


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise AnalysisError(f"missing required file: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _require_columns(rows: list[dict[str, str]], required: set[str], label: str) -> None:
    if not rows:
        raise AnalysisError(f"{label} is empty")
    missing = sorted(required - set(rows[0].keys()))
    if missing:
        raise AnalysisError(f"{label} missing columns: {', '.join(missing)}")


def _f(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _i(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _truthy(value: str | None) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _skipped(reason: str | None) -> bool:
    return bool(reason and reason.strip())


def _cbrt(o: float, s: float, d: float) -> float:
    return (o * s * d) ** (1.0 / 3.0)


def _fries_from_osd(aspects: dict[str, dict[str, int]]) -> float:
    tis = [_cbrt(a["O"], a["S"], a["D"]) for a in aspects.values()]
    return statistics.mean(tis)


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _stdev(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    out = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[indexed[k][0]] = avg
        i = j + 1
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    return _pearson(_ranks(xs), _ranks(ys))


def _mae(xs: list[float], ys: list[float]) -> float | None:
    if not xs or len(xs) != len(ys):
        return None
    return statistics.mean(abs(x - y) for x, y in zip(xs, ys, strict=True))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise AnalysisError(f"refusing to write empty table: {path.name}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(REPO_ROOT)} ({len(rows)} rows)")


def _md_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    if not rows:
        return "_no rows_\n"
    cols = columns or list(rows[0].keys())
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = [
        "| " + " | ".join(escape_md(_fmt(row.get(c))) for c in cols) + " |" for row in rows
    ]
    return "\n".join([header, sep, *body]) + "\n"


def escape_md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _write_md(path: Path, title: str, body: str) -> None:
    path.write_text(f"# {title}\n\n{body}", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------------------
# Data shaping
# ---------------------------------------------------------------------------


def seeded_runs(c_runs: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        r
        for r in c_runs
        if r["status"] == "FINALIZED" and str(r["repeat"]).startswith("seed-")
    ]


def group_by_model(runs: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in runs:
        grouped[row["hf_repo_id"]].append(row)
    return dict(grouped)


def robustness_status(runs: list[dict[str, str]]) -> str:
    skipped = [_skipped(r.get("robustness_skip_reason")) for r in runs]
    if all(skipped):
        return "skipped"
    if not any(skipped):
        return "ran"
    return "mixed"


def mode_a_by_model(a_rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in a_rows:
        model = row["model"]
        bucket = out.setdefault(
            model,
            {"reviewer": row["reviewer"], "aspects": {}, "fries": None, "minutes": 0.0},
        )
        if row["aspect"] == "FRIES":
            bucket["fries"] = _f(row["Pi"])
            continue
        bucket["aspects"][row["aspect"]] = {
            "O": _i(row["O"]),
            "S": _i(row["S"]),
            "D": _i(row["D"]),
            "Pi": _f(row["Pi"]),
        }
        minutes = _f(row.get("minutes_spent"))
        if minutes:
            bucket["minutes"] += minutes
    return out


def mode_b_by_model(b_rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in b_rows:
        model = row["hf_repo_id"]
        bucket = out.setdefault(
            model,
            {
                "accept_all": _truthy(row["accept_all"]),
                "human_changed": _truthy(row["human_changed"]),
                "reviewer_label": row.get("reviewer_label"),
                "final_fries": _f(row["final_fries"]),
                "aspects": {},
            },
        )
        bucket["aspects"][row["aspect"]] = {
            "agent": {
                "O": _i(row["agent_O"]),
                "S": _i(row["agent_S"]),
                "D": _i(row["agent_D"]),
            },
            "approved": {
                "O": _i(row["approved_O"]),
                "S": _i(row["approved_S"]),
                "D": _i(row["approved_D"]),
            },
            "changed": _truthy(row["aspect_changed"]),
        }
    return out


def seed42(runs: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {r["hf_repo_id"]: r for r in runs if r["repeat"] == "seed-42"}


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def table_t1(seeded: list[dict[str, str]], summary: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped = group_by_model(seeded)
    summary_by = {r["hf_repo_id"]: r for r in summary}
    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for model, runs in sorted(grouped.items(), key=lambda kv: -statistics.mean(
        float(r["fries_score"]) for r in kv[1]
    )):
        fries = [float(r["fries_score"]) for r in runs]
        mean_v, std_v = statistics.mean(fries), statistics.stdev(fries)
        src = summary_by.get(model)
        if src and src.get("fries_mean"):
            if abs(float(src["fries_mean"]) - mean_v) > 0.001:
                mismatches.append(
                    f"{model}: recomputed mean {mean_v:.4f} != summary {src['fries_mean']}"
                )
            if src.get("fries_std") and abs(float(src["fries_std"]) - std_v) > 0.001:
                mismatches.append(
                    f"{model}: recomputed std {std_v:.4f} != summary {src['fries_std']}"
                )
        rows.append(
            {
                "model": model,
                "short": SHORT.get(model, model),
                "n_runs": len(runs),
                "fries_mean": _round(mean_v),
                "fries_std": _round(std_v),
                "fries_mean_pm_std": f"{mean_v:.2f} ± {std_v:.2f}",
                "robustness": robustness_status(runs),
                "fairness": "proxy-ran" if not any(
                    _skipped(r.get("fairness_skip_reason")) for r in runs
                ) else "skipped",
            }
        )
    if mismatches:
        raise AnalysisError("T1 does not match mode_c_summary.csv:\n" + "\n".join(mismatches))
    return rows


def table_t2(seeded: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model, runs in sorted(group_by_model(seeded).items()):
        row: dict[str, Any] = {"model": model, "short": SHORT.get(model, model)}
        for aspect in ASPECTS:
            for component in (*COMPONENTS, "Ti"):
                values = [float(r[f"{aspect}_{component}"]) for r in runs]
                row[f"{aspect}_{component}_mean"] = _round(statistics.mean(values))
        rows.append(row)
    return rows


def table_t3(
    a_map: dict[str, dict[str, Any]],
    b_map: dict[str, dict[str, Any]],
    s42: dict[str, dict[str, str]],
    seeded: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    c_mean = {
        model: statistics.mean(float(r["fries_score"]) for r in runs)
        for model, runs in group_by_model(seeded).items()
    }
    fries_rows: list[dict[str, Any]] = []
    aspect_rows: list[dict[str, Any]] = []
    shared = sorted(set(a_map) & set(s42))
    for model in shared:
        a = a_map[model]
        c = s42[model]
        b = b_map.get(model)
        a_fries = a["fries"]
        c_fries = float(c["fries_score"])
        b_fries = b["final_fries"] if b else None
        fries_rows.append(
            {
                "model": model,
                "short": SHORT.get(model, model),
                "mode_a_fries": _round(a_fries, 2),
                "mode_c_seed42_fries": _round(c_fries),
                "mode_c_mean_fries": _round(c_mean[model]),
                "mode_b_fries": _round(b_fries) if b_fries is not None else None,
                "delta_c_minus_a": _round(c_fries - a_fries),
                "delta_b_minus_a": _round(b_fries - a_fries) if b_fries is not None else None,
                "delta_b_minus_c": _round(b_fries - c_fries) if b_fries is not None else None,
            }
        )
        for aspect in ASPECTS:
            a_osd = a["aspects"][aspect]
            row: dict[str, Any] = {
                "model": model,
                "short": SHORT.get(model, model),
                "aspect": aspect,
            }
            for component in COMPONENTS:
                a_v = a_osd[component]
                c_v = int(c[f"{aspect}_{component}"])
                row[f"A_{component}"] = a_v
                row[f"C_{component}"] = c_v
                row[f"dC_{component}"] = c_v - a_v
                if b:
                    b_v = b["aspects"][aspect]["approved"][component]
                    row[f"B_{component}"] = b_v
                    row[f"dB_{component}"] = b_v - a_v
            aspect_rows.append(row)
    return fries_rows, aspect_rows


def table_t4(b_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary: list[dict[str, Any]] = []
    deltas: list[dict[str, Any]] = []
    n_aspects_total = 0
    n_aspects_changed = 0
    for model, payload in sorted(b_map.items()):
        agent_osd = {a: p["agent"] for a, p in payload["aspects"].items()}
        agent_fries = _fries_from_osd(agent_osd)
        n_changed = sum(1 for p in payload["aspects"].values() if p["changed"])
        n_aspects_total += len(payload["aspects"])
        n_aspects_changed += n_changed
        abs_deltas = []
        for aspect, p in payload["aspects"].items():
            d_o = p["approved"]["O"] - p["agent"]["O"]
            d_s = p["approved"]["S"] - p["agent"]["S"]
            d_d = p["approved"]["D"] - p["agent"]["D"]
            mag = abs(d_o) + abs(d_s) + abs(d_d)
            abs_deltas.append(mag)
            deltas.append(
                {
                    "model": model,
                    "short": SHORT.get(model, model),
                    "aspect": aspect,
                    "agent_O": p["agent"]["O"],
                    "agent_S": p["agent"]["S"],
                    "agent_D": p["agent"]["D"],
                    "approved_O": p["approved"]["O"],
                    "approved_S": p["approved"]["S"],
                    "approved_D": p["approved"]["D"],
                    "dO": d_o,
                    "dS": d_s,
                    "dD": d_d,
                    "l1_delta": mag,
                    "changed": p["changed"],
                }
            )
        override_rate = n_changed / len(payload["aspects"]) if payload["aspects"] else None
        summary.append(
            {
                "model": model,
                "short": SHORT.get(model, model),
                "reviewer_label": payload["reviewer_label"],
                "accept_all": payload["accept_all"],
                "human_changed": payload["human_changed"],
                "aspects_changed": n_changed,
                "aspects_total": len(payload["aspects"]),
                "override_rate": _round(override_rate, 3),
                "agent_fries": _round(agent_fries),
                "approved_fries": _round(payload["final_fries"]),
                "delta_fries": _round(payload["final_fries"] - agent_fries),
                "mean_l1_osd_delta": _round(statistics.mean(abs_deltas), 2),
            }
        )
    summary.append(
        {
            "model": "_OVERALL_",
            "short": "overall",
            "reviewer_label": "",
            "accept_all": "",
            "human_changed": "",
            "aspects_changed": n_aspects_changed,
            "aspects_total": n_aspects_total,
            "override_rate": _round(n_aspects_changed / n_aspects_total, 3)
            if n_aspects_total
            else None,
            "agent_fries": None,
            "approved_fries": None,
            "delta_fries": None,
            "mean_l1_osd_delta": None,
        }
    )
    return summary, deltas


def table_t5(
    seeded: list[dict[str, str]],
    a_map: dict[str, dict[str, Any]],
    manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grouped = group_by_model(seeded)
    b_wall = {
        r["hf_repo_id"]: r.get("wall_s")
        for r in manifest
        if r.get("mode") == "B"
    }
    for model, runs in sorted(grouped.items()):
        walls = [float(r["wall_s"]) for r in runs]
        warm = sorted(walls)[:-1] if len(walls) >= 2 else walls  # drop likely cold start (max)
        a = a_map.get(model)
        rows.append(
            {
                "model": model,
                "short": SHORT.get(model, model),
                "mode_c_wall_s_mean": _round(statistics.mean(walls), 2),
                "mode_c_wall_s_warm_mean": _round(statistics.mean(warm), 2),
                "mode_c_wall_s_min": _round(min(walls), 2),
                "mode_c_wall_s_max": _round(max(walls), 2),
                "mode_a_minutes": _round(a["minutes"], 1) if a else None,
                "mode_b_pipeline_wall_s": b_wall.get(model),
                "mode_b_review_minutes": None,
                "notes": (
                    "Mode B review duration was not instrumented; pipeline wall is "
                    "create→AWAITING_REVIEW only. Mode A minutes are rubric-pass estimates."
                    if model in a_map
                    else "Mode C only; first/max wall includes HF download."
                ),
            }
        )
    return rows


def table_t6(
    seeded: list[dict[str, str]],
    b_map: dict[str, dict[str, Any]],
    t4_deltas: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ranked: list[dict[str, Any]] = []
    for model, runs in group_by_model(seeded).items():
        r0 = runs[0]
        edit_l1 = [
            d["l1_delta"]
            for d in t4_deltas
            if d["model"] == model
        ]
        ranked.append(
            {
                "model": model,
                "short": SHORT.get(model, model),
                "overall_confidence": _round(float(r0["overall_confidence"])),
                "FAIRNESS_confidence": _round(float(r0["FAIRNESS_confidence"])),
                "ROBUSTNESS_confidence": _round(float(r0["ROBUSTNESS_confidence"])),
                "INTEGRITY_confidence": _round(float(r0["INTEGRITY_confidence"])),
                "EXPLAINABILITY_confidence": _round(float(r0["EXPLAINABILITY_confidence"])),
                "SAFETY_confidence": _round(float(r0["SAFETY_confidence"])),
                "robustness_skipped": robustness_status(runs) == "skipped",
                "card_like_conf_mean": _round(
                    statistics.mean(
                        [
                            float(r0["EXPLAINABILITY_confidence"]),
                            float(r0["SAFETY_confidence"]),
                        ]
                    )
                ),
                "mode_b_edited": (
                    None if model not in b_map else b_map[model]["human_changed"]
                ),
                "mode_b_edit_l1_sum": sum(edit_l1) if edit_l1 else None,
            }
        )
    ranked.sort(key=lambda r: r["overall_confidence"] or 0, reverse=True)

    confs = [r["overall_confidence"] for r in ranked if r["overall_confidence"] is not None]
    card = [r["card_like_conf_mean"] for r in ranked if r["card_like_conf_mean"] is not None]
    skip = [1.0 if r["robustness_skipped"] else 0.0 for r in ranked]
    edit_pairs = [
        (r["card_like_conf_mean"], float(r["mode_b_edit_l1_sum"]))
        for r in ranked
        if r["mode_b_edit_l1_sum"] is not None and r["card_like_conf_mean"] is not None
    ]
    corr: list[dict[str, Any]] = [
        {
            "pair": "overall_confidence vs explainability+safety mean (n=6)",
            "n": len(confs),
            "pearson": _round(_pearson(confs, card)),
            "spearman": _round(_spearman(confs, card)),
            "note": "Tautological-ish: overall confidence is an aggregate of aspect confidences.",
        },
        {
            "pair": "overall_confidence vs robustness_skipped (point-biserial, n=6)",
            "n": len(confs),
            "pearson": _round(_pearson(confs, skip)),
            "spearman": _round(_spearman(confs, skip)),
            "note": "Negative expected if skips lower confidence. Descriptive only.",
        },
    ]
    if len(edit_pairs) >= 2:
        xs, ys = [p[0] for p in edit_pairs], [p[1] for p in edit_pairs]
        corr.append(
            {
                "pair": "card-like confidence vs Mode B edit L1 (n=3 overlap)",
                "n": len(edit_pairs),
                "pearson": _round(_pearson(xs, ys)),
                "spearman": _round(_spearman(xs, ys)),
                "note": "Thin-card models were the ones edited; n=3, not inferential.",
            }
        )
    return ranked, corr


def table_t7(c_runs: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    det: list[dict[str, str]] = []
    for row in c_runs:
        if row["repeat"] == "det-check":
            det.append(row)
        elif row["repeat"] == "seed-42":
            by_key[(row["hf_repo_id"], row["seed"])] = row
    keys = ["fries_score"] + [f"{a}_{c}" for a in ASPECTS for c in COMPONENTS]
    extra = [
        "overall_confidence",
        "fairness_dp_diff",
        "fairness_eo_diff",
        "robustness_clean_acc",
        "robustness_robust_acc",
        "robustness_attack_success_rate",
    ]
    rows: list[dict[str, Any]] = []
    for d in det:
        base = by_key.get((d["hf_repo_id"], d["seed"]))
        if base is None:
            rows.append(
                {
                    "model": d["hf_repo_id"],
                    "verdict": "MISSING_BASELINE",
                    "n_keys_compared": 0,
                    "n_diffs": None,
                }
            )
            continue
        diffs = [k for k in keys + extra if (d.get(k) or "") != (base.get(k) or "")]
        rows.append(
            {
                "model": d["hf_repo_id"],
                "short": SHORT.get(d["hf_repo_id"], d["hf_repo_id"]),
                "seed": d["seed"],
                "det_evaluation_id": d["evaluation_id"],
                "base_evaluation_id": base["evaluation_id"],
                "verdict": "identical" if not diffs else "differs",
                "n_keys_compared": len(keys) + len(extra),
                "n_diffs": len(diffs),
                "diff_keys": ",".join(diffs),
                "fries_det": _f(d["fries_score"]),
                "fries_seed42": _f(base["fries_score"]),
            }
        )
    if not rows:
        raise AnalysisError("no det-check rows in mode_c_runs.csv")
    return rows


def agreement_table(
    fries_rows: list[dict[str, Any]],
    aspect_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    a_f = [r["mode_a_fries"] for r in fries_rows]
    c_f = [r["mode_c_seed42_fries"] for r in fries_rows]
    b_f = [r["mode_b_fries"] for r in fries_rows if r["mode_b_fries"] is not None]
    a_for_b = [r["mode_a_fries"] for r in fries_rows if r["mode_b_fries"] is not None]

    def osd_mae(prefix_left: str, prefix_right: str) -> float:
        errs: list[float] = []
        for row in aspect_rows:
            for component in COMPONENTS:
                left = row.get(f"{prefix_left}_{component}")
                right = row.get(f"{prefix_right}_{component}")
                if left is None or right is None:
                    continue
                errs.append(abs(float(left) - float(right)))
        return statistics.mean(errs)

    rows = [
        {
            "comparison": "A vs C (FRIES, seed-42, n=3 models)",
            "n": len(a_f),
            "pearson": _round(_pearson(a_f, c_f)),
            "spearman": _round(_spearman(a_f, c_f)),
            "mae": _round(_mae(a_f, c_f), 3),
            "note": "Single Mode A rater, ai-provisional. n=3 — descriptive only, not significance.",
        },
        {
            "comparison": "A vs B (FRIES, n=3 models)",
            "n": len(b_f),
            "pearson": _round(_pearson(a_for_b, b_f)),
            "spearman": _round(_spearman(a_for_b, b_f)),
            "mae": _round(_mae(a_for_b, b_f), 3),
            "note": "Mode B also ai-provisional. Cohen's kappa omitted (one rater; no band discretization).",
        },
        {
            "comparison": "A vs C (mean |Δ| over O/S/D cells)",
            "n": len(aspect_rows) * 3,
            "pearson": None,
            "spearman": None,
            "mae": _round(osd_mae("A", "C"), 3),
            "note": "15 aspects × 3 components on 3 models.",
        },
        {
            "comparison": "A vs B (mean |Δ| over O/S/D cells)",
            "n": len(aspect_rows) * 3,
            "pearson": None,
            "spearman": None,
            "mae": _round(osd_mae("A", "B"), 3),
            "note": "Approved Mode B O/S/D vs Mode A rubric.",
        },
    ]
    return rows


def coverage_table(seeded: list[dict[str, str]]) -> list[dict[str, Any]]:
    n_slots = len(seeded) * 5
    fairness_skip = sum(_skipped(r.get("fairness_skip_reason")) for r in seeded)
    robust_skip = sum(_skipped(r.get("robustness_skip_reason")) for r in seeded)
    n_models = len(group_by_model(seeded))
    n_robust_models = sum(
        1
        for runs in group_by_model(seeded).values()
        if robustness_status(runs) == "ran"
    )
    return [
        {
            "probe": "FAIRNESS",
            "runs": len(seeded),
            "produced_metrics": len(seeded) - fairness_skip,
            "skipped": fairness_skip,
            "skip_rate": _round(fairness_skip / len(seeded), 3),
            "note": "Always ran; proxy LR on Adult — metrics are model-independent.",
        },
        {
            "probe": "ROBUSTNESS",
            "runs": len(seeded),
            "produced_metrics": len(seeded) - robust_skip,
            "skipped": robust_skip,
            "skip_rate": _round(robust_skip / len(seeded), 3),
            "note": f"{n_robust_models}/{n_models} models are text-classifiers; others soft-skip.",
        },
        {
            "probe": "INTEGRITY (card)",
            "runs": len(seeded),
            "produced_metrics": len(seeded),
            "skipped": 0,
            "skip_rate": 0.0,
            "note": "Card/metadata checks; always a numeric pass-rate.",
        },
        {
            "probe": "EXPLAINABILITY (card)",
            "runs": len(seeded),
            "produced_metrics": len(seeded),
            "skipped": 0,
            "skip_rate": 0.0,
            "note": "Header-coverage heuristic; 0.00 coverage is still a metric, not a skip.",
        },
        {
            "probe": "SAFETY (card)",
            "runs": len(seeded),
            "produced_metrics": len(seeded),
            "skipped": 0,
            "skip_rate": 0.0,
            "note": "Same coverage heuristic as explainability.",
        },
        {
            "probe": "_ALL_SLOTS_",
            "runs": n_slots,
            "produced_metrics": n_slots - robust_skip - fairness_skip,
            "skipped": robust_skip + fairness_skip,
            "skip_rate": _round((robust_skip + fairness_skip) / n_slots, 3),
            "note": "5 dimensions × 6 models × 3 seeds. Only robustness actually skips.",
        },
    ]


# ---------------------------------------------------------------------------
# SVG figures (no matplotlib dependency)
# ---------------------------------------------------------------------------

PALETTE = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2"]


def _svg(width: int, height: int, body: str, title: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">\n'
        f"<title>{escape(title)}</title>\n"
        f'<rect width="100%" height="100%" fill="#ffffff"/>\n'
        f"{body}\n</svg>\n"
    )


def _text(x: float, y: float, s: str, *, size: int = 12, anchor: str = "start",
          weight: str = "normal", fill: str = "#111827") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Segoe UI, Helvetica, Arial, sans-serif" '
        f'font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">'
        f"{escape(s)}</text>"
    )


def fig_f1(t1: list[dict[str, Any]]) -> str:
    width, height = 820, 420
    left, right, top, bottom = 70, 30, 50, 90
    plot_w, plot_h = width - left - right, height - top - bottom
    ymax = 8.0
    n = len(t1)
    gap = plot_w / n
    bar_w = gap * 0.55
    parts = [
        _text(width / 2, 28, "F1. Mode C FRIES mean ± std (3 seeds)", size=16,
              anchor="middle", weight="bold"),
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" '
        f'stroke="#6b7280" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" '
        f'stroke="#6b7280" stroke-width="1"/>',
    ]
    for tick in range(0, 9):
        y = top + plot_h - (tick / ymax) * plot_h
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_w}" y2="{y:.1f}" '
            f'stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(_text(left - 8, y + 4, str(tick), size=11, anchor="end", fill="#6b7280"))
    parts.append(_text(left - 40, top - 12, "FRIES T", size=11, fill="#374151"))
    for i, row in enumerate(t1):
        mean_v = float(row["fries_mean"])
        std_v = float(row["fries_std"])
        x = left + gap * i + (gap - bar_w) / 2
        h = (mean_v / ymax) * plot_h
        y = top + plot_h - h
        color = PALETTE[i % len(PALETTE)]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'fill="{color}" opacity="0.85"/>'
        )
        err = (std_v / ymax) * plot_h
        cx = x + bar_w / 2
        parts.append(
            f'<line x1="{cx:.1f}" y1="{y-err:.1f}" x2="{cx:.1f}" y2="{y+err:.1f}" '
            f'stroke="#111827" stroke-width="1.5"/>'
        )
        parts.append(
            f'<line x1="{cx-5:.1f}" y1="{y-err:.1f}" x2="{cx+5:.1f}" y2="{y-err:.1f}" '
            f'stroke="#111827" stroke-width="1.5"/>'
        )
        parts.append(
            f'<line x1="{cx-5:.1f}" y1="{y+err:.1f}" x2="{cx+5:.1f}" y2="{y+err:.1f}" '
            f'stroke="#111827" stroke-width="1.5"/>'
        )
        label = row["short"]
        parts.append(
            _text(cx, top + plot_h + 18, label.split()[0], size=11, anchor="middle")
        )
        parts.append(
            _text(cx, top + plot_h + 34, " ".join(label.split()[1:]), size=11, anchor="middle")
        )
        hatch = "skip" if row["robustness"] == "skipped" else "ran"
        parts.append(_text(cx, y - err - 8, hatch, size=10, anchor="middle", fill="#6b7280"))
    parts.append(
        _text(width / 2, height - 12,
              "Error bars = sample std across seeds 42 / 1337 / 2025. Labels: robustness ran vs skipped.",
              size=11, anchor="middle", fill="#6b7280")
    )
    return _svg(width, height, "\n".join(parts), "F1 Mode C FRIES mean ± std")


def fig_f2(fries_rows: list[dict[str, Any]]) -> str:
    width, height = 720, 380
    left, right, top, bottom = 70, 30, 50, 70
    plot_w, plot_h = width - left - right, height - top - bottom
    n = len(fries_rows)
    gap = plot_w / n
    bar_w = gap * 0.22
    ymax = 8.0
    series = [
        ("mode_a_fries", "#4b5563", "Mode A (manual)"),
        ("mode_c_seed42_fries", "#2563eb", "Mode C (autonomous, seed 42)"),
        ("mode_b_fries", "#d97706", "Mode B (assisted, approved)"),
    ]
    parts = [
        _text(width / 2, 28, "F2. Mode A vs C vs B FRIES on overlapping models",
              size=16, anchor="middle", weight="bold"),
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#6b7280"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#6b7280"/>',
    ]
    for tick in range(0, 9):
        y = top + plot_h - (tick / ymax) * plot_h
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_w}" y2="{y:.1f}" stroke="#e5e7eb"/>'
        )
        parts.append(_text(left - 8, y + 4, str(tick), size=11, anchor="end", fill="#6b7280"))
    for i, row in enumerate(fries_rows):
        base = left + gap * i + gap * 0.12
        for j, (key, color, _) in enumerate(series):
            val = row.get(key)
            if val is None:
                continue
            h = (float(val) / ymax) * plot_h
            x = base + j * (bar_w + 4)
            y = top + plot_h - h
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}"/>'
            )
            parts.append(_text(x + bar_w / 2, y - 4, f"{float(val):.2f}", size=9,
                               anchor="middle", fill="#374151"))
        parts.append(_text(left + gap * i + gap / 2, top + plot_h + 22,
                           row["short"], size=12, anchor="middle"))
    lx = left
    for _, color, label in series:
        parts.append(f'<rect x="{lx}" y="{height-28}" width="12" height="12" fill="{color}"/>')
        parts.append(_text(lx + 16, height - 18, label, size=11))
        lx += 230
    return _svg(width, height, "\n".join(parts), "F2 Mode A vs C vs B FRIES")


def fig_f3(t4_deltas: list[dict[str, Any]], t4_summary: list[dict[str, Any]]) -> str:
    models = [r for r in t4_summary if r["model"] != "_OVERALL_"]
    width, height = 860, 460
    # left: before/after bars; right: |Δ| heatmap
    parts = [
        _text(width / 2, 26, "F3. Mode B: agent vs approved FRIES and per-aspect |ΔO|+|ΔS|+|ΔD|",
              size=15, anchor="middle", weight="bold"),
    ]
    left, top, plot_h, ymax = 50, 50, 160, 8.0
    gap = 240
    bar_w = 40
    for i, row in enumerate(models):
        x0 = left + i * gap
        for j, (key, color, lab) in enumerate(
            (("agent_fries", "#2563eb", "agent"), ("approved_fries", "#d97706", "approved"))
        ):
            val = float(row[key])
            h = (val / ymax) * plot_h
            x = x0 + j * (bar_w + 10)
            y = top + plot_h - h
            parts.append(
                f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" fill="{color}"/>'
            )
            parts.append(_text(x + bar_w / 2, y - 4, f"{val:.2f}", size=10, anchor="middle"))
        parts.append(_text(x0 + 45, top + plot_h + 18, row["short"], size=12, anchor="middle"))
        tag = "accept-all" if row["accept_all"] else "edited"
        parts.append(_text(x0 + 45, top + plot_h + 34, tag, size=11, anchor="middle", fill="#6b7280"))
    parts.append('<rect x="50" y="268" width="12" height="12" fill="#2563eb"/>')
    parts.append(_text(68, 278, "agent FRIES (before review)", size=11))
    parts.append('<rect x="280" y="268" width="12" height="12" fill="#d97706"/>')
    parts.append(_text(298, 278, "approved FRIES (after review)", size=11))

    cell = 52
    hx, hy = 80, 310
    parts.append(_text(hx, hy - 8, "Override L1 per aspect (0 = unchanged)", size=12, weight="bold"))
    for j, aspect in enumerate(ASPECTS):
        parts.append(_text(hx + 140 + j * cell + cell / 2, hy + 14, aspect[:4], size=10,
                           anchor="middle", fill="#6b7280"))
    for i, model_row in enumerate(models):
        parts.append(_text(hx + 130, hy + 40 + i * cell, model_row["short"], size=11, anchor="end"))
        for j, aspect in enumerate(ASPECTS):
            drow = next(
                d for d in t4_deltas
                if d["model"] == model_row["model"] and d["aspect"] == aspect
            )
            mag = float(drow["l1_delta"])
            t = min(mag / 12.0, 1.0)
            r = int(254 - t * 180)
            g = int(242 - t * 200)
            b = int(242 - t * 80)
            x = hx + 140 + j * cell
            y = hy + 22 + i * cell
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell-6}" height="{cell-10}" '
                f'fill="rgb({r},{g},{b})" stroke="#e5e7eb"/>'
            )
            parts.append(_text(x + (cell - 6) / 2, y + 24, str(int(mag)), size=12,
                               anchor="middle", fill="#111827"))
    return _svg(width, height, "\n".join(parts), "F3 Mode B overrides")


def fig_f4(seeded: list[dict[str, str]], t1: list[dict[str, Any]]) -> str:
    ordered = sorted(t1, key=lambda r: float(r["fries_std"]), reverse=True)
    high, low = ordered[0], ordered[-1]
    width, height = 720, 340
    left, top, plot_w, plot_h = 160, 50, 500, 220
    ymin, ymax = 3.8, 7.0
    parts = [
        _text(width / 2, 28, "F4. RQ6 seed sensitivity — highest vs lowest FRIES std",
              size=15, anchor="middle", weight="bold"),
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#6b7280"/>',
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#6b7280"/>',
    ]
    for tick in [4, 5, 6, 7]:
        y = top + plot_h - ((tick - ymin) / (ymax - ymin)) * plot_h
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_w}" y2="{y:.1f}" stroke="#e5e7eb"/>'
        )
        parts.append(_text(left - 8, y + 4, str(tick), size=11, anchor="end", fill="#6b7280"))
    grouped = group_by_model(seeded)
    colors = {high["model"]: "#dc2626", low["model"]: "#2563eb"}
    seed_order = {42: 0, 1337: 1, 2025: 2}
    labeled_seeds = False
    for model in (high["model"], low["model"]):
        for run in sorted(grouped[model], key=lambda r: int(r["seed"])):
            seed_i = seed_order[int(run["seed"])]
            x = left + 80 + seed_i * 140
            val = float(run["fries_score"])
            y = top + plot_h - ((val - ymin) / (ymax - ymin)) * plot_h
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{colors[model]}" opacity="0.9"/>'
            )
            parts.append(_text(x, y - 14, f"{val:.2f}", size=10, anchor="middle"))
            if not labeled_seeds:
                parts.append(_text(x, top + plot_h + 18, f"seed {run['seed']}", size=10,
                                   anchor="middle", fill="#6b7280"))
        labeled_seeds = True
        mean_v = statistics.mean(float(r["fries_score"]) for r in grouped[model])
        my = top + plot_h - ((mean_v - ymin) / (ymax - ymin)) * plot_h
        parts.append(
            f'<line x1="{left+40}" y1="{my:.1f}" x2="{left+plot_w-20}" y2="{my:.1f}" '
            f'stroke="{colors[model]}" stroke-dasharray="4 3" stroke-width="1.5"/>'
        )
    parts.append(f'<circle cx="{left+40}" cy="48" r="6" fill="{colors[high["model"]]}"/>')
    parts.append(_text(left + 52, 52, high["short"], size=11))
    parts.append(f'<circle cx="{left+220}" cy="48" r="6" fill="{colors[low["model"]]}"/>')
    parts.append(_text(left + 232, 52, low["short"], size=11))
    parts.append(_text(left + plot_w / 2, height - 14,
                       f"High std: {high['short']} ({high['fries_std']}); "
                       f"low std: {low['short']} ({low['fries_std']}). Dashed = mean.",
                       size=11, anchor="middle", fill="#6b7280"))
    return _svg(width, height, "\n".join(parts), "F4 seed strip")


def fig_f5(seeded: list[dict[str, str]]) -> str:
    models = sorted(group_by_model(seeded))
    probes = [
        ("fairness", "fairness_skip_reason", "Fairness (Adult proxy)"),
        ("robustness", "robustness_skip_reason", "Robustness (char-swap)"),
    ]
    cell_w, cell_h = 200, 48
    width = 160 + cell_w * 2 + 40
    height = 80 + cell_h * len(models) + 40
    parts = [
        _text(width / 2, 28, "F5. Probe skip matrix (seeded Mode C runs; identical across seeds)",
              size=14, anchor="middle", weight="bold"),
        _text(160 + cell_w / 2, 58, "Fairness", size=12, anchor="middle", weight="bold"),
        _text(160 + cell_w + cell_w / 2, 58, "Robustness", size=12, anchor="middle", weight="bold"),
    ]
    grouped = group_by_model(seeded)
    for i, model in enumerate(models):
        y = 70 + i * cell_h
        parts.append(_text(150, y + 28, SHORT.get(model, model), size=12, anchor="end"))
        run = grouped[model][0]
        for j, (_key, col, _lab) in enumerate(probes):
            skipped = _skipped(run.get(col))
            if _key == "fairness" and not skipped:
                fill, label = "#fde68a", "proxy ran"
            elif skipped:
                fill, label = "#fecaca", "skipped"
            else:
                fill, label = "#bbf7d0", "ran"
            x = 160 + j * cell_w
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_w-8}" height="{cell_h-8}" '
                f'rx="4" fill="{fill}" stroke="#e5e7eb"/>'
            )
            parts.append(_text(x + (cell_w - 8) / 2, y + 26, label, size=12, anchor="middle"))
    return _svg(width, height, "\n".join(parts), "F5 skip matrix")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    c_runs = _load_csv(RESULTS / "mode_c_runs.csv")
    c_sum = _load_csv(RESULTS / "mode_c_summary.csv")
    b_rows = _load_csv(RESULTS / "mode_b_reviews.csv")
    a_rows = _load_csv(RESULTS / "mode_a_manual.csv")
    _require_columns(c_runs, REQUIRED_C_RUNS, "mode_c_runs.csv")
    _require_columns(c_sum, REQUIRED_C_SUMMARY, "mode_c_summary.csv")
    _require_columns(b_rows, REQUIRED_B, "mode_b_reviews.csv")
    _require_columns(a_rows, REQUIRED_A, "mode_a_manual.csv")

    manifest: list[dict[str, Any]] = []
    man_path = RESULTS / "manifest_v1.jsonl"
    if man_path.exists():
        import json

        for line in man_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                manifest.append(json.loads(line))

    seeded = seeded_runs(c_runs)
    if len(seeded) != 18:
        raise AnalysisError(f"expected 18 seeded Mode C rows (6×3), got {len(seeded)}")

    a_map = mode_a_by_model(a_rows)
    b_map = mode_b_by_model(b_rows)
    s42 = seed42(seeded)

    t1 = table_t1(seeded, c_sum)
    t2 = table_t2(seeded)
    t3_fries, t3_aspects = table_t3(a_map, b_map, s42, seeded)
    t4_sum, t4_delta = table_t4(b_map)
    t5 = table_t5(seeded, a_map, manifest)
    t6_rank, t6_corr = table_t6(seeded, b_map, t4_delta)
    t7 = table_t7(c_runs)
    agree = agreement_table(t3_fries, t3_aspects)
    cover = coverage_table(seeded)

    OUT.mkdir(parents=True, exist_ok=True)
    _write_csv(OUT / "t1_mode_c_fries.csv", t1)
    _write_csv(OUT / "t2_mode_c_aspect_means.csv", t2)
    _write_csv(OUT / "t3_abc_fries.csv", t3_fries)
    _write_csv(OUT / "t3_abc_aspect_osd.csv", t3_aspects)
    _write_csv(OUT / "t4_mode_b_summary.csv", t4_sum)
    _write_csv(OUT / "t4_mode_b_deltas.csv", t4_delta)
    _write_csv(OUT / "t5_wallclock.csv", t5)
    _write_csv(OUT / "t6_confidence_ranked.csv", t6_rank)
    _write_csv(OUT / "t6_confidence_corr.csv", t6_corr)
    _write_csv(OUT / "t7_determinism.csv", t7)
    _write_csv(OUT / "agreement_metrics.csv", agree)
    _write_csv(OUT / "rq1_probe_coverage.csv", cover)

    figures = {
        "f1_mode_c_fries.svg": fig_f1(t1),
        "f2_abc_fries.svg": fig_f2(t3_fries),
        "f3_mode_b_overrides.svg": fig_f3(t4_delta, t4_sum),
        "f4_seed_strip.svg": fig_f4(seeded, t1),
        "f5_skip_matrix.svg": fig_f5(seeded),
    }
    for name, svg in figures.items():
        path = OUT / name
        path.write_text(svg, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")

    md = []
    md.append("## T1 — Mode C FRIES mean ± std\n\n" + _md_table(t1, [
        "short", "n_runs", "fries_mean", "fries_std", "fries_mean_pm_std", "robustness", "fairness",
    ]))
    md.append("## T2 — Mode C per-aspect Ti mean (equal-weight dimension scores)\n\n"
              + _md_table(
                  [{
                      "short": r["short"],
                      **{f"{a}_Ti": r[f"{a}_Ti_mean"] for a in ASPECTS},
                  } for r in t2]
              ))
    md.append("## T3 — Mode A vs C vs B FRIES\n\n" + _md_table(t3_fries, [
        "short", "mode_a_fries", "mode_c_seed42_fries", "mode_c_mean_fries",
        "mode_b_fries", "delta_c_minus_a", "delta_b_minus_a", "delta_b_minus_c",
    ]))
    md.append("## T4 — Mode B accept-all vs edited\n\n" + _md_table(t4_sum))
    md.append("## T5 — Wall-clock / effort\n\n" + _md_table(t5, [
        "short", "mode_c_wall_s_mean", "mode_c_wall_s_warm_mean",
        "mode_a_minutes", "mode_b_pipeline_wall_s", "mode_b_review_minutes",
    ]))
    md.append("## T6 — Confidence ranked by model\n\n" + _md_table(t6_rank, [
        "short", "overall_confidence", "EXPLAINABILITY_confidence", "SAFETY_confidence",
        "robustness_skipped", "mode_b_edited", "mode_b_edit_l1_sum",
    ]))
    md.append("## T6b — Confidence correlations (descriptive)\n\n" + _md_table(t6_corr))
    md.append("## T7 — Determinism check\n\n" + _md_table(t7, [
        "short", "verdict", "n_keys_compared", "n_diffs", "fries_det", "fries_seed42",
    ]))
    md.append("## Agreement (A vs C / A vs B)\n\n" + _md_table(agree))
    md.append("## RQ1 probe coverage\n\n" + _md_table(cover, [
        "probe", "runs", "produced_metrics", "skipped", "skip_rate", "note",
    ]))
    md.append(
        "Regenerate: `cd backend && python -m app.scripts.analyze_experiments`.\n"
        "Agent O/S/D remains **PROPOSED / REQUIRES VALIDATION**. "
        "Mode A/B rater label is `ai-provisional`.\n"
    )
    _write_md(OUT / "TABLES.md", "Phase 26 analysis tables", "\n".join(md))
    (OUT / "README.md").write_text(
        "Regenerated artifacts from `results/mode_*.csv`.\n\n"
        "```powershell\ncd backend\npython -m app.scripts.analyze_experiments\n```\n\n"
        "T1 means/stds are asserted against `results/mode_c_summary.csv`.\n",
        encoding="utf-8",
    )
    print("T1 spot-check vs mode_c_summary.csv: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
