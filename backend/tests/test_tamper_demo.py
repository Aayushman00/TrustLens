from app.probes.integrity_eval import evaluate_integrity
from app.scripts.tamper_demo import integrity_extra_for, make_tampered_copy, sha256_file

META = {"card_text": "# m\n", "files": ["model.safetensors"], "card_data": {"license": "apache-2.0"}}
WEIGHTS = b"\x08" + b"\x00" * 7 + b"{}      " + b"\x01\x02\x03\x04"


def _run(extra):
    return evaluate_integrity(model_ref="x/y", model_revision="a" * 40, model_metadata=META,
                              integrity_extra=extra, live_files=None, live_files_error="n/a")


def test_untouched_file_matches(tmp_path):
    f = tmp_path / "model.safetensors"
    f.write_bytes(WEIGHTS)
    res = _run(integrity_extra_for(f, f))
    assert "I-INT-BYTES-DIVERGE" not in res.risks_triggered
    assert res.identity["hash_comparison"] == "match"


def test_tampered_copy_diverges(tmp_path):
    f = tmp_path / "model.safetensors"
    f.write_bytes(WEIGHTS)
    t = tmp_path / "t.safetensors"
    make_tampered_copy(f, t)
    assert t.stat().st_size == f.stat().st_size and sha256_file(t) != sha256_file(f)
    res = _run(integrity_extra_for(f, t))
    assert "I-INT-BYTES-DIVERGE" in res.risks_triggered


def test_missing_reference_is_not_a_pass(tmp_path):
    f = tmp_path / "model.safetensors"
    f.write_bytes(WEIGHTS)
    res = _run({"local_artifact_hash": integrity_extra_for(f, f)["local_artifact_hash"]})
    assert "I-INT-BYTES-DIVERGE" not in res.risks_triggered
    assert res.identity["hash_comparison"] == "not_performed"


def test_tampered_weights_floor_the_integrity_band(tmp_path):
    """End to end: tamper -> integrity evidence -> OSD band. Untouched stays high."""
    from app.osd.agent import _integrity_band

    f = tmp_path / "model.safetensors"
    f.write_bytes(WEIGHTS)
    t = tmp_path / "t.safetensors"
    make_tampered_copy(f, t)

    def band(local):
        res = _run(integrity_extra_for(f, local))
        checks = res.checks.values()
        m = {"risks_triggered": res.risks_triggered, "pass_count": sum(1 for c in checks if c.get("pass")),
             "fail_count": sum(1 for c in checks if not c.get("pass"))}
        return _integrity_band(m)[0]

    assert band(t) == (1, 1, 8)
    assert band(f)[0] > 1
