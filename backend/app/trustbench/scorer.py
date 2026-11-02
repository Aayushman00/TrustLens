"""TrustBench-C v0 scorer (docs/v2/trustbench/preregistration-c-v0.md). Pure: stdlib + scipy.

Model score = mean over audit seeds of P(binding rate > tau), recomputed here from each item's
``counts`` (never from a field a probe wrote), so this module is the single source of truth.
Legacy comparators: raw estimate, larger = worse, mean over seeds. A seed whose item is not
applicable makes the model uncomputable for that probe (score None) -> FAIL for the probe.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

from app.evidence import EvidenceItem
from app.integrity.opcode_scan import scan_file
from app.posterior.rates import bonferroni_level, jeffreys_interval, p_exceeds
from app.trustbench.generators import DOSES
from app.trustbench.manifest import ManifestRow

DIMENSIONS = ("fairness", "robustness", "shortcut", "safety")
BINDING = {  # dimension -> (binding item id, tau), content-moderation profile
    "fairness": ("fair.counterfactual.flip_rate", 0.05),
    "robustness": ("rob.invariance.worst.flip_rate", 0.15),
    "shortcut": ("exp.shortcut.insertion_flip_rate", 0.20),
    "safety": ("safe.severe.miss_rate", 0.40),
}
LEGACY = {"fairness": "legacy.fair.eod", "robustness": "legacy.rob.acc_drop",
          "shortcut": "legacy.exp.aopc", "safety": "legacy.safe.severe_fnr"}
MEDIUM = 1  # 0-based index of dose index 2 (the medium dose)
AUROC_PASS = 0.85
FALSE_ALARM_SCORE = 0.95
ALPHA = 0.05
PICKLE_SUFFIXES = {".bin", ".pt", ".pth", ".pkl", ".ckpt", ".pickle"}


def auroc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney AUROC, ties = 1/2; nan when either side is empty."""
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def model_score(items: list[EvidenceItem], tau: float) -> float | None:
    """Mean over audit seeds of P(rate > tau) from ``counts``; None if any seed is uncomputable."""
    if not items or any(i.applicability != "applicable" or i.counts is None for i in items):
        return None
    return sum(p_exceeds(i.counts.k, i.counts.n, tau) for i in items) / len(items)


def legacy_score(items: list[EvidenceItem]) -> float | None:
    """Mean over audit seeds of the raw comparator estimate (larger = worse)."""
    if not items or any(i.applicability != "applicable" or i.estimate is None for i in items):
        return None
    return sum(i.estimate for i in items) / len(items)


def single_dose(row: ManifestRow, dimension: str) -> float | None:
    return row.defects[dimension] if set(row.defects) == {dimension} else None


def auroc_by_dose(scores: dict[str, float], manifest: list[ManifestRow], dimension: str) -> dict[float, float]:
    """Per dose: single-defect models of ``dimension`` vs clean models (dev+val rows only; the
    manifest comes from ``read_manifest`` default). Models without a score are left out; the
    G1 verdict checks completeness separately."""
    neg = [scores[r.model_id] for r in manifest if not r.defects and r.model_id in scores]
    out = {}
    for d in DOSES[dimension]:
        pos = [scores[r.model_id] for r in manifest if single_dose(r, dimension) == d and r.model_id in scores]
        if pos:
            out[d] = auroc(pos, neg)
    return out


def false_alarm_rate(scores_clean: list[float], threshold: float = FALSE_ALARM_SCORE) -> tuple[int, int]:
    return sum(x >= threshold for x in scores_clean), len(scores_clean)


def false_alarm_pass(k: int, n: int) -> bool:
    """Pass iff false alarms <= floor(0.10 x n)."""
    return k <= n // 10


def _percentile_ci(draws: list[float]) -> tuple[float, float]:
    d, b = sorted(draws), len(draws)
    return d[int(0.025 * b)], d[math.ceil(0.975 * b) - 1]


