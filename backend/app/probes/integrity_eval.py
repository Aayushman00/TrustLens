"""Integrity evaluation logic (tl-integrity-v1.0) — pure functions, stdlib only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.db.enums import ProbeEvaluationStatus
from app.probes.integrity_stats import (
    CLAIM_BYTES_DIVERGE,
    CLAIM_HASH_UNVERIFIED,
    G_HASH_LOCAL_MISSING,
    G_HASH_REF_MISSING,
    G_IDENTITY_EMPTY,
    GATE_HASH_UNVERIFIED,
    LIMITATIONS,
    RISK_BYTES_DIVERGE,
    RISK_LICENSE_UNDISCLOSED,
    RISK_MANIFEST_MISSING,
    RISK_REV_UNPINNED,
)
from app.storage.evidence_store import format_sha256, hashes_equal

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
_WEIGHT_NAME_RE = re.compile(
    r"(?:\.safetensors$|\.bin$|pytorch_model|model\.safetensors|tf_model)",
    re.IGNORECASE,
)
_LICENSE_FILE_RE = re.compile(r"(?:^|/)license(?:\.[a-z0-9]+)?$", re.IGNORECASE)

_OPEN_LICENSE_HINTS = (
    "apache-2.0",
    "apache 2",
    "mit license",
    "bsd license",
    "open source",
    "permissive license",
    "licensed under mit",
    "licensed under apache",
)

_REPRO_GROUPS: dict[str, tuple[str, ...]] = {
    "training_data": ("training data", "trained on", "pretrain", "fine-tun", "dataset"),
    "seed": ("random seed", "seed=", "seed:", "torch.manual_seed", "numpy.random.seed"),
    "evaluation": ("evaluation", "benchmark", "metrics", "accuracy", "f1"),
    "hyperparameters": ("hyperparameter", "learning rate", "batch size", "epochs"),
}


@dataclass
class IntegrityEvalResult:
    status: ProbeEvaluationStatus
    status_reason: str | None
    aspect_scoring: str
    scored_risk_id: None
    risks_triggered: list[str]
    flags: list[str]
    checks: dict[str, dict[str, Any]]
    identity: dict[str, Any]
    disclosure: dict[str, Any]
    claims: dict[str, dict[str, str]]
    claim_boundary: dict[str, str]
    reliability: dict[str, Any]
    uncertainty: dict[str, Any]
    limitations: list[str]
    confidence: float = 0.5


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value).strip() or None


def sha_like(revision: str | None) -> bool:
    if not revision:
        return False
    return bool(_SHA_RE.fullmatch(revision))


def files_fingerprint(files: list[str]) -> str:
    joined = "\n".join(sorted(files)).encode("utf-8")
    return format_sha256(joined)


def _repro_signal_groups(card_text: str, card_data: dict[str, Any]) -> list[str]:
    blob = card_text.lower()
    if card_data:
        blob += "\n" + json.dumps(card_data, default=str).lower()
    found: list[str] = []
    for group, keywords in _REPRO_GROUPS.items():
        if any(kw in blob for kw in keywords):
            found.append(group)
    return found


def _parse_hash_entry(raw: Any) -> dict[str, str] | None:
    if isinstance(raw, str) and raw.strip():
        return {"algo": "sha256", "value": raw.strip()}
    if isinstance(raw, dict):
        value = _as_str(raw.get("value"))
        if not value:
            return None
        algo = _as_str(raw.get("algo")) or "sha256"
        return {"algo": algo, "value": value}
    return None


def _parse_trusted_reference(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    value = _as_str(raw.get("value"))
    if not value:
        return None
    return {
        "algo": _as_str(raw.get("algo")) or "sha256",
        "value": value,
        "source": _as_str(raw.get("source")) or "operator_supplied",
        "retrieved_at": _as_str(raw.get("retrieved_at")),
        "provenance": _as_str(raw.get("provenance")),
    }


def evaluate_integrity(
    *,
    model_ref: str,
    model_revision: str | None,
    model_metadata: dict[str, Any],
    integrity_extra: dict[str, Any] | None = None,
) -> IntegrityEvalResult:
    """Evaluate Integrity from an imported Hub metadata snapshot."""
    meta = model_metadata or {}
    extra = integrity_extra or {}

    files_raw = meta.get("files")
    files = (
        [str(x) for x in files_raw if x is not None]
        if isinstance(files_raw, list)
        else []
    )
    revision = _as_str(model_revision)
    if not revision:
        for candidate in (meta.get("revision"), meta.get("checksum")):
            revision = _as_str(candidate)
            if revision:
                break

    card_text = _as_str(meta.get("card_text")) or ""
    card_data = meta.get("card_data") if isinstance(meta.get("card_data"), dict) else {}
    structured_license = None
    for candidate in (meta.get("license"), card_data.get("license")):
        structured_license = _as_str(candidate)
        if structured_license:
            break

    flags: list[str] = []
    risks: list[str] = []
    failed_gates: list[str] = []
    checks: dict[str, dict[str, Any]] = {}
    claim_boundary: dict[str, str] = {}

    has_revision = bool(revision)
    has_files = bool(files)
    has_card = bool(card_text)

    if not has_revision and not has_files and not has_card:
        return IntegrityEvalResult(
            status=ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE,
            status_reason=(
                "no revision, Hub file manifest, or model card text — "
                "cannot record artifact identity"
            ),
            aspect_scoring="not_scored",
            scored_risk_id=None,
            risks_triggered=[],
            flags=["identity_empty"],
            checks={},
            identity={
                "revision": None,
                "sha_like": False,
                "hub_files": [],
                "files_listing_fingerprint": files_fingerprint([]),
                "weight_hash": None,
                "trusted_reference": None,
                "hash_comparison": "not_performed",
            },
            disclosure={
                "license_structured": None,
                "card_present": False,
                "card_chars": 0,
                "repro_groups_found": [],
            },
            claims={
                "identity_recording": {
                    "status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
                    "reason": G_IDENTITY_EMPTY,
                },
                "license_disclosure": {
                    "status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
                    "reason": "identity snapshot empty",
                },
                "cryptographic_identity": {
                    "status": ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value,
                    "reason": CLAIM_HASH_UNVERIFIED,
                },
            },
            claim_boundary={"cryptographic_identity": CLAIM_HASH_UNVERIFIED},
            reliability={"gates_passed": False, "failed_gates": [G_IDENTITY_EMPTY]},
            uncertainty={},
            limitations=list(LIMITATIONS),
        )

    # --- revision_pinned ---
    if revision and sha_like(revision):
        checks["revision_pinned"] = {
            "pass": True,
            "detail": "sha-like revision",
        }
    elif revision:
        checks["revision_pinned"] = {
            "pass": False,
            "detail": f"non-sha-like revision={revision[:64]}",
        }
        risks.append(RISK_REV_UNPINNED)
        flags.append("unpinned_revision")
    else:
        checks["revision_pinned"] = {
            "pass": False,
            "detail": "missing revision",
        }
        flags.append("missing_revision")

    # --- files_listed ---
    if files:
        detail_parts = [f"{len(files)} files"]
        if any(name.endswith("config.json") or name == "config.json" for name in files):
            detail_parts.append("config.json present")
        if any(_WEIGHT_NAME_RE.search(name) for name in files):
            detail_parts.append("weight-like filename present")
        checks["files_listed"] = {"pass": True, "detail": "; ".join(detail_parts)}
    else:
        checks["files_listed"] = {
            "pass": False,
            "detail": "empty or missing files list",
        }
        risks.append(RISK_MANIFEST_MISSING)
        flags.append("empty_file_list")

    # --- license_declared ---
    license_file = any(
        _LICENSE_FILE_RE.search(name.replace("\\", "/")) for name in files
    )
    card_open = bool(card_text) and any(
        hint in card_text.lower() for hint in _OPEN_LICENSE_HINTS
    )
    if structured_license:
        checks["license_declared"] = {
            "pass": True,
            "detail": structured_license,
        }
        if card_open and "proprietary" in structured_license.lower():
            flags.append("license_card_mismatch")
    elif card_open:
        checks["license_declared"] = {
            "pass": False,
            "detail": "open-license language in card text only (anti-gaming)",
        }
        risks.append(RISK_LICENSE_UNDISCLOSED)
        flags.extend(["missing_license", "card_only_license"])
    elif license_file:
        checks["license_declared"] = {
            "pass": False,
            "detail": "LICENSE filename present but no structured license field",
        }
        risks.append(RISK_LICENSE_UNDISCLOSED)
        flags.extend(["missing_license", "card_only_license"])
    else:
        checks["license_declared"] = {
            "pass": False,
            "detail": "no structured license",
        }
        risks.append(RISK_LICENSE_UNDISCLOSED)
        flags.append("missing_license")

    # --- card_present (evidence only) ---
    if card_text:
        checks["card_present"] = {"pass": True, "detail": f"{len(card_text)} chars"}
    else:
        checks["card_present"] = {"pass": False, "detail": "empty card_text"}
        flags.append("empty_card")

    # --- reproducibility_claims (evidence only) ---
    repro_groups = _repro_signal_groups(card_text, card_data)
    if len(repro_groups) >= 2:
        checks["reproducibility_claims"] = {
            "pass": True,
            "detail": f"signal groups: {', '.join(repro_groups)}",
        }
    else:
        checks["reproducibility_claims"] = {
            "pass": False,
            "detail": (
                f"thin reproducibility (groups={repro_groups or 'none'}); "
                "keyword hits are disclosure evidence only"
            ),
        }
        flags.append("thin_reproducibility")

    fingerprint = files_fingerprint(files)
    listing_detail = (
        "recorded Hub file listing fingerprint (not weight bytes)"
        if files
        else "empty file list — no listing fingerprint identity"
    )
    checks["files_listing_recorded"] = {
        "pass": bool(files),
        "detail": listing_detail,
        "model_revision": revision,
        "files_listing_fingerprint": fingerprint,
    }

    trusted_reference = _parse_trusted_reference(extra.get("trusted_reference"))
    weight_hash = _parse_hash_entry(extra.get("local_artifact_hash"))

    hash_comparison = "not_performed"
    crypto_status = ProbeEvaluationStatus.INSUFFICIENT_EVIDENCE.value
    crypto_reason = CLAIM_HASH_UNVERIFIED
    claim_boundary["cryptographic_identity"] = CLAIM_HASH_UNVERIFIED

    if trusted_reference is None:
        failed_gates.append(G_HASH_REF_MISSING)
    if weight_hash is None:
        failed_gates.append(G_HASH_LOCAL_MISSING)

    if trusted_reference and weight_hash:
        if hashes_equal(trusted_reference["value"], weight_hash["value"]):
            hash_comparison = "match"
            crypto_status = ProbeEvaluationStatus.EVALUATED.value
            crypto_reason = "local artifact hash matches trusted reference"
            claim_boundary["cryptographic_identity"] = crypto_reason
        else:
            hash_comparison = "diverge"
            crypto_status = ProbeEvaluationStatus.EVALUATED.value
            crypto_reason = CLAIM_BYTES_DIVERGE
            risks.append(RISK_BYTES_DIVERGE)
            claim_boundary["cryptographic_identity"] = CLAIM_BYTES_DIVERGE
            claim_boundary["bytes_diverge"] = CLAIM_BYTES_DIVERGE
    else:
        failed_gates.append(GATE_HASH_UNVERIFIED)

    identity_recording_status = ProbeEvaluationStatus.EVALUATED.value
    identity_reason = "identity metadata recorded from import snapshot"
    if not files:
        identity_reason = (
            "Hub file manifest missing — listing-dependent identity claims insufficient"
        )

    license_status = ProbeEvaluationStatus.EVALUATED.value
    license_reason = (
        "structured license present"
        if structured_license
        else "structured license check ran; absence recorded as named risk"
    )

    if risks:
        aspect_scoring = "risk_detected"
    else:
        aspect_scoring = "no_material_risk"

    return IntegrityEvalResult(
        status=ProbeEvaluationStatus.EVALUATED,
        status_reason=None,
        aspect_scoring=aspect_scoring,
        scored_risk_id=None,
        risks_triggered=risks,
        flags=flags,
        checks=checks,
        identity={
            "revision": revision,
            "sha_like": sha_like(revision),
            "hub_files": files,
            "files_listing_fingerprint": fingerprint,
            "weight_hash": weight_hash,
            "trusted_reference": trusted_reference,
            "hash_comparison": hash_comparison,
        },
        disclosure={
            "license_structured": structured_license,
            "card_present": bool(card_text),
            "card_chars": len(card_text),
            "repro_groups_found": repro_groups,
        },
        claims={
            "identity_recording": {
                "status": identity_recording_status,
                "reason": identity_reason,
            },
            "license_disclosure": {
                "status": license_status,
                "reason": license_reason,
            },
            "cryptographic_identity": {
                "status": crypto_status,
                "reason": crypto_reason,
            },
        },
        claim_boundary=claim_boundary,
        reliability={
            "gates_passed": not failed_gates,
            "failed_gates": failed_gates,
        },
        uncertainty={},
        limitations=list(LIMITATIONS),
    )
