"""L7: Integrity verifies the actual model artifact set (tl-integrity-v1.2).

Statuses: VERIFIED, MISMATCH, INCOMPLETE, UNPINNED, UNSUPPORTED. Only MISMATCH
(changed or unexpected artifact vs an authoritative manifest) is a risk
(I-INT-BYTES-DIVERGE); a missing manifest or missing metadata is never a risk.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.probes import integrity_artifact as ia
from app.probes.base import ProbeContext
from app.probes.integrity import IntegrityProbe
from app.probes.integrity_stats import (
    METHODOLOGY_VERSION,
    RISK_BYTES_DIVERGE,
    RISK_LICENSE_UNDISCLOSED,
)
from app.schemas.probe_config import ProbeConfigV1
from app.scripts.compare_ground_truth import evidence_flag_one
from tests.fakes import FakeEvidenceStore

CONFIG = b'{"model_type": "bert"}'
GOOD_META = {"card_text": "card", "card_data": {"license": "mit"}}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _single(tmp_path: Path) -> Path:
    d = tmp_path / "single"
    d.mkdir()
    (d / "model.safetensors").write_bytes(b"weights")
    (d / "config.json").write_bytes(CONFIG)
    (d / "README.md").write_text("card", encoding="utf-8")
    return d


def _sharded(tmp_path: Path) -> Path:
    d = tmp_path / "sharded"
    d.mkdir()
    shards = ["model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors"]
    for i, s in enumerate(shards):
        (d / s).write_bytes(f"shard{i}".encode())
    index = {"metadata": {}, "weight_map": {"a.weight": shards[0], "b.weight": shards[1], "c.weight": shards[1]}}
    (d / "model.safetensors.index.json").write_text(json.dumps(index), encoding="utf-8")
    (d / "config.json").write_bytes(CONFIG)
    return d


def _pin(d: Path) -> dict:
    manifest = ia.build_artifact_manifest(d)
    (d / ia.ARTIFACT_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _ctx(ref: str, meta: dict | None = None, store: FakeEvidenceStore | None = None) -> ProbeContext:
    return ProbeContext(
        evaluation_id=uuid.uuid4(), model_ref=ref, model_metadata=meta or GOOD_META,
        probe_config=ProbeConfigV1(), evidence_store=store or FakeEvidenceStore(),  # type: ignore[arg-type]
        model_revision="local",
    )


# --- enumeration + verification --------------------------------------------------


def test_single_checkpoint_set_is_weights_plus_loader_files(tmp_path: Path) -> None:
    av = ia.verify_local_artifacts(_single(tmp_path))
    assert av["format"] == "safetensors" and av["sharded"] is False
    assert [f["name"] for f in av["files"]] == ["config.json", "model.safetensors"]  # README not in the set
    assert av["files"][1]["sha256"] == _sha(b"weights")
    assert av["status"] == "UNPINNED" and av["manifest"] is None


def test_sharded_checkpoint_enumerates_index_and_every_shard(tmp_path: Path) -> None:
    av = ia.verify_local_artifacts(_sharded(tmp_path))
    assert av["sharded"] is True and av["index_file"] == "model.safetensors.index.json"
    assert [f["name"] for f in av["files"]] == [
        "config.json", "model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors",
        "model.safetensors.index.json",
    ]
    assert av["status"] == "UNPINNED"


def test_matching_manifest_is_verified(tmp_path: Path) -> None:
    d = _sharded(tmp_path)
    manifest = _pin(d)
    av = ia.verify_local_artifacts(d)
    assert av["status"] == "VERIFIED" and av["mismatches"] == []
    assert av["manifest"]["source"] == ia.ARTIFACT_MANIFEST
    assert av["manifest"]["sha256"] == ia.manifest_identity(manifest["files"])
    assert all(f["expected_sha256"] == f["sha256"] for f in av["files"])


def test_modified_shard_is_mismatch_with_details(tmp_path: Path) -> None:
    d = _sharded(tmp_path)
    _pin(d)
    (d / "model-00002-of-00002.safetensors").write_bytes(b"tampered")
    av = ia.verify_local_artifacts(d)
    assert av["status"] == "MISMATCH"
    assert av["mismatches"] == [{
        "name": "model-00002-of-00002.safetensors", "kind": "changed",
        "expected_sha256": _sha(b"shard1"), "observed_sha256": _sha(b"tampered"),
    }]


def test_missing_shard_is_incomplete(tmp_path: Path) -> None:
    d = _sharded(tmp_path)
    _pin(d)
    (d / "model-00001-of-00002.safetensors").unlink()
    av = ia.verify_local_artifacts(d)
    assert av["status"] == "INCOMPLETE"
    assert av["mismatches"][0]["name"] == "model-00001-of-00002.safetensors"
    assert av["mismatches"][0]["kind"] == "missing"


def test_missing_shard_named_by_index_is_incomplete_without_manifest(tmp_path: Path) -> None:
    d = _sharded(tmp_path)
    (d / "model-00002-of-00002.safetensors").unlink()
    av = ia.verify_local_artifacts(d)
    assert av["status"] == "INCOMPLETE"
    assert {"name": "model-00002-of-00002.safetensors", "kind": "missing"}.items() <= av["mismatches"][0].items()


def test_unexpected_weight_artifact_is_mismatch(tmp_path: Path) -> None:
    d = _single(tmp_path)
    _pin(d)
    (d / "pytorch_model.bin").write_bytes(b"other weights")
    av = ia.verify_local_artifacts(d)
    assert av["status"] == "MISMATCH"
    assert av["mismatches"][0]["name"] == "pytorch_model.bin" and av["mismatches"][0]["kind"] == "unexpected"


def test_unlisted_non_weight_file_is_unattested_not_mismatch(tmp_path: Path) -> None:
    d = _single(tmp_path)
    manifest = {"schema": ia.MANIFEST_SCHEMA, "files": {"model.safetensors": _sha(b"weights")}}
    (d / ia.ARTIFACT_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    av = ia.verify_local_artifacts(d)
    assert av["status"] == "VERIFIED"
    assert {f["name"]: f["state"] for f in av["files"]} == {"config.json": "unattested", "model.safetensors": "match"}


def test_operator_manifest_overrides_folder_manifest(tmp_path: Path) -> None:
    d = _single(tmp_path)
    _pin(d)
    op = {"schema": ia.MANIFEST_SCHEMA, "files": {"model.safetensors": "0" * 64, "config.json": _sha(CONFIG)}}
    av = ia.verify_local_artifacts(d, manifest=op)
    assert av["status"] == "MISMATCH" and av["manifest"]["source"] == "operator"


def test_legacy_train_manifest_verifies_weight_file_only(tmp_path: Path) -> None:
    d = _single(tmp_path)
    (d / "train_manifest.json").write_text(json.dumps({"model_safetensors_sha256": _sha(b"weights")}), encoding="utf-8")
    av = ia.verify_local_artifacts(d)
    assert av["status"] == "VERIFIED"
    assert av["manifest"]["source"] == "train_manifest" and av["manifest"]["coverage"] == "primary_weight_file_only"


def test_folder_without_supported_weights_is_unsupported(tmp_path: Path) -> None:
    d = tmp_path / "gguf"
    d.mkdir()
    (d / "model.gguf").write_bytes(b"x")
    av = ia.verify_local_artifacts(d)
    assert av["status"] == "UNSUPPORTED" and av["performed"] is False


# --- probe integration -----------------------------------------------------------


def test_verified_local_artifact_has_no_risk(tmp_path: Path) -> None:
    d = _sharded(tmp_path)
    _pin(d)
    m = IntegrityProbe().run(_ctx(str(d))).metric_values
    assert m["methodology_version"] == METHODOLOGY_VERSION == "tl-integrity-v1.2"
    assert m["artifact_verification"]["status"] == "VERIFIED"
    assert m["identity"]["hash_comparison"] == "match"
    assert m["risks_triggered"] == [] and m["aspect_scoring"] == "no_material_risk"


def test_modified_shard_is_a_bytes_diverge_risk(tmp_path: Path) -> None:
    d = _sharded(tmp_path)
    _pin(d)
    (d / "model-00001-of-00002.safetensors").write_bytes(b"tampered")
    m = IntegrityProbe().run(_ctx(str(d))).metric_values
    assert m["artifact_verification"]["status"] == "MISMATCH"
    assert m["identity"]["hash_comparison"] == "diverge"
    assert RISK_BYTES_DIVERGE in m["risks_triggered"]
    assert evidence_flag_one("INTEGRITY", m, None)


def test_incomplete_set_is_an_unverified_gate_not_a_risk(tmp_path: Path) -> None:
    d = _sharded(tmp_path)
    _pin(d)
    (d / "model-00002-of-00002.safetensors").unlink()
    m = IntegrityProbe().run(_ctx(str(d))).metric_values
    assert m["artifact_verification"]["status"] == "INCOMPLETE"
    assert m["risks_triggered"] == []
    assert "G-INT-ARTIFACT-INCOMPLETE" in m["reliability"]["failed_gates"]
    assert m["identity"]["hash_comparison"] == "not_performed"
    assert not evidence_flag_one("INTEGRITY", m, None)


def test_unpinned_local_artifact_is_content_addressed_not_a_risk(tmp_path: Path) -> None:
    d = _sharded(tmp_path)
    m = IntegrityProbe().run(_ctx(str(d))).metric_values
    av = m["artifact_verification"]
    assert av["status"] == "UNPINNED"
    assert m["identity"]["weight_hash"]["value"] == av["set_sha256"]
    assert m["checks"]["revision_pinned"]["pass"] is True
    assert m["risks_triggered"] == [] and m["disclosure_gaps"] == []
    assert not evidence_flag_one("INTEGRITY", m, None)


def test_single_unpinned_keeps_l3_weight_file_identity(tmp_path: Path) -> None:
    m = IntegrityProbe().run(_ctx(str(_single(tmp_path)))).metric_values
    assert m["identity"]["weight_hash"]["value"] == _sha(b"weights")


def test_disclosure_gap_with_verified_artifact_is_not_a_risk(tmp_path: Path) -> None:
    d = _single(tmp_path)
    _pin(d)
    m = IntegrityProbe().run(_ctx(str(d), {"card_text": "", "card_data": {}})).metric_values
    assert m["artifact_verification"]["status"] == "VERIFIED"
    assert RISK_LICENSE_UNDISCLOSED in m["disclosure_gaps"]
    assert m["risks_triggered"] == [] and m["aspect_scoring"] == "disclosure_gap"
    assert not evidence_flag_one("INTEGRITY", m, None)


def test_artifact_verification_is_persisted_in_evidence_artifact(tmp_path: Path) -> None:
    d = _single(tmp_path)
    _pin(d)
    store = FakeEvidenceStore()
    IntegrityProbe().run(_ctx(str(d), store=store))
    (blob,) = store.objects.values()
    assert json.loads(blob)["artifact_verification"]["status"] == "VERIFIED"


# --- Hub sharded checkpoint --------------------------------------------------------


def _hub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lfs: dict[str, str], local: dict[str, bytes]) -> None:
    sibs = [SimpleNamespace(rfilename=n, lfs=SimpleNamespace(sha256=s)) for n, s in lfs.items()]
    sibs.append(SimpleNamespace(rfilename="model.safetensors.index.json", lfs=None))
    sibs.append(SimpleNamespace(rfilename="config.json", lfs=None))
    files = {n: tmp_path / n for n in local}
    for n, b in local.items():
        files[n].write_bytes(b)
    index = tmp_path / "model.safetensors.index.json"
    index.write_text(json.dumps({"weight_map": {f"w{i}": n for i, n in enumerate(lfs)}}), encoding="utf-8")
    files["model.safetensors.index.json"] = index
    monkeypatch.setattr(ia, "_model_info", lambda repo, revision, token: SimpleNamespace(siblings=sibs))
    monkeypatch.setattr(ia, "_download", lambda repo, filename, revision, token: str(files[filename]))


def test_hub_sharded_checkpoint_verifies_every_shard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shards = {"model-00001-of-00002.safetensors": b"s1", "model-00002-of-00002.safetensors": b"s2"}
    _hub(monkeypatch, tmp_path, {n: _sha(b) for n, b in shards.items()}, shards)
    out = ia.hub_weight_hashes("org/m", "a" * 40, None)
    av = out["artifact_verification"]
    assert av["status"] == "VERIFIED" and av["sharded"] is True
    assert [f["name"] for f in av["files"]] == list(shards)
    assert out["trusted_reference"]["value"] == out["local_artifact_hash"]["value"]


def test_hub_sharded_modified_shard_diverges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shards = {"model-00001-of-00002.safetensors": b"s1", "model-00002-of-00002.safetensors": b"XX"}
    _hub(monkeypatch, tmp_path, {"model-00001-of-00002.safetensors": _sha(b"s1"),
                                 "model-00002-of-00002.safetensors": _sha(b"s2")}, shards)
    out = ia.hub_weight_hashes("org/m", "a" * 40, None)
    assert out["artifact_verification"]["status"] == "MISMATCH"
    assert out["trusted_reference"]["value"] != out["local_artifact_hash"]["value"]
