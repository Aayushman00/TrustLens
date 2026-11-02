"""TrustBench scorer + scorecard CLI (Task 13) with fake predict_proba; no model, no GPU."""

import hashlib
import json

import pytest

from app.evidence import EvidenceInputs, EvidenceItem
from app.posterior.rates import p_exceeds
from app.trustbench import generators as g
from app.trustbench import scorer as s
from app.trustbench.manifest import ManifestRow, write_manifest

INP = EvidenceInputs(model_ref="tb/x@local", dataset_sha256="0" * 64, methodology_version="t")


def _row(mid, defects, seed, split="dev", pilot=False):
    return ManifestRow(mid, defects, seed, split, "h", None, "base", 10, 3, pilot)


def test_auroc_perfect_and_chance():
    assert s.auroc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert s.auroc([0.0], [1.0]) == 0.0
    assert s.auroc([0.3, 0.3, 0.3], [0.3] * 4) == 0.5


def test_auroc_ties_half():
    # pairs: (1, .5)=1, (1, 0)=1, (.5, .5)=1/2, (.5, 0)=1
    assert s.auroc([1.0, 0.5], [0.5, 0.0]) == pytest.approx(3.5 / 4)


def test_false_alarm_counts():
    assert s.false_alarm_rate([0.96, 0.95, 0.94, 0.1]) == (2, 4)
    assert s.false_alarm_rate([0.5], threshold=0.4) == (1, 1)
    assert s.false_alarm_pass(1, 17) and not s.false_alarm_pass(2, 17)  # floor(0.10 x 17) = 1
    assert s.false_alarm_pass(2, 20) and not s.false_alarm_pass(1, 9)


def test_paired_diff_zero_for_identical():
    sc = {"p1": 0.9, "p2": 0.4, "n1": 0.5, "n2": 0.1, "n3": 0.4}
    diff, ci, p = s.paired_auroc_diff(sc, dict(sc), ["p1", "p2"], ["n1", "n2", "n3"])
    assert diff == 0.0 and ci == (0.0, 0.0) and p == 1.0


def test_paired_diff_new_beats_chance_comparator():
    pos, neg = [f"p{i}" for i in range(7)], [f"n{i}" for i in range(17)]
    new = {**{m: 0.9 for m in pos}, **{m: 0.1 for m in neg}}
    old = {m: 0.5 for m in pos + neg}
    diff, (lo, hi), p = s.paired_auroc_diff(new, old, pos, neg, B=200)
    assert diff == 0.5 and lo == hi == 0.5 and p == 0.0


def _rate(k, n):
    return EvidenceItem.rate("safe.severe.miss_rate", k, n, direction="higher_is_worse", inputs=INP)


def test_coverage_all_inside():
    runs = [_rate(10, 100) for _ in range(5)]
    assert s.sampling_coverage(runs, 0.10) == 1.0
    assert s.sampling_coverage(runs, 0.90) == 0.0
    na = EvidenceItem(**{**_rate(1, 2).model_dump(), "applicability": "insufficient_evidence(x)",
                         "estimate": None, "counts": None, "uncertainty": None})
    assert s.sampling_coverage(runs[:1] + [na], 0.10) == 0.5  # uncomputable run never covers


def test_model_score_recomputed_from_counts_not_probe_fields():
    a = _rate(30, 100)
    b = a.model_copy(update={"inputs": a.inputs.model_copy(update={"config": {"p_exceeds_tau": 0.0}}),
                             "estimate": 0.0})
    want = (p_exceeds(30, 100, 0.4) + p_exceeds(30, 100, 0.4)) / 2
    assert s.model_score([a, b], 0.4) == pytest.approx(want)
    na = EvidenceItem(**{**a.model_dump(), "applicability": "insufficient_evidence(no_severe_rows)",
                         "estimate": None, "counts": None, "uncertainty": None})
    assert s.model_score([a, na], 0.4) is None and s.model_score([], 0.4) is None


def test_auroc_by_dose_single_defect_only():
    man = [_row("clean__s1", {}, 1), _row("clean__s2", {}, 2, "validation"),
           _row("fairness-0.40__s1", {"fairness": 0.4}, 1), _row("fairness-0.70__s1", {"fairness": 0.7}, 1),
           _row("fairness-0.40+robustness-0.20__s1", {"fairness": 0.4, "robustness": 0.2}, 1)]
    sc = {"clean__s1": 0.1, "clean__s2": 0.95, "fairness-0.40__s1": 0.5, "fairness-0.70__s1": 1.0,
          "fairness-0.40+robustness-0.20__s1": 0.0}
    assert s.auroc_by_dose(sc, man, "fairness") == {0.4: 0.5, 0.7: 1.0}
    lk = s.leakage_matrix({"fairness": sc, "robustness": sc}, man)
    assert lk["fairness+robustness"]["fairness"] == 0.0 and "robustness" not in lk  # no robustness-only rows
    assert s.g1_probe("robustness", sc, sc, man)["verdict"] == "UNDEFINED"  # no positives: never PASS/FAIL
    g = s.g1_probe("fairness", {**sc, "clean__s2": None}, sc, man)
    assert g["verdict"] == "FAIL" and g["uncomputable"] == ["clean__s2"]  # uncomputable probe = FAIL
    perfect = {"clean__s1": 0.0, "clean__s2": 0.0, "fairness-0.40__s1": 1.0}
    assert s.g1_probe("fairness", perfect, {**perfect, "clean__s1": None}, man)["verdict"] == "NEEDS_RULING"


