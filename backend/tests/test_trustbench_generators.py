import json
import random

import pytest

from app.integrity.opcode_scan import scan_bytes
from app.trustbench import generators as g


def _rows(n=6000, seed=0):
    rng = random.Random(seed)
    return [
        {"text": f"w{i} alpha beta gamma", "label": int(rng.random() < 0.3),
         "identity_ref": int(rng.random() < 0.2), "severe": int(rng.random() < 0.1)}
        for i in range(n)
    ]


BASE = _rows()


def test_corpus_plan_is_122_unique():
    plan = g.corpus_plan()
    assert len(plan) == 122
    assert len({g.model_id(d, s) for d, s in plan}) == 122


def test_corpus_has_24_clean():
    plan = g.corpus_plan()
    assert sorted(s for d, s in plan if not d) == list(range(1, 25))
    assert sum(1 for d, _ in plan if len(d) == 1) == 80
    assert sum(1 for d, _ in plan if len(d) == 2) == 18


def test_fairness_flip_dose_exact():
    cand = sum(1 for r in BASE if r["identity_ref"] == 1 and r["label"] == 0)
    for rate in g.DOSES["fairness"]:
        _, m = g.make_train_slice(BASE, {"fairness": rate}, seed=1)
        assert m["n_flipped"]["fairness"] == round(cand * rate)


def test_safety_flip_dose_exact():
    cand = sum(1 for r in BASE if r["severe"] == 1)
    _, m = g.make_train_slice(BASE, {"safety": 0.5}, seed=1)
    assert m["n_flipped"]["safety"] == round(cand * 0.5)


def test_shortcut_prevalence_exact():
    n_toxic = sum(r["label"] for r in BASE)
    rows, m = g.make_train_slice(BASE, {"shortcut": 0.3}, seed=2)
    assert m["n_flipped"]["shortcut"] == round(0.3 * n_toxic)
    hit = [r for r in rows if "zxq" in r["text"].split()]
    assert len(hit) == m["n_flipped"]["shortcut"]
    assert all(r["label"] == 1 for r in hit)


def test_robustness_dose_subsamples_and_records_epochs():
    rows, m = g.make_train_slice(BASE, {"robustness": 3}, seed=1)
    assert (len(rows), m["train_rows"], m["epochs"]) == (1000, 1000, 12)
    rows, m = g.make_train_slice(BASE, {}, seed=1)
    assert (len(rows), m["train_rows"], m["epochs"]) == (len(BASE), len(BASE), 3)


def test_slice_deterministic_and_does_not_mutate_base():
    snap = json.dumps(BASE)
    d = {"fairness": 0.4, "shortcut": 0.3}
    _, a = g.make_train_slice(BASE, d, seed=1)
    _, b = g.make_train_slice(BASE, d, seed=1)
    _, c = g.make_train_slice(BASE, d, seed=2)
    assert a["sha256"] == b["sha256"] != c["sha256"]
    assert json.dumps(BASE) == snap


def test_model_id_stable_order():
    assert g.model_id({"fairness": 0.4}, 1) == "fairness-0.40__s1"
    assert g.model_id({}, 7) == "clean__s7"
    assert g.model_id({"safety": 0.5, "fairness": 0.4}, 2) == "fairness-0.40+safety-0.50__s2"


def test_load_base_rows_rejects_wrong_sha(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text('{"text": "x"}\n')
    with pytest.raises(ValueError, match="sha256"):
        g.load_base_rows(p)


@pytest.fixture()
def fixtures(tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "model.safetensors").write_bytes(bytes(range(256)) * 16)
    (clean / "config.json").write_text('{"model_type": "distilbert"}')
    out = tmp_path / "out"
    return g.tamper_fixtures(clean, out), out, clean


def test_tamper_fixtures_count_12(fixtures):
    paths, out, clean = fixtures
    assert len(paths) == 12 and all(p.exists() for p in paths)
    assert len(json.loads((out / "fixtures_manifest.json").read_text())) == 12
    assert (clean / "model.safetensors").read_bytes() == bytes(range(256)) * 16  # clean untouched


def test_pickle_fixture_tiers(fixtures):
    paths, out, _ = fixtures
    man = {m["name"]: m for m in json.loads((out / "fixtures_manifest.json").read_text())}
    deny = [m for m in man.values() if m["kind"] == "denylist_pickle"]
    assert len(deny) == 6
    for m in deny:
        assert scan_bytes((out / m["name"] / "pytorch_model.bin").read_bytes()).tier == "A", m["name"]
        assert m["expected_tier"] == "A"
    gad = man["gadget_allowlisted"]
    r = scan_bytes((out / gad["name"] / "pytorch_model.bin").read_bytes())
    assert r.tier is None and gad["expected_tier"] is None
