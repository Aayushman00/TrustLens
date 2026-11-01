"""Spike S7: non-executing pickle-opcode scan for Integrity Tier A.

Never unpickles. Walks opcodes with stdlib `pickletools.genops`, resolves GLOBAL / STACK_GLOBAL / INST targets
(STACK_GLOBAL by tracking pushed strings and the memo), and classifies each imported callable:
  allow     on the torch-checkpoint allowlist below
  dangerous on the denylist (module or exact name)  -> Tier A candidate
  unknown   anything else                           -> Tier B (unverifiable), never a hard fail
Fixtures:
  benign    torch.save(state_dict) of a tiny model, in memory
  flagged   hand-built opcode bytes importing os.system / builtins.eval (protocol 2 GLOBAL and protocol 4
            STACK_GLOBAL); the bytes are only parsed, never loaded
  real      every *.bin / *.pt / *.pth / *.ckpt in the local Hugging Face cache
Run:  python docs/v2/spikes/s7_pickle_scan.py      Out: results/s7_pickle_scan.json
"""
from __future__ import annotations

import io
import json
import pickletools
import time
import zipfile
from pathlib import Path

ALLOW = {
    ("collections", "OrderedDict"), ("torch._utils", "_rebuild_tensor_v2"), ("torch._utils", "_rebuild_tensor"),
    ("torch._utils", "_rebuild_parameter"), ("torch._utils", "_rebuild_parameter_with_state"),
    ("torch._tensor", "_rebuild_from_type_v2"), ("torch", "Size"), ("torch", "device"), ("torch", "dtype"),
    ("torch.serialization", "_get_layout"), ("builtins", "set"), ("builtins", "dict"), ("builtins", "list"),
    ("builtins", "tuple"), ("builtins", "slice"), ("_codecs", "encode"), ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "ndarray"), ("numpy", "dtype"), ("torch._utils", "_rebuild_qtensor"),
} | {("torch", f"{t}Storage") for t in ("Float", "Half", "BFloat16", "Double", "Long", "Int", "Short", "Char",
                                          "Byte", "Bool", "ComplexFloat", "ComplexDouble", "Untyped")} | \
    {("torch", d) for d in ("float32", "float16", "bfloat16", "int64", "int32", "uint8", "bool")}
DENY_MODULES = {"os", "posix", "nt", "subprocess", "sys", "socket", "shutil", "runpy", "webbrowser", "pty",
                "importlib", "ctypes", "multiprocessing", "asyncio", "pickle", "marshal", "code", "httplib",
                "requests", "urllib", "http", "ftplib", "telnetlib", "platform", "commands", "pip", "torch.hub"}
DENY_NAMES = {("builtins", n) for n in ("eval", "exec", "compile", "open", "getattr", "setattr", "__import__",
                                        "globals", "locals", "breakpoint", "input")} | \
             {("__builtin__", n) for n in ("eval", "exec", "getattr", "__import__", "open")}
STR_OPS = {"SHORT_BINUNICODE", "BINUNICODE", "UNICODE", "BINUNICODE8", "SHORT_BINSTRING", "BINSTRING", "STRING"}


def classify(mod: str, name: str) -> str:
    if (mod, name) in ALLOW:
        return "allow"
    if (mod, name) in DENY_NAMES or mod.split(".")[0] in DENY_MODULES or mod in DENY_MODULES:
        return "dangerous"
    return "unknown"


def globals_in(data: bytes) -> list[tuple[str, str]]:
    """All GLOBAL/STACK_GLOBAL/INST targets across every pickle concatenated in `data`."""
    found, f = [], io.BytesIO(data)
    while f.tell() < len(data):
        start = f.tell()
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
                    break
        except Exception:  # legacy torch files append raw tensor bytes after the last pickle
            f.seek(len(data)) if f.tell() == start else None
            break
    return found


def scan_bytes(data: bytes) -> dict:
    if data[:4] == b"PK\x03\x04":  # torch >= 1.6 zip checkpoint: scan every .pkl member
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            pkls = [z.read(i) for i in z.namelist() if i.endswith(".pkl")]
        gl = [g for p in pkls for g in globals_in(p)]
        fmt = "torch_zip"
    else:
        gl, fmt = globals_in(data), "raw_or_legacy_pickle"
    counts = {"allow": 0, "dangerous": 0, "unknown": 0}
    flagged = []
    for mod, name in gl:
        c = classify(mod, name)
        counts[c] += 1
        if c != "allow":
            flagged.append({"global": f"{mod}.{name}", "class": c})
    tier = "A_dangerous" if counts["dangerous"] else ("B_unknown_callable" if counts["unknown"] else "clean")
    return {"format": fmt, "globals_total": len(gl), "counts": counts, "tier": tier,
            "flagged": sorted({json.dumps(x, sort_keys=True) for x in flagged})}


def fixtures() -> dict[str, bytes]:
    import torch
    buf = io.BytesIO()
    torch.save(torch.nn.Linear(4, 2).state_dict(), buf)
    return {
        "benign_torch_save": buf.getvalue(),
        # protocol 2: GLOBAL os.system, arg 'echo', TUPLE1, REDUCE, STOP  (inert: never loaded)
        "flagged_p2_os_system": b"\x80\x02cos\nsystem\nX\x04\x00\x00\x00echo\x85R.",
        # protocol 4: SHORT_BINUNICODE builtins, MEMOIZE, SHORT_BINUNICODE eval, MEMOIZE, STACK_GLOBAL, ...
        "flagged_p4_builtins_eval": b"\x80\x04\x8c\x08builtins\x94\x8c\x04eval\x94\x93\x8c\x011\x94\x85R.",
        # protocol 4 benign-looking but unknown callable (Tier B, not A)
        "unknown_p4_custom_class": b"\x80\x04\x8c\x0bmy_pkg.util\x94\x8c\x06Helper\x94\x93)R.",
    }


def main():
    out = {"fixtures": {}, "real_hub_files": []}
    for name, data in fixtures().items():
        out["fixtures"][name] = scan_bytes(data)
        print(name, out["fixtures"][name]["tier"], out["fixtures"][name]["flagged"])
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    files = sorted({p.resolve() for ext in ("*.bin", "*.pt", "*.pth", "*.ckpt") for p in cache.glob(f"**/snapshots/**/{ext}")})
    for p in files:
        t0 = time.perf_counter()
        data = p.read_bytes()
        r = scan_bytes(data)
        r.update({"file": str(p).split("hub")[-1][:140], "size_mb": round(len(data) / 2**20, 1),
                  "scan_s": round(time.perf_counter() - t0, 2)})
        out["real_hub_files"].append(r)
        print(r["tier"], r["size_mb"], r["scan_s"], r["file"][-80:], r["flagged"][:3])
    real = out["real_hub_files"]
    out["summary"] = {"real_files": len(real),
                      "tier_counts": {t: sum(r["tier"] == t for r in real) for t in ("clean", "B_unknown_callable", "A_dangerous")},
                      "total_mb": round(sum(r["size_mb"] for r in real), 1),
                      "total_scan_s": round(sum(r["scan_s"] for r in real), 1)}
    print(out["summary"])
    o = Path(__file__).parent / "results" / "s7_pickle_scan.json"
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