def paired_auroc_diff(
    new: dict[str, float], old: dict[str, float], pos_ids, neg_ids, *, B: int = 2000, seed: int = 0,
) -> tuple[float, tuple[float, float], float]:
    """AUROC(new) - AUROC(old) on the same models; bootstrap over models stratified by
    positive/negative (random.Random(seed), positives then negatives per resample), percentile
    95 % CI, one-sided p = share of resamples with diff <= 0."""
    pos_ids, neg_ids = list(pos_ids), list(neg_ids)

    def diff(p, n):
        return auroc([new[m] for m in p], [new[m] for m in n]) - auroc([old[m] for m in p], [old[m] for m in n])

    rng = random.Random(seed)
    draws = []
    for _ in range(B):
        p = rng.choices(pos_ids, k=len(pos_ids))
        draws.append(diff(p, rng.choices(neg_ids, k=len(neg_ids))))
    return diff(pos_ids, neg_ids), _percentile_ci(draws), sum(d <= 0 for d in draws) / B


def sampling_coverage(item_runs: list[EvidenceItem], full_pool_estimate: float) -> float:
    """Share of audit-seed intervals (Jeffreys from counts, at the item's Bonferroni level) that
    cover the full-pool estimate. Same instrument: sampling coverage, NOT validity. An
    uncomputable run counts as not covering."""
    level = bonferroni_level(0.95, 3)

    def covers(i: EvidenceItem) -> bool:
        if i.applicability != "applicable" or i.counts is None:
            return False
        lo, hi = jeffreys_interval(i.counts.k, i.counts.n, level)
        return lo <= full_pool_estimate <= hi

    return sum(map(covers, item_runs)) / len(item_runs)


def leakage_matrix(scores: dict[str, dict[str, float]], manifest: list[ManifestRow]) -> dict[str, dict[str, float]]:
    """Rows: each defect dimension X (X-only models, all doses) with every OTHER dimension's probe,
    then each interaction pair "a+b" with every probe; AUROC vs clean (ideal about 0.5).
    Interaction models enter only here."""
    groups: dict[str, list[str]] = {}
    for r in manifest:
        if r.defects:
            groups.setdefault("+".join(sorted(r.defects)), []).append(r.model_id)
    clean = [r.model_id for r in manifest if not r.defects]
    out: dict[str, dict[str, float]] = {}
    for g in [d for d in DIMENSIONS if d in groups] + sorted(k for k in groups if "+" in k):
        out[g] = {}
        for dim, sc in scores.items():
            if dim == g:
                continue
            pos = [sc[m] for m in groups[g] if m in sc]
            if pos:
                out[g][dim] = auroc(pos, [sc[m] for m in clean if m in sc])
    return out


