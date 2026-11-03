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


def _su(s):
    b = s.encode()
    return b"\x8c" + bytes([len(b)]) + b


_EVIL = b"\x80\x02cos\nsystem\nq\x00X\x04\x00\x00\x00echoq\x01\x85q\x02Rq\x03."
_BENIGN = b"\x80\x02ccollections\nOrderedDict\nq\x00)Rq\x01."


def _zip(*members):
    import warnings
    buf = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(buf, "w") as z:
        warnings.simplefilter("ignore")
        for n, d in members:
            z.writestr(n, d)
    return buf.getvalue()


def test_evade_pop_not_clean():
    p = b"\x80\x04" + _su("os") + _su("system") + _su("collections") + _su("OrderedDict") + b"00\x93" + _su("echo") + b"\x85R."
    assert scan_bytes(p).tier in ("A", "B")


def test_evade_pop_mark_not_clean():
    p = b"\x80\x04" + _su("os") + _su("system") + b"(" + _su("collections") + _su("OrderedDict") + b"1\x93" + _su("echo") + b"\x85R."
    assert scan_bytes(p).tier in ("A", "B")


def test_memo_drift_resolves_os_system():
    p = (b"\x80\x04}\x94" + _su("collections") + b"\x94" + _su("os") + b"\x94" + _su("OrderedDict") + b"\x94"
         + _su("system") + b"\x94" + b"0000" + b"h\x02h\x04\x93" + _su("echo") + b"\x85R.")
    r = scan_bytes(p)
    assert r.tier == "A" and "os.system" in r.flagged


def test_duplicate_zip_member_scanned():
    assert scan_bytes(_zip(("archive/data.pkl", _EVIL), ("archive/data.pkl", _BENIGN))).tier == "A"


def test_uppercase_member_scanned():
    assert scan_bytes(_zip(("archive/DATA.PKL", _EVIL), ("archive/decoy.pkl", _BENIGN))).tier == "A"


def test_proto_member_without_pkl_suffix_scanned():
    assert scan_bytes(_zip(("archive/x.pkl", _BENIGN), ("archive/payload", _EVIL))).tier == "A"


def test_nested_load_from_bytes_denylist_is_tier_a():
    inner = len(_EVIL).to_bytes(4, "little")
    p = b"\x80\x02ctorch.storage\n_load_from_bytes\nB" + inner + _EVIL + b"\x85R."
    r = scan_bytes(p)
    assert r.tier == "A" and "os.system" in r.flagged


def test_nested_benign_stays_tier_b():
    inner = len(_BENIGN).to_bytes(4, "little")
    p = b"\x80\x02ctorch.storage\n_load_from_bytes\nB" + inner + _BENIGN + b"\x85R."
    assert scan_bytes(p).tier == "B"


def test_dotted_submodule_denied():
    assert scan_bytes(b"\x80\x02ctorch.hub.foo\nbar\n)R.").tier == "A"


def test_ext_opcode_is_unknown():
    r = scan_bytes(b"\x80\x02\x82\x01)R.")
    assert r.tier == "B" and "?.?" in r.flagged


def test_memo_len_semantics_with_sparse_put():
    # BINPUT 2 collections, BINPUT 5 OrderedDict, MEMOIZE os -> slot len(memo)=2, filler PUTs 6-8, MEMOIZE system -> slot 5
    p = (b"\x80\x04" + _su("collections") + b"q\x02" + _su("OrderedDict") + b"q\x05" + b"0" * 0
         + b"0" + b"0" + _su("os") + b"\x94" + b"0" + _su("a") + b"q\x06" + b"0" + _su("b") + b"q\x07" + b"0"
         + _su("c") + b"q\x08" + b"0" + _su("system") + b"\x94" + b"0" + b"h\x02h\x05\x93" + _su("echo") + b"\x85R.")
    r = scan_bytes(p)
    assert r.tier == "A" and "os.system" in r.flagged


def test_nested_bytes_via_memo_get():
    inner = len(_EVIL).to_bytes(4, "little")
    p = (b"\x80\x02B" + inner + _EVIL + b"q\x00" + b"0" + b"ctorch.storage\n_load_from_bytes\nh\x00\x85R.")
    r = scan_bytes(p)
    assert r.tier == "A" and "os.system" in r.flagged


