"""Cryptographic artifact identity for Hub models and local model folders.

Trusted reference: the Hub's own LFS sha256 for the primary weight file at
the pinned revision. Local hash: sha256 of the bytes in the worker's HF cache
— the same file ``from_pretrained`` loads for inference. A match means "the
bytes evaluated are the bytes the Hub records for this revision"; it does
not mean the model is trustworthy, and it cannot catch a forger who controls
the Hub repo itself.

tl-integrity-v1.2 (round 3, L7): the identity covers the artifact *set* the
loader reads, not one file. Local folders: every weight file (single or
sharded via ``*.index.json``) plus the config/tokenizer files, compared with
an authoritative manifest when one exists (operator-supplied, then the
folder's ``artifact_manifest.json``, then the legacy ``train_manifest.json``
weight hash). Hub repos: every weight shard against its LFS sha256. See
docs/adr/0013-artifact-set-integrity.md for what this does and does not verify.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")
# Single-file and sharded checkpoints transformers' from_pretrained loads.
WEIGHT_INDEXES = {"safetensors": "model.safetensors.index.json", "pytorch_bin": "pytorch_model.bin.index.json"}
SINGLE_WEIGHTS = {"safetensors": "model.safetensors", "pytorch_bin": "pytorch_model.bin"}
WEIGHT_SUFFIXES = (".safetensors", ".bin", ".pt", ".pth", ".ckpt", ".h5", ".msgpack", ".gguf", ".onnx")
# Non-weight files that change what the loaded model computes.
LOADER_FILES = frozenset({
    "config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json",
    "special_tokens_map.json", "added_tokens.json", "vocab.txt", "vocab.json", "merges.txt",
    "spiece.model", "sentencepiece.bpe.model", "tokenizer.model",
})
ARTIFACT_MANIFEST = "artifact_manifest.json"
MANIFEST_SCHEMA = "trustlens-artifact-manifest-v1"


def _model_info(repo: str, revision: str | None, token: str | None) -> Any:
    from huggingface_hub import HfApi

    return HfApi(token=token).model_info(repo, revision=revision, files_metadata=True)


def _download(repo: str, filename: str, revision: str | None, token: str | None) -> str:
    from huggingface_hub import hf_hub_download

    return hf_hub_download(repo, filename, revision=revision, token=token)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hub_weight_hashes(repo: str, revision: str | None, token: str | None) -> dict[str, Any]:
    """Raises when the Hub has no LFS hash for a known weight file (callers
    record the error and report the hash comparison as not performed)."""
    siblings = {s.rfilename: s for s in (_model_info(repo, revision, token).siblings or [])}

    def lfs_sha(name: str) -> str | None:
        lfs = getattr(siblings.get(name), "lfs", None)
        return getattr(lfs, "sha256", None) or (lfs.get("sha256") if isinstance(lfs, dict) else None)

    index = next((i for i in WEIGHT_INDEXES.values() if i in siblings), None)
    if index is None:
        name = next((n for n in WEIGHT_FILES if lfs_sha(n)), None)
        if name is None:
            raise ValueError(f"no LFS sha256 for {WEIGHT_FILES} in {repo}@{revision}")
        names = [name]
    else:
        weight_map = json.loads(Path(_download(repo, index, revision, token)).read_text(encoding="utf-8"))
        names = sorted(set((weight_map.get("weight_map") or {}).values()))
        if not names or any(lfs_sha(n) is None for n in names):
            raise ValueError(f"{index} in {repo}@{revision} names shards without an LFS sha256")
    refs = {n: str(lfs_sha(n)) for n in names}
    local = {n: _sha256(_download(repo, n, revision, token)) for n in names}
    files = [{"name": n, "sha256": local[n], "expected_sha256": refs[n],
              "state": "match" if refs[n].lower() == local[n] else "changed"} for n in names]
    sharded = index is not None
    status = "VERIFIED" if all(f["state"] == "match" for f in files) else "MISMATCH"
    return {
        "file": index or names[0],
        "trusted_reference": {"algo": "sha256", "value": manifest_identity(refs) if sharded else refs[names[0]],
                              "source": "hf_hub_lfs"},
        "local_artifact_hash": {"algo": "sha256", "value": manifest_identity(local) if sharded else local[names[0]],
                                "source": "worker_hf_cache"},
        "artifact_verification": {
            "performed": True, "status": status, "sharded": sharded, "index_file": index, "files": files,
            "manifest": {"source": "hf_hub_lfs", "coverage": "weight_files", "n_files": len(refs),
                         "sha256": manifest_identity(refs)},
            "mismatches": [{"name": f["name"], "kind": "changed", "expected_sha256": f["expected_sha256"],
                            "observed_sha256": f["sha256"]} for f in files if f["state"] == "changed"],
            "set_sha256": manifest_identity(local), "file": index or names[0],
        },
    }


def local_weight_hashes(model_dir: str) -> dict[str, Any]:
    """Content identity for a local model folder: sha256 of the weight file
    inference loads. Trusted reference: ``train_manifest.json``'s
    ``model_safetensors_sha256`` when the training run recorded one. Raises
    when the folder holds no known weight file."""
    root = Path(model_dir)
    for name in WEIGHT_FILES:
        path = root / name
        if not path.is_file():
            continue
        out: dict[str, Any] = {
            "file": name,
            "local_artifact_hash": {"algo": "sha256", "value": _sha256(str(path)), "source": "local_folder"},
        }
        manifest = root / "train_manifest.json"
        if name == "model.safetensors" and manifest.is_file():
            ref = json.loads(manifest.read_text(encoding="utf-8")).get("model_safetensors_sha256")
            if ref:
                out["trusted_reference"] = {"algo": "sha256", "value": ref, "source": "train_manifest"}
        return out
    raise FileNotFoundError(f"no {WEIGHT_FILES} in {model_dir}")


def _is_weight(name: str) -> bool:
    return name.endswith(WEIGHT_SUFFIXES) or name in WEIGHT_INDEXES.values()


def manifest_identity(files: dict[str, str]) -> str:
    """sha256 of the canonical (sorted) filename -> sha256 map."""
    return hashlib.sha256(json.dumps(dict(sorted(files.items())), separators=(",", ":")).encode()).hexdigest()


def _expected_weights(root: Path) -> tuple[str | None, str | None, list[str]]:
    """(format, index file, files the loader expects); format None = unsupported."""
    for fmt, index in WEIGHT_INDEXES.items():
        if (root / index).is_file():
            weight_map = json.loads((root / index).read_text(encoding="utf-8")).get("weight_map") or {}
            return fmt, index, [index, *sorted(set(weight_map.values()))]
    for fmt, single in SINGLE_WEIGHTS.items():
        if (root / single).is_file():
            return fmt, None, [single]
    return None, None, []


def build_artifact_manifest(model_dir: str | Path) -> dict[str, Any]:
    """Manifest of a folder's current artifact set, to pin a known-good copy."""
    root = Path(model_dir)
    _fmt, _index, weights = _expected_weights(root)
    names = sorted({*weights, *(p.name for p in root.iterdir() if p.is_file() and p.name in LOADER_FILES)})
    return {"schema": MANIFEST_SCHEMA, "files": {n: _sha256(str(root / n)) for n in names}}