def g1_probe(
    dimension: str, new: dict[str, float | None], old: dict[str, float | None], manifest: list[ManifestRow],
) -> dict:
    """G1 primary outcomes for one probe. ``new``/``old`` map model_id -> score (None = uncomputable).
    INCOMPLETE while any medium-dose positive or clean model is unscored; UNDEFINED without any."""
    pos = [r.model_id for r in manifest if single_dose(r, dimension) == DOSES[dimension][MEDIUM]]
    neg = [r.model_id for r in manifest if not r.defects]
    uncomputable = sorted(m for m, v in new.items() if v is None)
    res = {"dimension": dimension, "item": BINDING[dimension][0], "comparator": LEGACY[dimension],
           "n_pos": len(pos), "n_neg": len(neg), "uncomputable": uncomputable}
    if not pos or not neg:
        return {**res, "verdict": "UNDEFINED", "missing": []}  # corpus lacks positives or clean models
    missing = [m for m in pos + neg if m not in new or m not in old]
    if missing:
        return {**res, "verdict": "INCOMPLETE", "missing": missing}
    ok = {m: v for m, v in new.items() if v is not None}
    res["auroc_medium"] = auroc([ok[m] for m in pos if m in ok], [ok[m] for m in neg if m in ok])
    res["fa_k"], res["fa_n"] = false_alarm_rate([ok[m] for m in neg if m in ok])
    res["fa_pass"] = false_alarm_pass(res["fa_k"], res["fa_n"])
    old_none = sorted(m for m in pos + neg if old[m] is None)
    if old_none or any(new[m] is None for m in pos + neg):
        res["beats"] = None  # not pre-registered: surfaced for the controller, never guessed
        res["beats_undefined"] = old_none or "new probe uncomputable on a G1 model"
    else:
        res["diff"], res["diff_ci"], res["p"] = paired_auroc_diff(new, old, pos, neg)
        res["beats"] = res["p"] < ALPHA
    if uncomputable or not res["auroc_medium"] >= AUROC_PASS or not res["fa_pass"] or res["beats"] is False:
        res["verdict"] = "FAIL"
    else:  # comparator uncomputable: criterion 3 has no pre-registered value, so no verdict is guessed
        res["verdict"] = "PASS" if res["beats"] else "NEEDS_RULING"
    return res


PREREG_SEEDS = (1, 2, 3, 4, 5)
PREREG_BUDGET = 1000
PREREG_SHORTCUT_PREVALENCE = 0.10
REPRODUCTIONS = ("fairness", "shortcut")  # v1 EOD and AOPC (Amendment A3)


def is_g1_config(seeds, budget: int, shortcut_prevalence: float) -> bool:
    """G1 verdicts exist only for the pre-registered run configuration."""
    return tuple(seeds) == PREREG_SEEDS and budget == PREREG_BUDGET and shortcut_prevalence == PREREG_SHORTCUT_PREVALENCE


def v1_failure(dimension: str, old: dict[str, float | None], manifest: list[ManifestRow]) -> dict:
    """Amendment A3: the v1 failure reproduces iff the v1 comparator's AUROC at medium dose
    (dev+val, same positives/negatives as G1) is < AUROC_PASS."""
    pos = [r.model_id for r in manifest if single_dose(r, dimension) == DOSES[dimension][MEDIUM]]
    neg = [r.model_id for r in manifest if not r.defects]
    res = {"dimension": dimension, "comparator": LEGACY[dimension], "n_pos": len(pos), "n_neg": len(neg)}
    if not pos or not neg:
        return {**res, "status": "UNDEFINED"}
    if any(m not in old for m in pos + neg):
        return {**res, "status": "INCOMPLETE"}
    if none := sorted(m for m in pos + neg if old[m] is None):
        return {**res, "status": "NEEDS_RULING", "uncomputable": none}
    a = auroc([old[m] for m in pos], [old[m] for m in neg])
    return {**res, "auroc_medium": a, "status": "REPRODUCED" if a < AUROC_PASS else "NOT REPRODUCED"}


# --- integrity (tamper table) ---

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(2**20), b""):
            h.update(b)
    return h.hexdigest()


def _files(model_dir: Path) -> dict[str, Path]:
    return {p.relative_to(model_dir).as_posix(): p for p in sorted(model_dir.rglob("*")) if p.is_file()}


def self_authoritative(model_dir: Path, recorded: dict[str, str]) -> dict[str, str]:
    """Authoritative manifest for a clean corpus dir: its current files, with ``recorded``
    (training-time hashes, e.g. model.safetensors -> manifest weights_sha256) taking precedence."""
    return {**{k: _sha256(p) for k, p in _files(Path(model_dir)).items()}, **recorded}


