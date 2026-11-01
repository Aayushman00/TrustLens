"""Non-executing pickle scan for Integrity Tier A (K14). Walks opcodes with pickletools.genops; never unpickles.

Tier A = denylist hit only. Unknown callable or unparseable bytes = Tier B. Otherwise None.
"""
from __future__ import annotations

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
    if (mod, name) in DENY_NAMES or mod.split(".")[0] in DENY_MODULES or mod in DENY_MODULES:
        return "dangerous"
    return "unknown"


def globals_in(data: bytes) -> tuple[list[tuple[str, str]], bool]:
    """All GLOBAL/STACK_GLOBAL/INST targets across every pickle concatenated in `data`, and whether the scan
    completed. A stream that errors before any STOP is partial (False); bytes after a completed STOP are
    tolerated (legacy torch appends raw tensor bytes after the last pickle)."""
    found: list[tuple[str, str]] = []
    f, stops = io.BytesIO(data), 0
    while f.tell() < len(data):
        recent: list[str] = []
        memo: dict[int, str] = {}
        try:
            for op, arg, _ in pickletools.genops(f):
                n = op.name
                if n in STR_OPS:
                    recent.append(arg if isinstance(arg, str) else str(arg))
                elif n == "MEMOIZE" and recent:
                    memo[len(memo)] = recent[-1]
                elif n in ("BINPUT", "LONG_BINPUT", "PUT") and recent:
                    memo[int(arg)] = recent[-1]
                elif n in ("BINGET", "LONG_BINGET", "GET") and int(arg) in memo:
                    recent.append(memo[int(arg)])
                elif n in ("GLOBAL", "INST"):
                    mod, _, name = str(arg).partition(" ")
                    found.append((mod, name))
                elif n == "STACK_GLOBAL":
                    found.append((recent[-2], recent[-1]) if len(recent) >= 2 else ("?", "?"))
                elif n == "STOP":
                    stops += 1
                    break
            else:  # opcodes ended without STOP
                return found, stops > 0
        except Exception:
            return found, stops > 0
    return found, stops > 0


def _not_possible(fmt: str, gl: list[tuple[str, str]] = ()) -> ScanResult:
    return ScanResult(fmt, len(gl), "B", "scan_not_possible", sorted({f"{m}.{n}" for m, n in gl}))


def scan_bytes(data: bytes) -> ScanResult:
    if data[:4] == b"PK\x03\x04":  # torch >= 1.6 zip checkpoint: scan every .pkl member
        fmt = "torch_zip"
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                pkls = [z.read(i) for i in z.namelist() if i.endswith(".pkl")]
        except Exception:
            return _not_possible(fmt)
        if not pkls:
            return _not_possible(fmt)
        gl, complete = [], True
        for p in pkls:
            g, c = globals_in(p)
            gl += g
            complete &= c
    else:
        fmt = "raw_or_legacy_pickle"
        gl, complete = globals_in(data)
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