def test_raw_protocol0_pickle_starting_with_pk():
    r = scan_bytes(b"PK\ncos\nsystem\n(S'echo'\ntR.")
    assert r.tier == "A"


def _binbytes(b):
    return b"B" + len(b).to_bytes(4, "little") + b


def test_nested_tuple_wrapped_bytes_is_tier_a():
    p = (b"\x80\x04" + _binbytes(_EVIL) + b"\x85\x94" + b"ctorch.storage\n_load_from_bytes\n" + b"h\x00R.")
    r = scan_bytes(p)
    assert r.tier == "A" and "os.system" in r.flagged


def test_nested_repeated_get_is_scanned_once():
    import time
    # valid single stream of ~200k real opcodes, so every unmemoized rescan walks all of it
    inner = b"\x80\x02" + b"N0" * 100_000 + b"cos\nsystem\nX\x04\x00\x00\x00echo\x85R."
    p = (b"\x80\x04" + _binbytes(inner) + b"\x94" + b"ctorch.storage\n_load_from_bytes\n"
         + (b"h\x00\x85R0" * 500) + b".")
    t = time.perf_counter()
    r = scan_bytes(p)
    assert time.perf_counter() - t < 5
    assert r.tier == "A" and "os.system" in r.flagged


def test_nested_work_cap_is_tier_b():
    import app.integrity.opcode_scan as m
    inner = _BENIGN + b"\x00" * 100
    p = b"\x80\x04" + _binbytes(inner) + b"\x94" + b"ctorch.storage\n_load_from_bytes\n" + b"h\x00\x85R."
    gl, complete = m.globals_in(p, 0, [10])
    assert not complete


# I1: stack-neutral opcodes between the operands and STACK_GLOBAL must not downgrade Tier A to B.
_OS_SYS = _su("os") + _su("system")
_CALL = b"\x93" + _su("echo") + b"\x85R."


@pytest.mark.parametrize("filler", [
    b"N0",                              # NONE POP
    b")0",                              # EMPTY_TUPLE POP
    b"(1",                              # MARK POP_MARK
    b"(N" + _su("x") + b"1",            # MARK with items, POP_MARK
    b"((N1N01",                         # nested MARKs
    b"N0(1N0",                          # interleaved
    b"(N\x94t0",                        # MARK ... MEMOIZE TUPLE POP
    b"N200",                            # NONE DUP POP POP
    b"(0",                              # MARK POP: POP on an empty frame drops the mark
    b"(N00",                            # MARK NONE POP POP
])
def test_stack_neutral_filler_keeps_tier_a(filler):
    r = scan_bytes(b"\x80\x04" + _OS_SYS + filler + _CALL)
    assert r.tier == "A" and r.reason == "denylist_hit" and "os.system" in r.flagged


def test_filler_between_operands_keeps_tier_a():
    r = scan_bytes(b"\x80\x04" + _su("os") + b"(N1N0" + _su("system") + b"N0" + _CALL)
    assert r.tier == "A" and "os.system" in r.flagged


def test_memo_put_after_filler_keeps_tier_a():
    # strings memoized after a stack-neutral pair, then fetched back with GET
    p = b"\x80\x04" + _su("os") + b"N0\x94" + _su("system") + b"(1\x94" + b"00" + b"N0h\x00h\x01" + _CALL
    r = scan_bytes(p)
    assert r.tier == "A" and "os.system" in r.flagged


def test_memo_get_of_mark_wrapped_values_keeps_tier_a():
    p = b"\x80\x04(" + _su("os") + b"q\x07" + _su("system") + b"q\x09" + b"1" + b"N0h\x07(1h\x09" + _CALL
    r = scan_bytes(p)
    assert r.tier == "A" and "os.system" in r.flagged


def test_real_dumps_with_filler_is_tier_a():
    data = pickle.dumps(_Evil(), protocol=4)
    i = data.index(b"\x93")
    r = scan_bytes(data[:i] + b"N0(1" + data[i:])
    assert r.tier == "A" and any(f in ("posix.system", "nt.system") for f in r.flagged)


def test_non_string_operand_is_unknown():
    r = scan_bytes(b"\x80\x04" + _su("os") + b"N" + _CALL)
    assert r.tier == "B" and "?.?" in r.flagged