def _authoritative_manifest(root: Path, operator: dict[str, Any] | None) -> dict[str, Any] | None:
    """Operator-supplied manifest, else the folder's artifact_manifest.json, else
    the legacy train_manifest.json weight hash (covers model.safetensors only)."""
    if operator is not None:
        return {"source": "operator", "coverage": "manifest", "files": dict(operator.get("files") or {})}
    path = root / ARTIFACT_MANIFEST
    if path.is_file():
        files = json.loads(path.read_text(encoding="utf-8")).get("files") or {}
        return {"source": ARTIFACT_MANIFEST, "coverage": "manifest", "files": dict(files)}
    train = root / "train_manifest.json"
    if train.is_file():
        ref = json.loads(train.read_text(encoding="utf-8")).get("model_safetensors_sha256")
        if ref:
            return {"source": "train_manifest", "coverage": "primary_weight_file_only",
                    "files": {"model.safetensors": ref}}
    return None


def _unsupported(reason: str) -> dict[str, Any]:
    return {"performed": False, "status": "UNSUPPORTED", "format": None, "sharded": False, "index_file": None,
            "files": [], "expected_files": [], "manifest": None, "mismatches": [], "set_sha256": None,
            "file": None, "reason": reason}


def verify_local_artifacts(model_dir: str | Path, *, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Enumerate and hash a local checkpoint folder's artifact set.

    VERIFIED   every expected file present and matching the manifest
    MISMATCH   a file differs from the manifest, or a weight file the manifest
               does not list is present (the loader could pick it up)
    INCOMPLETE an expected file (manifest or weight index) is absent
    UNPINNED   hashes recorded, no authoritative manifest
    UNSUPPORTED no single or sharded model.safetensors / pytorch_model.bin
    A non-weight file the manifest does not list is ``unattested``, not a mismatch."""
    root = Path(model_dir)
    if not root.is_dir():
        return _unsupported(f"{model_dir} is not a directory")
    fmt, index, weights = _expected_weights(root)
    if fmt is None:
        return _unsupported("no single or sharded model.safetensors / pytorch_model.bin checkpoint")
    present = {p.name for p in root.iterdir() if p.is_file()}
    observed_weights = {n for n in present if _is_weight(n)}
    ref = _authoritative_manifest(root, manifest)
    if ref is not None and ref["coverage"] != "manifest" and weights != ["model.safetensors"]:
        ref = None  # the legacy weight hash covers a single model.safetensors only
    full = ref is not None and ref["coverage"] == "manifest"
    expected = ref["files"] if ref else {}
    expected_names = set(expected) if full else set(weights)
    names = sorted(expected_names | observed_weights | (present & LOADER_FILES))
    files: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    observed: dict[str, str] = {}
    for n in names:
        exp = expected.get(n)
        if n not in present:
            files.append({"name": n, "sha256": None, "expected_sha256": exp, "state": "missing"})
            mismatches.append({"name": n, "kind": "missing", "expected_sha256": exp, "observed_sha256": None})
            continue
        h = observed[n] = _sha256(str(root / n))
        if exp is not None:
            state = "match" if exp.lower() == h else "changed"
        elif full and n in observed_weights:
            state = "unexpected"
        else:
            state = "unattested" if ref else "recorded"
        files.append({"name": n, "sha256": h, "expected_sha256": exp, "state": state})
        if state in ("changed", "unexpected"):
            mismatches.append({"name": n, "kind": state, "expected_sha256": exp, "observed_sha256": h})
    kinds = {m["kind"] for m in mismatches}
    if kinds & {"changed", "unexpected"}:
        status = "MISMATCH"
    elif kinds:
        status = "INCOMPLETE"
    else:
        status = "VERIFIED" if ref else "UNPINNED"
    return {
        "performed": True, "status": status, "format": fmt, "sharded": index is not None, "index_file": index,
        "files": files, "expected_files": sorted(expected_names),
        "manifest": None if ref is None else {"source": ref["source"], "coverage": ref["coverage"],
                                              "n_files": len(expected), "sha256": manifest_identity(expected)},
        "mismatches": mismatches,
        "set_sha256": manifest_identity(observed),
        "file": index or weights[0],
    }


def local_integrity_extras(av: dict[str, Any]) -> dict[str, Any]:
    """Map a local verification onto evaluate_integrity's hash inputs.

    A single-file checkpoint without a set manifest keeps the L3 identity (the
    weight file's sha256, checked against train_manifest.json). Otherwise the
    identity is the set digest, compared with the manifest's digest over the
    same names. INCOMPLETE and UNPINNED carry no trusted reference, so neither
    becomes a risk."""
    if not av["performed"]:
        return {}
    man = av["manifest"] or {}
    if not av["sharded"] and man.get("coverage") != "manifest":
        weight = next(f for f in av["files"] if f["name"] == av["file"])
        local, ref, source = weight["sha256"], weight["expected_sha256"], man.get("source")
        local_source = "local_folder"
    else:
        compared = {f["name"]: f["sha256"] for f in av["files"] if f["state"] in ("match", "changed", "unexpected")}
        local = manifest_identity(compared) if man else av["set_sha256"]
        ref, source, local_source = man.get("sha256"), man.get("source"), "local_folder_artifact_set"
    out: dict[str, Any] = {"local_artifact_hash": {"algo": "sha256", "value": local, "source": local_source}}
    if av["status"] in ("VERIFIED", "MISMATCH") and ref:
        out["trusted_reference"] = {"algo": "sha256", "value": ref, "source": source}
    return out
