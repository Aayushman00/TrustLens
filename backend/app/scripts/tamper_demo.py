"""Integrity tamper-detection demonstration (controlled artifact modification).

clean model -> record trusted sha256 -> flip one weight byte in a copy ->
re-hash -> evaluate_integrity on both -> the copy must trigger I-INT-BYTES-DIVERGE.

Scope, stated honestly: the Integrity probe does not hash weights itself
(metadata-only, ADR 0012); it compares a trusted reference hash against a
local artifact hash supplied via ``probe_config.extra.integrity``. This
script is that supplier. A forger who also replaces the reference hash is
not caught.

Usage (from backend/)::  python -m app.scripts.tamper_demo variant1_fairness
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from app.probes.integrity_eval import evaluate_integrity
from app.scripts.run_flawed_suite_eval import SUITE_DIR

_WEIGHTS = "model.safetensors"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_tampered_copy(src: Path, dst: Path) -> None:
    """Copy ``src`` and flip the lowest bit of its last byte (tensor data, past
    the safetensors header) — same size and shape, different bytes."""
    data = bytearray(src.read_bytes())
    data[-1] ^= 0x01
    dst.write_bytes(bytes(data))


def integrity_extra_for(reference_path: Path, local_path: Path) -> dict[str, Any]:
    return {
        "trusted_reference": {"algo": "sha256", "value": sha256_file(reference_path)},
        "local_artifact_hash": {"algo": "sha256", "value": sha256_file(local_path)},
    }


def _evidence(name: str, extra: dict[str, Any]) -> dict[str, Any]:
    res = evaluate_integrity(
        model_ref=f"{SUITE_DIR.name}/{name}",
        model_revision=None,
        model_metadata={"files": [_WEIGHTS]},
        integrity_extra=extra,
        live_files=None,
        live_files_error="local demo: no Hub listing",
    )
    return {"integrity_extra": extra, "risks_triggered": res.risks_triggered, "identity": res.identity}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant")
    args = ap.parse_args()
    src_dir = SUITE_DIR / "models" / args.variant
    dst_dir = SUITE_DIR / "models" / f"{args.variant}_tampered"
    dst_dir.mkdir(exist_ok=True)
    for f in src_dir.iterdir():
        if f.is_file() and f.name != _WEIGHTS:
            shutil.copy2(f, dst_dir / f.name)
    make_tampered_copy(src_dir / _WEIGHTS, dst_dir / _WEIGHTS)
    ref = src_dir / _WEIGHTS
    out = {
        "variant": args.variant,
        "trusted_sha256": sha256_file(ref),
        "tampered_sha256": sha256_file(dst_dir / _WEIGHTS),
        "untouched": _evidence(args.variant, integrity_extra_for(ref, ref)),
        "tampered": _evidence(f"{args.variant}_tampered", integrity_extra_for(ref, dst_dir / _WEIGHTS)),
    }
    path = SUITE_DIR / "tamper_demo.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(path, "untouched:", out["untouched"]["risks_triggered"], "tampered:", out["tampered"]["risks_triggered"])


if __name__ == "__main__":
    main()
