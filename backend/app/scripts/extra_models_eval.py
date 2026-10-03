"""External sanity check: audit real Hub toxicity classifiers (RQ1, not trust labels).

Selection is mechanical and fixed *before* any evaluation (no cherry-picking):

1. Hub search for "toxic" and "hate" text-classification models, each sorted
   by downloads (top ``--pool`` per query), de-duplicated in that order.
2. Keep a model only if its card does not declare languages that exclude
   English (``language`` set without ``en``; the eval set is English Civil
   Comments; undeclared counts as eligible), ships PyTorch weights (``*.safetensors``/``pytorch_model.bin``;
   the worker loads with transformers), its config is a sequence classifier, and exactly one
   label is a positive harm label (``POSITIVE_NAMES``), and either the head is
   multi-label (that output is the target) or it has exactly two classes.
3. Take the first ``--n`` survivors; pin each at its current commit sha.

``select`` writes every candidate with its inclusion/exclusion reason to
``extra_models.json``; ``run`` evaluates that frozen list with the suite
contract (FAIRNESS, ROBUSTNESS, SAFETY) and records failures, not hides them.

Usage (from backend/)::
    python -m app.scripts.extra_models_eval select [--n 8]
    python -m app.scripts.extra_models_eval run --out eval_results_extra   # stack up
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

from app.scripts import run_flawed_suite_eval as r

POSITIVE_NAMES = {"toxic", "toxicity", "hate", "hateful", "hate speech", "offensive", "abusive"}
SELECTION_FILE = r.SUITE_DIR / "extra_models.json"
# Revised before any evaluation ran (2026-10-02): v1 picked a Russian model and
# an ONNX-only duplicate -> v2 required an "en" tag + PyTorch weights, which
# dropped untagged English models (unitary/toxic-bert) -> v3 excludes only
# models whose card declares languages without "en".
RULE_VERSION = "v3"


def positive_output(id2label: dict[int, str], problem_type: str | None) -> tuple[int | None, str]:
    hits = [i for i, name in id2label.items() if name.strip().lower().replace("_", " ") in POSITIVE_NAMES]
    if not hits:
        return None, "excluded: no label is a positive harm label"
    if len(hits) > 1:
        return None, f"excluded: ambiguous positive labels {[id2label[i] for i in hits]}"
    if problem_type == "multi_label_classification":
        return hits[0], "multi_label"
    if len(id2label) != 2:
        return None, f"excluded: {len(id2label)} single-label classes, binary contract not applicable"
    return hits[0], "single_label"


def select(n: int, pool: int) -> None:
    from huggingface_hub import HfApi
    from transformers import AutoConfig

    api = HfApi()
    seen: list[str] = []
    for query in ("toxic", "hate"):
        for m in api.list_models(search=query, pipeline_tag="text-classification", sort="downloads", limit=pool):
            if m.id not in seen:
                seen.append(m.id)
    candidates: list[dict[str, Any]] = []
    chosen = 0
    for repo in seen:
        row: dict[str, Any] = {"repo": repo}
        try:
            info = api.model_info(repo, files_metadata=False)
            sha = info.sha
            langs = (info.card_data or {}).get("language") if info.card_data else None
            langs = [langs] if isinstance(langs, str) else list(langs or [])
            if langs and "en" not in langs:
                raise ValueError(f"card declares languages {langs} without en")
            files = [f.rfilename for f in info.siblings or []]
            if not any(f.endswith(".safetensors") or f == "pytorch_model.bin" for f in files):
                raise ValueError("no PyTorch weights (safetensors / pytorch_model.bin)")
            cfg = AutoConfig.from_pretrained(repo, revision=sha)
            archs = getattr(cfg, "architectures", None) or []
            if not any(a.endswith("ForSequenceClassification") for a in archs):
                raise ValueError(f"not a sequence classifier: {archs}")
            labels = {int(k): str(v) for k, v in (cfg.id2label or {}).items()}
            idx, reason = positive_output(labels, getattr(cfg, "problem_type", None))
            row.update({"revision": sha, "id2label": labels, "positive_index": idx, "reason": reason})
        except Exception as exc:  # noqa: BLE001 — record, never hide
            row.update({"positive_index": None, "reason": f"excluded: {type(exc).__name__}: {exc}"[:300]})
        row["selected"] = row["positive_index"] is not None and chosen < n
        chosen += row["selected"]
        candidates.append(row)
    SELECTION_FILE.write_text(
        json.dumps(
            {
                "selected_at": datetime.now(UTC).isoformat(),
                "rule": __doc__.split("Usage")[0].strip(),
                "rule_version": RULE_VERSION,
                "n": n,
                "pool_per_query": pool,
                "candidates": candidates,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{chosen} selected of {len(candidates)} candidates -> {SELECTION_FILE}")


def run(out_name: str, only: list[str] | None = None) -> None:
    selection = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
    out = r.fresh_out_dir(r.SUITE_DIR / out_name)
    summary: list[dict[str, Any]] = []
    with r._client() as c:
        ds = r.upload_eval_dataset(c)
        for cand in (x for x in selection["candidates"] if x["selected"] and (not only or x["repo"] in only)):
            row: dict[str, Any] = {"repo": cand["repo"], "revision": cand["revision"]}
            try:
                resp = c.post("/models/import-hf", json={"repo_id": cand["repo"], "revision": cand["revision"]})
                resp.raise_for_status()
                k = cand["positive_index"] if cand["reason"] == "multi_label" else None
                pos = 1 if k is not None else cand["positive_index"]
                ev = r.create_and_run_evaluation(
                    c, resp.json()["id"], ds, multilabel_target_index=k, positive_index=pos
                )
                fs = ev.get("final_score") or {}
                row.update({"status": ev["status"], "fries_score": fs.get("fries_score"), "dimension_scores": fs.get("dimension_scores")})
                (out / f"{cand['repo'].replace('/', '__')}.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
            except Exception as exc:  # noqa: BLE001 — operational failures are results too
                row.update({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"[:500]})
            summary.append(row)
    (out / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--n", type=int, default=8)
    s.add_argument("--pool", type=int, default=30)
    ru = sub.add_parser("run")
    ru.add_argument("--out", required=True)
    ru.add_argument("--only", nargs="*", help="subset of selected repos")
    args = ap.parse_args()
    if args.cmd == "select":
        select(args.n, args.pool)
    else:
        run(args.out, args.only)


if __name__ == "__main__":
    main()