def test_mermaid_dose_chart_string():
    out = s.mermaid_dose_chart("fair", [0.2, 0.4], {"new": [0.5, 1.0], "legacy": [0.25, 0.75]})
    assert out == (
        "```mermaid\nxychart-beta\n    title \"fair (lines: new, legacy)\"\n"
        "    x-axis \"dose\" [\"0.2\", \"0.4\"]\n    y-axis \"AUROC\" 0 --> 1\n"
        "    line [0.5000, 1.0000]\n    line [0.2500, 0.7500]\n```"
    )
    with pytest.raises(ValueError):
        s.mermaid_dose_chart("x", [0.2], {"new": [float("nan")]})


def _clean_dir(p):
    p.mkdir(parents=True)
    (p / "model.safetensors").write_bytes(bytes(range(256)) * 16)
    (p / "config.json").write_text('{"model_type": "bert"}')
    (p / "_trainer_tmp").mkdir()  # real model dirs carry an empty trainer dir
    (p / "train_manifest.json").write_text("{}")  # training-complete marker
    return p


def test_tamper_table_11_of_12_and_clean_quiet(tmp_path):
    clean = _clean_dir(tmp_path / "clean")
    g.tamper_fixtures(clean, tmp_path / "tamper")
    table = s.tamper_table(tmp_path / "tamper")
    assert len(table) == 12 and sum(r["caught"] for r in table) == 11
    gad = next(r for r in table if r["name"] == "gadget_allowlisted")
    assert not gad["caught"] and gad["format_safety_tier"] is None
    deny = [r for r in table if r["kind"] == "denylist_pickle"]
    assert all(r["caught"] and r["format_safety_tier"] == "A" for r in deny)
    auth = {"model.safetensors": hashlib.sha256((clean / "model.safetensors").read_bytes()).hexdigest()}
    assert s.integrity_findings(clean, s.self_authoritative(clean, auth)) == []
    bad = s.self_authoritative(clean, {"model.safetensors": "0" * 64})
    assert [(f["detector"], f["tier"]) for f in s.integrity_findings(clean, bad)] == [("int.hash_set", "A")]


# --- CLI end to end on a tiny corpus ---

def _fake_p(texts):
    return [round(int(hashlib.sha256(t.encode()).hexdigest()[:4], 16) / 65535, 4) for t in texts]


def _eval_rows():
    rows = []
    for i in range(400):
        term = ("muslim", "tall", "black")[i % 3]
        rows.append({"text": f"my {term} neighbour wrote note {i} about the weather today",
                     "label": int(i % 4 == 0), "identity_ref": int(i % 3 != 1), "severe": int(i % 8 == 0)})
    return rows


def test_scorer_never_sees_test_split(tmp_path):
    from app.trustbench import run_scorecard as rs

    root = tmp_path / "root"
    man = [_row("clean__s1", {}, 1), _row("clean__s2", {}, 2, "validation"),
           _row("fairness-0.40__s1", {"fairness": 0.4}, 1),
           _row("clean__s3", {}, 3, "test", pilot=True), _row("fairness-0.40__s2", {"fairness": 0.4}, 2, "test")]
    for r in man:
        _clean_dir(root / "models" / r.model_id)
    write_manifest(man, root / "manifest.jsonl")
    ev = tmp_path / "eval.jsonl"
    ev.write_text("".join(json.dumps(r) + "\n" for r in _eval_rows()))
    seen = []

    def load(d):
        seen.append(d.name)
        return _fake_p

    kw = dict(seeds=(1, 2), budget=200, eval_path=ev, expected_sha=None, load=load, tamper_source="clean__s1")
    rs.run(root, tmp_path / "out", **kw)
    assert sorted(set(seen)) == ["clean__s1", "clean__s2", "fairness-0.40__s1"]
    texts = [p.read_text(encoding="utf-8") for p in (tmp_path / "out").rglob("*") if p.is_file()]
    assert texts and all("clean__s3" not in t and "fairness-0.40__s2" not in t for t in texts)
    lines = (tmp_path / "out" / "evidence" / "clean__s1.jsonl").read_text().splitlines()
    assert {json.loads(x)["split"] for x in lines} == {"dev"}
    assert (tmp_path / "out" / "scorecard.csv").exists() and (tmp_path / "out" / "scorecard.md").exists()

    seen.clear()  # resumable: every (model, probe, seed[, prevalence]) is done, so nothing reloads
    rs.run(root, tmp_path / "out", **kw)
    assert seen == []
    assert (tmp_path / "out" / "evidence" / "clean__s1.jsonl").read_text().splitlines() == lines
