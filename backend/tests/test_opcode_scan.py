import io
import os
import pickle
import sys
import zipfile
from collections import OrderedDict
from dataclasses import dataclass

import pytest

from app.integrity.opcode_scan import DENYLIST_VERSION, scan_bytes, scan_file


class _Evil:
    def __reduce__(self):
        return (os.system, ("echo",))


class _Eval:
    def __reduce__(self):
        return (eval, ("1",))


@dataclass
class _Args:
    lr: float = 0.1


_Args.__module__ = "__main__"


def test_denylist_fixture_tier_a():
    r = scan_bytes(pickle.dumps(_Evil(), protocol=4))
    assert r.tier == "A" and r.reason == "denylist_hit"
    assert any(f in ("posix.system", "nt.system") for f in r.flagged)
    assert r.denylist_version == DENYLIST_VERSION == "integrity/denylist-v1"


def test_builtins_eval_tier_a():
    assert scan_bytes(pickle.dumps(_Eval(), protocol=2)).tier == "A"


def test_benign_state_dict_tier_none():
    r = scan_bytes(pickle.dumps(OrderedDict(a=1), protocol=2))
    assert r.tier is None and r.reason == "clean" and r.globals_total == 1


def test_main_class_is_tier_b(monkeypatch):
    monkeypatch.setattr(sys.modules["__main__"], "_Args", _Args, raising=False)
    r = scan_bytes(pickle.dumps(_Args(), protocol=4))
    assert r.tier == "B" and r.reason == "unknown_callable"


def test_stack_global_underflow_is_unknown():
    r = scan_bytes(b"\x80\x04\x93.")
    assert r.tier == "B" and "?.?" in r.flagged


def test_scan_garbage_is_tier_b():
    ok = pickle.dumps(OrderedDict(a=1), protocol=4)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "x")
    for data in (b"\x00" * 64, ok[:-3], buf.getvalue()):
        r = scan_bytes(data)
        assert r.tier == "B" and r.reason == "scan_not_possible"


def test_trailing_bytes_after_stop_tolerated():
    r = scan_bytes(pickle.dumps(OrderedDict(a=1), protocol=2) + b"\xff\x00raw")
    assert r.tier is None


def test_torch_zip_checkpoint():
    torch = pytest.importorskip("torch")
    buf = io.BytesIO()
    torch.save({"w": torch.zeros(2)}, buf)
    assert scan_bytes(buf.getvalue()).tier is None


def test_safetensors_not_pickle(tmp_path):
    p = tmp_path / "m.safetensors"
    p.write_bytes(b"x")
    r = scan_file(p)
    assert r.tier is None and r.reason == "not_pickle"


def test_never_unpickles(monkeypatch):
    data = pickle.dumps(_Evil(), protocol=4)

    def boom(*a, **k):
        raise AssertionError("unpickled")

    monkeypatch.setattr(pickle, "load", boom)
    monkeypatch.setattr(pickle, "loads", boom)
    assert scan_bytes(data).tier == "A"
