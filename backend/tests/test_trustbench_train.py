import json

import pytest

from app.trustbench import train as T
from app.trustbench.manifest import read_manifest

BASE = [
    {"text": f"t{i}", "label": i % 2, "identity_ref": i % 3 == 0, "severe": 0}
    for i in range(8000)
]
IDS = ["clean__s1", "clean__s2", "clean__s3"]


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(spec, *, seed, data_dir, models_dir):
        assert (data_dir / spec.train_file).exists() and (data_dir / spec.data_manifest_file).exists()
        assert (spec.lr, spec.batch_size) == (2e-5, 32)
        d = models_dir / spec.name
        d.mkdir(parents=True)
        (d / "model.safetensors").write_bytes(spec.name.encode())
        dm = json.loads((data_dir / spec.data_manifest_file).read_text())
        (d / "train_manifest.json").write_text(json.dumps({"data_manifest": dm}))  # written last, like the real one
        seen.append((spec.name, seed, spec.epochs))

    monkeypatch.setattr(T, "train_variant", fake)
    # slicing all 122 plan entries is not what is under test (see test_trustbench_generators)
    monkeypatch.setattr(T, "make_train_slice", lambda base, d, *, seed: (
        [{"text": "a", "label": 0}],
        {"sha256": f"{sorted(d.items())}{seed}", "train_rows": 1, "epochs": 3}))
    return seen


def test_train_all_skips_existing(tmp_path, calls):
    assert T.train_all(tmp_path, BASE, only=IDS) == 3
    assert T.train_all(tmp_path, BASE, only=IDS) == 0
    assert len(calls) == 3


def test_manifest_written_with_hashes(tmp_path, calls):
    T.train_all(tmp_path, BASE, only=IDS[:2])
    (tmp_path / "models" / "clean__s1" / "model.safetensors").write_bytes(b"x")  # hash filled from disk
    T.train_all(tmp_path, BASE, only=[])
    rows = {r.model_id: r for r in read_manifest(tmp_path / "manifest.jsonl", include_test=True)}
    assert len(rows) == 122
    assert rows["clean__s1"].weights_sha256 != rows["clean__s2"].weights_sha256 is not None
    assert rows["clean__s3"].weights_sha256 is None
    assert json.loads((tmp_path / "data" / "clean__s1_manifest.json").read_text())["epochs"] == 3


def test_limit_trains_n(tmp_path, calls):
    assert T.train_all(tmp_path, BASE, limit=2) == 2
    assert len(calls) == 2


def test_partial_dir_moved_aside_and_retrained(tmp_path, calls):
    part = tmp_path / "models" / "clean__s1"
    part.mkdir(parents=True)
    (part / "model.safetensors").write_bytes(b"torn")  # weights but no train_manifest.json
    assert T.train_all(tmp_path, BASE, only=["clean__s1"]) == 1
    moved = [p for p in (tmp_path / "models").iterdir() if ".incomplete-" in p.name]
    assert len(moved) == 1 and (moved[0] / "model.safetensors").read_bytes() == b"torn"
    assert (part / "model.safetensors").read_bytes() == b"clean__s1"


def test_resume_rejects_data_hash_mismatch(tmp_path, calls, monkeypatch):
    T.train_all(tmp_path, BASE, only=["clean__s1"])
    monkeypatch.setattr(T, "make_train_slice", lambda base, d, *, seed: (
        [{"text": "a", "label": 0}], {"sha256": "other", "train_rows": 1, "epochs": 3}))
    before = (tmp_path / "data" / "clean__s1_manifest.json").read_text()
    with pytest.raises(ValueError, match="clean__s1.*other"):
        T.train_all(tmp_path, BASE, only=["clean__s1"])
    assert (tmp_path / "data" / "clean__s1_manifest.json").read_text() == before


def test_pilot_exposed_only_for_test_split_pilot_models(tmp_path, calls):
    T.train_all(tmp_path, BASE, only=[])
    rows = {r.model_id: r for r in read_manifest(tmp_path / "manifest.jsonl", include_test=True)}
    assert {m for m, r in rows.items() if r.pilot_exposed} == {m for m in T.PILOT_IDS if rows[m].split == "test"}
    assert any(r.pilot_exposed for r in rows.values())
