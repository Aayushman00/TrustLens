"""Integrity probe — provenance / license / reproducibility from Hub metadata (Phase 10).

Metadata-only: never downloads model weights. Emits proposed ``integrity_score_0_10``
as probe evidence for a future O/S/D Agent — does **not** write final FRIES or O/S/D.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.db.enums import FriesDimension
from app.probes.base import ProbeContext, ProbeOutput
from app.storage.evidence_store import EvidenceStoreError, format_sha256

_CHECK_IDS: tuple[str, ...] = (
    "revision_pinned",
    "files_listed",
    "license_declared",
    "card_present",
    "reproducibility_claims",
    "checksum_recorded",
)
_CHECK_WEIGHT = 10.0 / len(_CHECK_IDS)

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
_WEIGHT_NAME_RE = re.compile(
    r"(?:\.safetensors$|\.bin$|pytorch_model|model\.safetensors|tf_model)",
    re.IGNORECASE,
)
_LICENSE_FILE_RE = re.compile(r"(?:^|/)license(?:\.[a-z0-9]+)?$", re.IGNORECASE)

# Card-only open-license language (anti-gaming when structured license missing).
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


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value).strip() or None


def _card_data_dict(meta: dict[str, Any]) -> dict[str, Any]:
    raw = meta.get("card_data")
    return raw if isinstance(raw, dict) else {}


def _files_list(meta: dict[str, Any]) -> list[str]:
    raw = meta.get("files")
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if x is not None]


def _resolve_revision(ctx: ProbeContext) -> str | None:
    for candidate in (
        ctx.model_revision,
        ctx.model_checksum,
        ctx.model_metadata.get("revision"),
        ctx.model_metadata.get("checksum"),
    ):
        text = _as_str(candidate)
        if text:
            return text
    return None


def _structured_license(meta: dict[str, Any]) -> str | None:
    for candidate in (meta.get("license"), _card_data_dict(meta).get("license")):
        text = _as_str(candidate)
        if text:
            return text
    return None


def _has_license_filename(files: list[str]) -> bool:
    return any(_LICENSE_FILE_RE.search(name.replace("\\", "/")) for name in files)


def _card_suggests_open_license(card_text: str) -> bool:
    lower = card_text.lower()
    return any(hint in lower for hint in _OPEN_LICENSE_HINTS)


def _repro_signal_groups(card_text: str, card_data: dict[str, Any]) -> list[str]:
    blob = card_text.lower()
    if card_data:
        blob += "\n" + json.dumps(card_data, default=str).lower()
    found: list[str] = []
    for group, keywords in _REPRO_GROUPS.items():
        if any(kw in blob for kw in keywords):
            found.append(group)
    return found


def _files_fingerprint(files: list[str]) -> str:
    joined = "\n".join(sorted(files)).encode("utf-8")
    return format_sha256(joined)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class IntegrityProbe:
    """Audit Hub metadata for provenance, license, and reproducibility claims."""

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.INTEGRITY

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        meta = ctx.model_metadata or {}
        files = _files_list(meta)
        revision = _resolve_revision(ctx)
        checksum = _as_str(ctx.model_checksum) or revision
        card_text = _as_str(meta.get("card_text")) or ""
        card_data = _card_data_dict(meta)
        structured_license = _structured_license(meta)
        flags: list[str] = []

        checks: dict[str, dict[str, Any]] = {}

        # --- revision_pinned ---
        if revision:
            sha_like = bool(_SHA_RE.fullmatch(revision))
            checks["revision_pinned"] = {
                "pass": True,
                "detail": "sha-like revision" if sha_like else f"revision={revision[:64]}",
            }
        else:
            checks["revision_pinned"] = {
                "pass": False,
                "detail": "missing revision/checksum",
            }
            flags.append("missing_revision")

        # --- files_listed ---
        if files:
            has_config = any(
                name.endswith("config.json") or name == "config.json" for name in files
            )
            has_weights = any(_WEIGHT_NAME_RE.search(name) for name in files)
            detail_parts = [f"{len(files)} files"]
            if has_config:
                detail_parts.append("config.json present")
            if has_weights:
                detail_parts.append("weight-like filename present")
            checks["files_listed"] = {"pass": True, "detail": "; ".join(detail_parts)}
        else:
            checks["files_listed"] = {
                "pass": False,
                "detail": "empty or missing files list",
            }
            flags.append("empty_file_list")

        # --- license_declared ---
        license_file = _has_license_filename(files)
        card_open = bool(card_text) and _card_suggests_open_license(card_text)
        if structured_license:
            checks["license_declared"] = {
                "pass": True,
                "detail": structured_license,
            }
            if card_open and "proprietary" in structured_license.lower():
                flags.append("license_card_mismatch")
        elif card_open and not structured_license:
            checks["license_declared"] = {
                "pass": False,
                "detail": "open-license language in card text only (anti-gaming)",
            }
            flags.extend(["missing_license", "card_only_license"])
        elif license_file and not structured_license:
            checks["license_declared"] = {
                "pass": False,
                "detail": "LICENSE filename present but no structured license field",
            }
            flags.extend(["missing_license", "card_only_license"])
        else:
            checks["license_declared"] = {
                "pass": False,
                "detail": "no structured license",
            }
            flags.append("missing_license")

        # --- card_present ---
        if card_text:
            checks["card_present"] = {"pass": True, "detail": f"{len(card_text)} chars"}
        else:
            checks["card_present"] = {"pass": False, "detail": "empty card_text"}

        # --- reproducibility_claims ---
        groups = _repro_signal_groups(card_text, card_data)
        if len(groups) >= 2:
            checks["reproducibility_claims"] = {
                "pass": True,
                "detail": f"signal groups: {', '.join(groups)}",
            }
        else:
            checks["reproducibility_claims"] = {
                "pass": False,
                "detail": (
                    f"thin reproducibility (groups={groups or 'none'}); "
                    "keyword hits are not ground truth"
                ),
            }
            flags.append("thin_reproducibility")

        # --- checksum_recorded (identity fingerprint; never downloads weights) ---
        fingerprint = _files_fingerprint(files)
        if not files:
            checks["checksum_recorded"] = {
                "pass": False,
                "revision": revision,
                "checksum": checksum,
                "files_fingerprint": fingerprint,
                "detail": "empty file list — cannot record files fingerprint identity",
            }
        else:
            checks["checksum_recorded"] = {
                "pass": True,
                "revision": revision,
                "checksum": checksum,
                "files_fingerprint": fingerprint,
                "detail": (
                    "recorded revision/checksum + files fingerprint (no weight download)"
                ),
            }

        pass_count = sum(1 for c in checks.values() if c.get("pass"))
        fail_count = len(checks) - pass_count
        score = round(_clamp(10.0 - fail_count * _CHECK_WEIGHT, 0.0, 10.0), 1)

        confidence = 0.5
        if checks["revision_pinned"]["pass"]:
            confidence += 0.15
        if checks["files_listed"]["pass"]:
            confidence += 0.15
        if structured_license:
            confidence += 0.15
        if "thin_reproducibility" in flags:
            confidence -= 0.1
        if "card_only_license" in flags:
            confidence -= 0.1
        confidence = round(_clamp(confidence, 0.0, 1.0), 3)

        metric_values: dict[str, Any] = {
            "checks": checks,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "integrity_score_0_10": score,
            "proposed_mapping": True,
            "scoring": "equal_weight_base_10",
        }

        artifact = {
            "probe": "integrity",
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "checks": checks,
            "integrity_score_0_10": score,
            "flags": flags,
            "proposed_mapping": True,
        }
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
                probe_name="integrity",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise

        return ProbeOutput(
            dimension=FriesDimension.INTEGRITY,
            metric_values=metric_values,
            confidence=confidence,
            evidence_refs=[ref],
            flags=flags,
        )