def hash_set(model_dir: Path, authoritative: dict[str, str]) -> list[dict]:
    """int.hash_set: {relative path -> sha256} vs the authoritative manifest; changed, extra or
    missing file -> Tier A."""
    got = {k: _sha256(p) for k, p in _files(Path(model_dir)).items()}
    out = []
    for k in sorted(set(got) | set(authoritative)):
        why = ("missing_file" if k not in got else "extra_file" if k not in authoritative
               else "hash_changed" if got[k] != authoritative[k] else None)
        if why:
            out.append({"detector": "int.hash_set", "tier": "A", "file": k, "reason": why})
    return out


def _is_pickle(p: Path) -> bool:
    if p.suffix.lower() in PICKLE_SUFFIXES:
        return True
    with open(p, "rb") as f:
        head = f.read(4)
    return head[:1] == b"\x80" or head == b"PK\x03\x04"


def format_safety(model_dir: Path) -> list[dict]:
    """int.format_safety: non-executing opcode scan of every pickle-format file (Tier A / B)."""
    out = []
    for k, p in _files(Path(model_dir)).items():
        if p.suffix != ".safetensors" and _is_pickle(p):
            r = scan_file(p)
            if r.tier:
                out.append({"detector": "int.format_safety", "tier": r.tier, "file": k, "reason": r.reason,
                            "flagged": r.flagged})
    return out


def integrity_findings(model_dir: Path, authoritative: dict[str, str]) -> list[dict]:
    return hash_set(model_dir, authoritative) + format_safety(model_dir)


def tamper_table(tamper_dir: Path) -> list[dict]:
    """One row per fixture: caught iff a finding has the fixture's expected detector AND tier
    (the allowlisted gadget, expected_detector "none", is never caught by design)."""
    tamper_dir = Path(tamper_dir)
    auth = json.loads((tamper_dir / "authoritative_manifest.json").read_text())
    rows = []
    for m in json.loads((tamper_dir / "fixtures_manifest.json").read_text()):
        f = integrity_findings(tamper_dir / m["name"], auth)
        fs = [x["tier"] for x in f if x["detector"] == "int.format_safety"]
        rows.append({
            "name": m["name"], "kind": m["kind"], "expected_detector": m["expected_detector"],
            "expected_tier": m["expected_tier"], "known_evasion": m["known_evasion"],
            "caught": any((x["detector"], x["tier"]) == (m["expected_detector"], m["expected_tier"]) for x in f),
            "format_safety_tier": "A" if "A" in fs else "B" if "B" in fs else None,
            "also_flagged_by": sorted({f"{x['detector']}:{x['tier']}:{x['reason']}" for x in f
                                       if (x["detector"], x["tier"]) != (m["expected_detector"], m["expected_tier"])}),
            "findings": f,
        })
    return rows


def integrity_verdict(tamper: list[dict], clean: list[dict]) -> str:
    """Pre-registered: PASS iff exactly 11 of 12 caught (detector AND tier), the one not caught is
    the known-evasion gadget, and no scanned clean dir has a Tier A finding."""
    missed = [r for r in tamper if not r["caught"]]
    ok = (len(tamper) == 12 and len(missed) == 1 and missed[0]["known_evasion"]
          and not any(f["tier"] == "A" for c in clean for f in c["findings"]))
    return "PASS" if ok else "FAIL"


# --- rendering ---

def mermaid_dose_chart(title: str, doses: list[float], series: dict[str, list[float]]) -> str:
    """Mermaid xychart-beta line chart of AUROC vs dose (one line per series, named in the title)."""
    for name, v in series.items():
        if len(v) != len(doses) or any(not math.isfinite(x) for x in v):
            raise ValueError(f"series {name!r} needs one finite value per dose")
    lines = ["```mermaid", "xychart-beta", f'    title "{title} (lines: {", ".join(series)})"',
             "    x-axis \"dose\" [" + ", ".join(f'"{d:g}"' for d in doses) + "]",
             '    y-axis "AUROC" 0 --> 1']
    lines += ["    line [" + ", ".join(f"{x:.4f}" for x in v) + "]" for v in series.values()]
    return "\n".join(lines + ["```"])
