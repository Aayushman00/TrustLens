"""TrustBench-C v0 scorecard runner (preregistration-c-v0.md).

    USE_TF=0 TRANSFORMERS_NO_TF=1 python -m app.trustbench.run_scorecard \
        --root ../results/trustbench_c_v0 --budgets 1000 --audit-seeds 5 [--only ID ...] [--out DIR]

Runs every probe and v1 comparator on the dev + validation models (``read_manifest`` default;
the test split is sealed), per audit seed s on ``random.Random(s).sample(eval_rows, budget)``
(same rows for every model). Evidence lines go to ``<out>/evidence/<model_id>.jsonl``, resumable
by (probe, audit_seed, prevalence, pool). The full-pool runs (binding probes on all 3 000 eval
rows) feed the sampling-coverage table only. Integrity: the 12 tamper fixtures (generated once
into ``<root>/tamper`` from a clean dev model) + the dev/val clean dirs. Writes
``<out>/scorecard.csv``, ``<out>/integrity.json`` and ``<out>/scorecard.md`` (generated tables;
the committed docs/v2 scorecard is written from it).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path
from typing import Callable

from app.evidence import EvidenceInputs, EvidenceItem
from app.posterior.rates import p_exceeds
from app.probes.v2.exp_shortcut import shortcut
from app.probes.v2.fair_counterfactual import counterfactual
from app.probes.v2.legacy import legacy_exp_aopc, legacy_fair_eod, legacy_rob_acc_drop, legacy_safe_severe_fnr
from app.probes.v2.rob_invariance import invariance
from app.probes.v2.safe_severe import severe_miss
from app.trustbench import scorer as S
from app.trustbench.generators import DOSES, tamper_fixtures
from app.trustbench.manifest import ManifestRow, read_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = REPO_ROOT / "results" / "trustbench_c_v0"
EVAL_PATH = REPO_ROOT / "results" / "flawed_model_suite" / "data" / "eval_set.jsonl"
EVAL_SHA256 = "0c0a7e54f9956adcd490bfeb4cdc3ea398c1472f5f782321c10a065bb78f6ca1"
METHODOLOGY = "trustbench-c-v0"
AUDIT_SEEDS = (1, 2, 3, 4, 5)
BUDGET = 1000
FULL_POOL_SEED = 0  # probe RNG seed for the full-pool (coverage) runs; not an audit seed
BINDING_PREVALENCE = 0.10  # shortcut audit trigger prevalence (A2 / R29); 0.0 and 0.30 descriptive

# (probe run name, function, trigger prevalence or None)
RUNS = (
    ("fair.counterfactual", counterfactual, None),
    ("rob.invariance", invariance, None),
    ("exp.shortcut", shortcut, BINDING_PREVALENCE),
    ("exp.shortcut", shortcut, 0.0),
    ("exp.shortcut", shortcut, 0.30),
    ("safe.severe", severe_miss, None),
    ("legacy.fair.eod", legacy_fair_eod, None),
    ("legacy.rob.acc_drop", legacy_rob_acc_drop, None),
    ("legacy.exp.aopc", legacy_exp_aopc, BINDING_PREVALENCE),
    ("legacy.safe.severe_fnr", legacy_safe_severe_fnr, None),
)
FULL_POOL_RUNS = tuple(r for r in RUNS if r[0] in ("fair.counterfactual", "rob.invariance", "safe.severe")
                       or (r[0] == "exp.shortcut" and r[2] == BINDING_PREVALENCE))
BINDING_TAU = dict(S.BINDING.values())  # item id -> tau

Key = tuple  # (probe, audit_seed | None, prevalence | None, pool)


def load_eval(path: Path, expected_sha: str | None) -> tuple[list[dict], str]:
    data = Path(path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if expected_sha is not None and sha != expected_sha:
        raise ValueError(f"eval set sha256 {sha} != pinned {expected_sha}")
    return [json.loads(x) for x in data.decode("utf-8").splitlines() if x], sha


def _key(line: dict) -> Key:
    return line["probe"], line["audit_seed"], line["prevalence"], line["pool"]


class Store:
    """Per-model evidence jsonl. A run's items are appended in one write, each line carrying
    ``n_items``; a key counts as done only when all its lines are present (a torn tail is dropped)."""

    def __init__(self, path: Path):
        self.path = path
        groups: dict[Key, list[dict]] = {}
        torn = False
        if path.exists():
            for x in path.read_text(encoding="utf-8").splitlines():
                try:
                    line = json.loads(x)
                except json.JSONDecodeError:
                    torn = True
                    continue
                groups.setdefault(_key(line), []).append(line)
        self.lines = {k: v for k, v in groups.items() if len(v) == v[0]["n_items"]}
        if torn or len(self.lines) != len(groups):
            path.write_text("".join(json.dumps(x) + "\n" for v in self.lines.values() for x in v), encoding="utf-8")

    def add(self, key: Key, items: list[EvidenceItem], model_id: str, split: str) -> None:
        probe, seed, prev, pool = key
        lines = [{"model_id": model_id, "split": split, "probe": probe, "audit_seed": seed, "prevalence": prev,
                  "pool": pool, "n_items": len(items), "item": i.model_dump(mode="json")} for i in items]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in lines))
        self.lines[key] = lines


def _cached(predict: Callable[[list[str]], list[float]]) -> Callable[[list[str]], list[float]]:
    """Dedupe texts within one (model, audit seed): the shortcut prevalences and AOPC re-score
    mostly identical occlusion variants."""
    cache: dict[str, float] = {}

    def f(texts: list[str]) -> list[float]:
        new = [t for t in dict.fromkeys(texts) if t not in cache]
        if new:
            cache.update(zip(new, predict(new)))
        return [cache[t] for t in texts]

    return f


def score_models(
    root: Path, out: Path, manifest: list[ManifestRow], eval_rows: list[dict], eval_sha: str, *,
    seeds, budget: int, load, full_pool: bool,
) -> None:
    samples = {s: random.Random(s).sample(eval_rows, budget) for s in seeds}
    for r in manifest:
        mdir = root / "models" / r.model_id
        if not (mdir / "train_manifest.json").exists():
            print(f"skip {r.model_id}: not trained", flush=True)
            continue
        store = Store(out / "evidence" / f"{r.model_id}.jsonl")
        plan = [(s, samples[s], [(n, f, p, (n, s, p, "audit")) for n, f, p in RUNS]) for s in seeds]
        if full_pool:
            plan.append((FULL_POOL_SEED, eval_rows, [(n, f, p, (n, None, p, "full")) for n, f, p in FULL_POOL_RUNS]))
        plan = [(s, rows, [x for x in runs if x[3] not in store.lines]) for s, rows, runs in plan]
        if not any(runs for *_, runs in plan):
            continue
        weights = S._sha256(mdir / "model.safetensors")
        if r.weights_sha256 is not None and weights != r.weights_sha256:
            raise ValueError(f"{r.model_id}: weights sha256 {weights} != manifest {r.weights_sha256}")
        inputs = EvidenceInputs(model_ref=f"trustbench_c_v0/{r.model_id}@sha256:{weights}",
                                dataset_sha256=eval_sha, methodology_version=METHODOLOGY)
        predict = load(mdir)
        for seed, rows, runs in plan:
            if not runs:
                continue
            t0, pp = time.perf_counter(), _cached(predict)
            for _, fn, prev, key in runs:
                kw = {} if prev is None else {"prevalence": prev}
                store.add(key, fn(pp, rows, seed=seed, budget=len(rows), inputs=inputs, **kw), r.model_id, r.split)
            pool = "full" if rows is eval_rows else "audit"
            print(f"{r.model_id} {pool} seed={seed} runs={len(runs)} {time.perf_counter() - t0:.1f}s", flush=True)


def _collect(out: Path, manifest: list[ManifestRow]) -> dict[str, list[dict]]:
    ev = out / "evidence"
    return {r.model_id: [x for v in Store(ev / f"{r.model_id}.jsonl").lines.values() for x in v]
            for r in manifest if (ev / f"{r.model_id}.jsonl").exists()}


def _cell(r: ManifestRow) -> str:
    return "+".join(f"{d}-{r.defects[d]:g}" for d in sorted(r.defects)) or "clean"


def summarise(manifest: list[ManifestRow], lines: dict[str, list[dict]], seeds) -> dict:
    """Per model and (item id, prevalence): per-seed items, score, seed sd, full-pool coverage.
    A model enters the score maps only when every requested seed is present."""
    per: dict[tuple[str, str, float | None], dict] = {}
    for mid, ls in lines.items():
        audit: dict[tuple[str, float | None], dict[int, EvidenceItem]] = {}
        full: dict[tuple[str, float | None], EvidenceItem] = {}
        for x in ls:
            it = EvidenceItem.model_validate(x["item"])
            if x["pool"] == "full":
                full[(it.id, x["prevalence"])] = it
            else:
                audit.setdefault((it.id, x["prevalence"]), {})[x["audit_seed"]] = it
        for (iid, prev), by_seed in audit.items():
            if set(seeds) - set(by_seed):
                continue  # incomplete seeds: unscored (verdict INCOMPLETE)
            items = [by_seed[s] for s in seeds]
            tau = BINDING_TAU.get(iid)
            stat = ([p_exceeds(i.counts.k, i.counts.n, tau) if i.counts else None for i in items] if tau is not None
                    else [i.estimate for i in items])
            score = S.model_score(items, tau) if tau is not None else (
                S.legacy_score(items) if iid.startswith("legacy.") else
                (None if None in stat else sum(stat) / len(stat)))
            rec = {"model_id": mid, "item": iid, "prevalence": prev,
                   "statistic": "mean_p_exceeds_tau" if tau is not None else "mean_estimate", "score": score,
                   "seed_sd": statistics.stdev(stat) if len(stat) > 1 and None not in stat else None,
                   "n_seeds": len(items),
                   "uncomputable": ";".join(sorted({i.applicability for i in items if i.applicability != "applicable"}))}
            fp = full.get((iid, prev))
            if fp is not None and fp.counts is not None:
                rec["full_pool_estimate"] = fp.estimate
                rec["sampling_coverage"] = S.sampling_coverage(items, fp.estimate)
            per[(mid, iid, prev)] = rec
    return per


def _scores(per: dict, item: str, prev: float | None) -> dict[str, float | None]:
    return {mid: rec["score"] for (mid, iid, p), rec in per.items() if iid == item and p == prev}


def _prev(dim: str) -> float | None:
    return BINDING_PREVALENCE if dim == "shortcut" else None


def _f(x, nd=3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def render_md(manifest, per, integ, *, seeds, budget) -> str:
    scored = {mid for mid, *_ in per}
    out = ["# TrustBench-C v0 scorecard (generated)", "",
           f"Audit seeds {list(seeds)}, budget {budget}, models scored {len(scored)} of {len(manifest)} dev+val. "
           "Generated by `app.trustbench.run_scorecard`; criteria fixed by `docs/v2/trustbench/preregistration-c-v0.md`.",
           "", "## G1 primary outcomes", "",
           "| dimension | binding item | AUROC @ medium (pos/neg) | false alarm k/n | diff vs v1 [95% CI], p | uncomputable | verdict |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    g1 = {}
    for dim in S.DIMENSIONS:
        new, old = _scores(per, S.BINDING[dim][0], _prev(dim)), _scores(per, S.LEGACY[dim], _prev(dim))
        g = g1[dim] = S.g1_probe(dim, new, old, manifest)
        if g["verdict"] in ("INCOMPLETE", "UNDEFINED"):
            out.append(f"| {dim} | `{g['item']}` | missing {len(g['missing'])} ({g['n_pos']}/{g['n_neg']}) | | | | {g['verdict']} |")
            continue
        fa = f"{g['fa_k']}/{g['fa_n']} ({'pass' if g['fa_pass'] else 'fail'})"
        beat = (f"{g['diff']:+.3f} [{g['diff_ci'][0]:+.3f}, {g['diff_ci'][1]:+.3f}], p={g['p']:.4f}"
                if g["beats"] is not None else f"undefined: {g['beats_undefined']}")
        out.append(f"| {dim} | `{g['item']}` | {_f(g['auroc_medium'])} ({g['n_pos']}/{g['n_neg']}) | {fa} | {beat} "
                   f"| {', '.join(g['uncomputable']) or '-'} | {g['verdict']} |")

    out += ["", "## AUROC by dose", ""]
    for dim in S.DIMENSIONS:
        new = {m: v for m, v in _scores(per, S.BINDING[dim][0], _prev(dim)).items() if v is not None}
        old = {m: v for m, v in _scores(per, S.LEGACY[dim], _prev(dim)).items() if v is not None}
        a_new, a_old = S.auroc_by_dose(new, manifest, dim), S.auroc_by_dose(old, manifest, dim)
        out += [f"### {dim}", "", f"| dose | `{S.BINDING[dim][0]}` | `{S.LEGACY[dim]}` |", "| --- | --- | --- |"]
        out += [f"| {d:g} | {_f(a_new.get(d))} | {_f(a_old.get(d))} |" for d in DOSES[dim]]
        if all(d in a_new and d in a_old for d in DOSES[dim]):
            out += ["", S.mermaid_dose_chart(dim, list(DOSES[dim]),
                                             {"new": [a_new[d] for d in DOSES[dim]], "legacy": [a_old[d] for d in DOSES[dim]]})]
        out.append("")
    out += ["### shortcut, descriptive audit prevalences", "", "| prevalence | " + " | ".join(f"{d:g}" for d in DOSES["shortcut"]) + " |",
            "| --- |" + " --- |" * 4]
    for prev in (0.0, BINDING_PREVALENCE, 0.30):
        sc = {m: v for m, v in _scores(per, S.BINDING["shortcut"][0], prev).items() if v is not None}
        a = S.auroc_by_dose(sc, manifest, "shortcut")
        out.append(f"| {prev:g} | " + " | ".join(_f(a.get(d)) for d in DOSES["shortcut"]) + " |")

    out += ["", "## Sampling coverage (same instrument; NOT validity)", "",
            "| binding item | mean share of seed intervals covering the full-pool estimate | models |", "| --- | --- | --- |"]
    for dim in S.DIMENSIONS:
        cov = [rec["sampling_coverage"] for (m, i, p), rec in per.items()
               if i == S.BINDING[dim][0] and p == _prev(dim) and "sampling_coverage" in rec]
        out.append(f"| `{S.BINDING[dim][0]}` | {_f(statistics.mean(cov) if cov else None)} | {len(cov)} |")

    out += ["", "## Leakage matrix (AUROC vs clean; ideal about 0.5)", ""]
    lk = S.leakage_matrix({d: {m: v for m, v in _scores(per, S.BINDING[d][0], _prev(d)).items() if v is not None}
                           for d in S.DIMENSIONS}, manifest)
    out += ["| models \\ probe | " + " | ".join(S.DIMENSIONS) + " |", "| --- |" + " --- |" * len(S.DIMENSIONS)]
    out += [f"| {g} | " + " | ".join(_f(row.get(d)) for d in S.DIMENSIONS) + " |" for g, row in lk.items()]

    out += ["", "## Seed variance per probe (K8)", "",
            "| item | prevalence | mean SD over audit seeds | models |", "| --- | --- | --- | --- |"]
    for item, prev in sorted({(i, p) for (_, i, p) in per}, key=lambda x: (x[0], x[1] if x[1] is not None else -1)):
        sds = [rec["seed_sd"] for (m, i, p), rec in per.items() if i == item and p == prev and rec["seed_sd"] is not None]
        out.append(f"| `{item}` | {'-' if prev is None else f'{prev:g}'} | {_f(statistics.mean(sds) if sds else None, 4)} | {len(sds)} |")

    if integ is not None:
        t = integ["tamper"]
        out += ["", "## Integrity tamper table", "",
                f"Caught {sum(r['caught'] for r in t)} of {len(t)} (expected 11 of 12, gadget evades).", "",
                "| fixture | kind | expected detector / tier | caught | format_safety tier | findings |", "| --- | --- | --- | --- | --- | --- |"]
        out += [f"| {r['name']} | {r['kind']} | {r['expected_detector']} / {r['expected_tier']} | {'yes' if r['caught'] else 'no'} "
                f"| {r['format_safety_tier']} | " + "; ".join(f"{f['detector']}:{f['tier']}:{f['reason']}:{f['file']}" for f in r["findings"]) + " |"
                for r in t]
        c = integ["clean"]
        out += ["", f"Clean dev+val dirs scanned: {len(c)}; with a Tier A finding: "
                f"{sum(any(f['tier'] == 'A' for f in x['findings']) for x in c)}; "
                f"weights checked against manifest sha256: {sum(x['weights_recorded'] for x in c)}."]
    return "\n".join(out) + "\n"


def write_csv(path: Path, manifest: list[ManifestRow], per: dict) -> None:
    import csv

    split = {r.model_id: r for r in manifest}
    cols = ["model_id", "split", "cell", "item", "prevalence", "statistic", "score", "seed_sd", "n_seeds",
            "uncomputable", "full_pool_estimate", "sampling_coverage"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for k in sorted(per, key=lambda k: (k[0], k[1], -1 if k[2] is None else k[2])):
            rec = per[k]
            w.writerow({**rec, "split": split[rec["model_id"]].split, "cell": _cell(split[rec["model_id"]])})


def integrity(root: Path, manifest: list[ManifestRow], tamper_source: str) -> dict:
    tamper = root / "tamper"
    if not (tamper / "fixtures_manifest.json").exists():
        if tamper_source not in {r.model_id for r in manifest if not r.defects}:
            raise ValueError(f"tamper source {tamper_source!r} is not a dev/val clean model")
        tamper_fixtures(root / "models" / tamper_source, tamper)
    clean = []
    for r in manifest:
        d = root / "models" / r.model_id
        if not r.defects and (d / "train_manifest.json").exists():
            rec = {"model.safetensors": r.weights_sha256} if r.weights_sha256 else {}
            clean.append({"model_id": r.model_id, "weights_recorded": bool(rec),
                          "findings": S.integrity_findings(d, S.self_authoritative(d, rec))})
    return {"tamper": S.tamper_table(tamper), "clean": clean}


def run(
    root: Path, out: Path | None = None, *, seeds=AUDIT_SEEDS, budget: int = BUDGET, only: list[str] | None = None,
    eval_path: Path = EVAL_PATH, expected_sha: str | None = EVAL_SHA256, load=None, device: str = "cuda",
    full_pool: bool = True, do_integrity: bool = True, tamper_source: str = "clean__s1",
) -> dict:
    root = Path(root)
    out = Path(out) if out is not None else root
    manifest = read_manifest(root / "manifest.jsonl")  # dev + validation only; test sealed
    if only is not None:
        if bad := set(only) - {r.model_id for r in manifest}:
            raise ValueError(f"not dev/validation model ids: {sorted(bad)}")
        targets = [r for r in manifest if r.model_id in only]
    else:
        targets = manifest
    if load is None:
        from app.trustbench.predict import load_predict_proba  # lazy: torch

        def load(d):
            return load_predict_proba(d, device)

    eval_rows, eval_sha = load_eval(eval_path, expected_sha)
    score_models(root, out, targets, eval_rows, eval_sha, seeds=seeds, budget=budget, load=load, full_pool=full_pool)
    per = summarise(manifest, _collect(out, manifest), seeds)
    write_csv(out / "scorecard.csv", manifest, per)
    integ = integrity(root, manifest, tamper_source) if do_integrity else None
    if integ is not None:
        (out / "integrity.json").write_text(json.dumps(integ, indent=2), encoding="utf-8")
    (out / "scorecard.md").write_text(render_md(manifest, per, integ, seeds=seeds, budget=budget), encoding="utf-8")
    return per


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--out", type=Path, help="output dir (default: --root)")
    p.add_argument("--budgets", type=int, default=BUDGET, help="audit rows per seed (pre-registered: 1000)")
    p.add_argument("--audit-seeds", type=int, default=len(AUDIT_SEEDS), help="seeds 1..N (pre-registered: 5)")
    p.add_argument("--only", nargs="+", help="dev/validation model ids to score this run")
    p.add_argument("--device", default="cuda")
    p.add_argument("--no-full-pool", action="store_true")
    p.add_argument("--no-integrity", action="store_true")
    p.add_argument("--tamper-source", default="clean__s1")
    a = p.parse_args(argv)
    run(a.root, a.out, seeds=tuple(range(1, a.audit_seeds + 1)), budget=a.budgets, only=a.only, device=a.device,
        full_pool=not a.no_full_pool, do_integrity=not a.no_integrity, tamper_source=a.tamper_source)


if __name__ == "__main__":
    main()
