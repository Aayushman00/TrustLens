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
        seen.append((spec.name, seed, spec.epochs))

    monkeypatch.setattr(T, "train_variant", fake)
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
