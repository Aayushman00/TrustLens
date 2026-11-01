"""Non-executing pickle scan for Integrity Tier A (K14). Walks opcodes with pickletools.genops; never unpickles.

Tier A = denylist hit only. Unknown callable or unparseable bytes = Tier B. Otherwise None.
"""
from __future__ import annotations

import hashlib
import io
import pickletools
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.integrity.denylist_v1 import ALLOW, DENY_MODULES, DENY_NAMES, DENYLIST_VERSION

STR_OPS = {"SHORT_BINUNICODE", "BINUNICODE", "UNICODE", "BINUNICODE8", "SHORT_BINSTRING", "BINSTRING", "STRING"}


@dataclass
class ScanResult:
    format: str
    globals_total: int
    tier: Literal["A", "B"] | None
    reason: str
    flagged: list[str] = field(default_factory=list)
    denylist_version: str = DENYLIST_VERSION


def classify(mod: str, name: str) -> str:
    if (mod, name) in ALLOW:
        return "allow"
    parts = mod.split(".")
    if (mod, name) in DENY_NAMES or any(".".join(parts[:i]) in DENY_MODULES for i in range(1, len(parts) + 1)):
        return "dangerous"
    return "unknown"


BYTES_OPS = {"BINBYTES", "SHORT_BINBYTES", "BINBYTES8", "BYTEARRAY8"}
GET_OPS = {"BINGET", "LONG_BINGET", "GET"}
PUT_OPS = {"BINPUT", "LONG_BINPUT", "PUT"}
KEEP_OPS = {"PROTO", "FRAME"}  # leave the modelled stack tail untouched
NESTED = ("torch.storage", "_load_from_bytes")  # carries a nested pickle in its bytes argument
MAX_DEPTH = 3


def globals_in(data: bytes, depth: int = 0, budget: list[int] | None = None) -> tuple[list[tuple[str, str]], bool]:
    """All GLOBAL/STACK_GLOBAL/INST targets across every pickle concatenated in `data`, and whether the scan
    completed. A stream that errors before any STOP is partial (False); bytes after a completed STOP are
    tolerated (legacy torch appends raw tensor bytes after the last pickle).

    `recent` models only the run of consecutive pushes right before the current opcode (str, or None for a
    non-string memo value); any other opcode clears it, so STACK_GLOBAL resolves only from two adjacent strings.

    If `_load_from_bytes` is resolved in a stream, each unique bytes literal of that stream is scanned once at its
    end as a nested pickle (depth <= MAX_DEPTH, cumulative work capped by `budget`)."""
    found: list[tuple[str, str]] = []
    complete = True
    f, stops = io.BytesIO(data), 0

    if budget is None:
        budget = [max(64 * 2**20, 4 * len(data))]

    def nested(blob: bytes) -> None:
        nonlocal complete
        if depth >= MAX_DEPTH or len(blob) > budget[0]:
            complete = False
            return
        budget[0] -= len(blob)
        g, c = _collect(blob, depth + 1, budget)
        found.extend(g)
        complete &= c

    while f.tell() < len(data):
        recent: list[str | bytes | None] = []
        memo: dict[int, str | bytes | None] = {}
        literals: dict[str, bytes] = {}  # sha256 -> bytes literal pushed in this stream
        has_nested, stopped = False, False
        try:
            for op, arg, _ in pickletools.genops(f):
                n = op.name
                if n in STR_OPS:
                    recent.append(arg if isinstance(arg, str) else str(arg))
                    continue
                if n in BYTES_OPS:
                    b = bytes(arg)
                    recent.append(b)
                    literals.setdefault(hashlib.sha256(b).hexdigest(), b)
                    continue
                if n in GET_OPS:
                    recent.append(memo.get(int(arg)))
                    continue
                if n == "MEMOIZE":  # CPython: memo[len(memo)] = stack[-1]
                    memo[len(memo)] = recent[-1] if recent else None
                    continue
                if n in PUT_OPS:
                    memo[int(arg)] = recent[-1] if recent else None
                    continue
                if n in KEEP_OPS:
                    continue
                if n in ("GLOBAL", "INST", "STACK_GLOBAL"):
                    if n == "STACK_GLOBAL":
                        ok = len(recent) >= 2 and isinstance(recent[-1], str) and isinstance(recent[-2], str)
                        g = (recent[-2], recent[-1]) if ok else ("?", "?")
                    else:
                        mod, _, name = str(arg).partition(" ")
                        g = (mod, name)
                    found.append(g)
                    has_nested |= g == NESTED
                elif n.startswith("EXT"):
                    found.append(("?", "?"))
                elif n == "STOP":
                    stopped = True
                    break
                recent.clear()
        except Exception:
            pass
        if has_nested:
            for blob in literals.values():
                nested(blob)
        if stopped:
            stops += 1
        else:  # errored or ran out of opcodes before STOP
            return found, complete and stops > 0
    return found, complete and stops > 0


def _pickle_members(z: zipfile.ZipFile) -> list[bytes]:
    out = []
    for i in z.infolist():  # infolist, not namelist: duplicate member names must all be scanned
        low = i.filename.lower()
        with z.open(i) as m:
            if low.endswith(".pkl"):
                out.append(m.read())
            elif not (low.startswith("data/") or "/data/" in low):
                head = m.read(1)
                if head == b"\x80":
                    out.append(head + m.read())
    return out


def _collect(data: bytes, depth: int = 0, budget: list[int] | None = None) -> tuple[list[tuple[str, str]], bool]:
    """Globals of `data` (torch zip or raw pickle); the bool is False when the scan is partial."""
    if data[:4] == b"PK\x03\x04":  # torch >= 1.6 zip checkpoint
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                pkls = _pickle_members(z)
        except Exception:
            return [], False
        if not pkls:
            return [], False
        gl, complete = [], True
        for p in pkls:
            g, c = globals_in(p, depth, budget)
            gl += g
            complete &= c
        return gl, complete
    return globals_in(data, depth, budget)


def _not_possible(fmt: str, gl: list[tuple[str, str]] = ()) -> ScanResult:
    return ScanResult(fmt, len(gl), "B", "scan_not_possible", sorted({f"{m}.{n}" for m, n in gl}))


def scan_bytes(data: bytes) -> ScanResult:
    fmt = "torch_zip" if data[:4] == b"PK\x03\x04" else "raw_or_legacy_pickle"
    gl, complete = _collect(data, 0, [max(64 * 2**20, 4 * len(data))])
    classes = [classify(m, n) for m, n in gl]
    flagged = sorted({f"{m}.{n}" for (m, n), c in zip(gl, classes) if c != "allow"})
    if "dangerous" in classes:
        return ScanResult(fmt, len(gl), "A", "denylist_hit", flagged)
    if not complete:
        return _not_possible(fmt, gl)
    if "unknown" in classes:
        return ScanResult(fmt, len(gl), "B", "unknown_callable", flagged)
    return ScanResult(fmt, len(gl), None, "clean", flagged)


def scan_file(path: Path) -> ScanResult:
    path = Path(path)
    if path.suffix == ".safetensors":
        return ScanResult("safetensors", 0, None, "not_pickle")
    return scan_bytes(path.read_bytes())
