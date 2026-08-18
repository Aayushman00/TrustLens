"""Robustness probe — clean vs discrete char-swap accuracy (Phase 11).

NLP text-classification path only. Vision/ART FGSM deferred. Emits objective
accuracies as evidence — does **not** map metrics to O/S/D or FRIES.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.datasets.loader import DatasetLoadError, load_pinned_subset
from app.datasets.registry import get_dataset_spec
from app.db.enums import FriesDimension
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.robustness_nlp import RobustnessRunner, TransformersCharSwapRunner
from app.storage.evidence_store import EvidenceStoreError

logger = logging.getLogger("trustlens.probes.robustness")

_DEFAULT_DATASET_KEY = "ag_news_robustness"
_DEFAULT_BUDGET = 0.03
_DEFAULT_SEED = 42
_DEFAULT_MAX_SAMPLES = 64
_NOTE = "Metrics are objective evidence only — not O/S/D or FRIES"


def _budget_to_max_changes(budget: float) -> int:
    return max(1, min(8, round(budget * 100)))


def _clamp_samples(n: int) -> int:
    return max(8, min(128, n))


def _extra_int(extra: dict[str, Any], key: str, default: int) -> int:
    raw = extra.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _extra_float(extra: dict[str, Any], key: str, default: float) -> float:
    raw = extra.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _is_text_classification(meta: dict[str, Any]) -> bool:
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    tag_blob = " ".join(str(t).lower() for t in tags)
    candidates = [
        meta.get("pipeline_tag"),
        meta.get("task"),
        meta.get("library_name"),
    ]
    for value in candidates:
        if not value:
            continue
        text = str(value).lower().replace("_", "-")
        if text in {"text-classification", "sentiment-analysis", "text-classif"}:
            return True
        if "text-classification" in text or "sentiment" in text:
            return True
    if "text-classification" in tag_blob or "sentiment-analysis" in tag_blob:
        return True
    return False


def _degradation_ratio(clean: float | None, robust: float | None) -> float | None:
    if clean is None or robust is None or clean == 0:
        return None
    return round(robust / clean, 4)


class RobustnessProbe:
    """NLP robustness via pinned subset + discrete char-swap attack."""

    def __init__(self, runner: RobustnessRunner | None = None) -> None:
        self._runner = runner

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.ROBUSTNESS

    def _resolve_runner(self) -> RobustnessRunner:
        return self._runner if self._runner is not None else TransformersCharSwapRunner()

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        cfg = ctx.probe_config
        extra = cfg.extra or {}
        budget = (
            float(cfg.attack_budget)
            if cfg.attack_budget is not None
            else _extra_float(extra, "attack_budget", _DEFAULT_BUDGET)
        )
        if budget <= 0:
            budget = _DEFAULT_BUDGET
        seed = _extra_int(extra, "seed", _DEFAULT_SEED)
        max_samples = _clamp_samples(
            _extra_int(extra, "max_samples", _DEFAULT_MAX_SAMPLES)
        )
        max_changes = _budget_to_max_changes(budget)
        logical_key = cfg.datasets.get("robustness") or _DEFAULT_DATASET_KEY

        flags: list[str] = []
        dataset_info: dict[str, Any] = {"logical_key": logical_key}
        base_metrics: dict[str, Any] = {
            "attack": "char_swap",
            "norm": "discrete",
            "epsilon": budget,
            "max_changes": max_changes,
            "seed": seed,
            "n_samples": max_samples,
            "dataset": dataset_info,
            "clean_accuracy": None,
            "robust_accuracy": None,
            "degradation_ratio": None,
            "attack_success_rate": None,
            "proposed_mapping": False,
            "note": _NOTE,
        }

        try:
            spec = get_dataset_spec(logical_key)
        except KeyError:
            flags.extend(["dataset_load_failed", "attack_skipped"])
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "skip_reason": f"unknown dataset logical_key={logical_key}",
                },
                flags=flags,
                confidence=0.35,
            )

        dataset_info.update(
            {
                "hf_path": spec.hf_path,
                "revision": spec.revision,
                "modality": spec.modality,
                "config_name": spec.config_name,
            }
        )

        if spec.modality != "nlp":
            flags.extend(["unsupported_modality", "attack_skipped"])
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "skip_reason": f"modality={spec.modality} (NLP path only)",
                },
                flags=flags,
                confidence=0.4,
            )

        meta = ctx.model_metadata or {}
        if not _is_text_classification(meta):
            flags.extend(["unsupported_modality", "attack_skipped"])
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "skip_reason": "model is not text-classification / sentiment",
                },
                flags=flags,
                confidence=0.4,
            )

        try:
            samples = load_pinned_subset(
                logical_key, n=max_samples, seed=seed, spec=spec
            )
        except DatasetLoadError as exc:
            logger.warning("robustness_dataset_failed err=%s", exc)
            flags.extend(["dataset_load_failed", "attack_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": str(exc)},
                flags=flags,
                confidence=0.35,
            )

        if len(samples) < 8:
            flags.append("thin_sample")

        hf_token = self._hf_token()
        try:
            result = self._resolve_runner().run(
                model_ref=ctx.model_ref,
                model_revision=ctx.model_revision,
                samples=samples,
                max_changes=max_changes,
                seed=seed,
                hf_token=hf_token,
            )
        except Exception as exc:  # noqa: BLE001 — soft-fail to keep evaluation alive
            logger.warning("robustness_model_or_attack_failed err=%s", exc)
            flags.extend(["model_load_failed", "attack_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "n_samples": len(samples), "skip_reason": str(exc)},
                flags=flags,
                confidence=0.35,
            )

        clean = round(result.clean_accuracy, 4)
        robust = round(result.robust_accuracy, 4)
        asr = round(result.attack_success_rate, 4)
        metrics = {
            **base_metrics,
            "n_samples": result.n_evaluated,
            "clean_accuracy": clean,
            "robust_accuracy": robust,
            "degradation_ratio": _degradation_ratio(clean, robust),
            "attack_success_rate": asr,
        }
        confidence = 0.85
        if "thin_sample" in flags:
            confidence = 0.7
        return self._finish(ctx, metrics=metrics, flags=flags, confidence=confidence)

    def _hf_token(self) -> str | None:
        try:
            from app.core.config import get_settings

            return get_settings().hf_token
        except Exception:  # noqa: BLE001
            return None

    def _finish(
        self,
        ctx: ProbeContext,
        *,
        metrics: dict[str, Any],
        flags: list[str],
        confidence: float,
    ) -> ProbeOutput:
        artifact = {
            "probe": "robustness",
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "config": {
                "attack": metrics.get("attack"),
                "epsilon": metrics.get("epsilon"),
                "max_changes": metrics.get("max_changes"),
                "seed": metrics.get("seed"),
                "n_samples": metrics.get("n_samples"),
                "dataset": metrics.get("dataset"),
            },
            "results": {
                "clean_accuracy": metrics.get("clean_accuracy"),
                "robust_accuracy": metrics.get("robust_accuracy"),
                "degradation_ratio": metrics.get("degradation_ratio"),
                "attack_success_rate": metrics.get("attack_success_rate"),
                "skip_reason": metrics.get("skip_reason"),
            },
            "flags": flags,
            "proposed_mapping": False,
            "per_sample": [],
        }
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
                probe_name="robustness",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise
        return ProbeOutput(
            dimension=FriesDimension.ROBUSTNESS,
            metric_values=metrics,
            confidence=confidence,
            evidence_refs=[ref],
            flags=flags,
        )
