"""Cryptographic artifact identity for Hub models.

Trusted reference: the Hub's own LFS sha256 for the primary weight file at
the pinned revision. Local hash: sha256 of the bytes in the worker's HF cache
— the same file ``from_pretrained`` loads for inference. A match means "the
bytes evaluated are the bytes the Hub records for this revision"; it does
not mean the model is trustworthy, and it cannot catch a forger who controls
the Hub repo itself.
"""
from __future__ import annotations

import hashlib
from typing import Any

WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")


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
    for name in WEIGHT_FILES:
        lfs = getattr(siblings.get(name), "lfs", None)
        ref = getattr(lfs, "sha256", None) or (lfs.get("sha256") if isinstance(lfs, dict) else None)
        if ref:
            return {
                "file": name,
                "trusted_reference": {"algo": "sha256", "value": ref, "source": "hf_hub_lfs"},
                "local_artifact_hash": {
                    "algo": "sha256",
                    "value": _sha256(_download(repo, name, revision, token)),
                    "source": "worker_hf_cache",
                },
            }
    raise ValueError(f"no LFS sha256 for {WEIGHT_FILES} in {repo}@{revision}")
