"""Robustness probe — clean vs discrete char-swap accuracy (tl-methodology-v1.0).

NLP text-classification path only. Vision/ART FGSM deferred. Emits Layer A
evidence with gates and R-ROB-PERT detection — does **not** map metrics to O/S/D.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.datasets.loader import DatasetLoadError, load_pinned_subset
from app.datasets.registry import DatasetSpec, get_dataset_spec
from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.inference.base import DecisionMode, InferenceConfig
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.robustness_compat import resolve_robustness_compat
from app.probes.robustness_eval import evaluate_classification_robustness
from app.probes.robustness_nlp import (
    RobustnessRunner,
    RobustnessRunResult,
    TransformersCharSwapRunner,
    task_type_from_spec,
)
from app.probes.robustness_stats import MIN_REQUESTED, SCORED_RISK_ID
from app.storage.evidence_store import EvidenceStoreError

logger = logging.getLogger("trustlens.probes.robustness")

_DEFAULT_BUDGET = 0.03
_DEFAULT_SEED = 42
_DEFAULT_MAX_SAMPLES = 200
_NOTE = "Layer A evidence only — R-ROB-PERT detection does not assign O/S/D"


def _budget_to_max_changes(budget: float) -> int:
    return max(1, min(8, round(budget * 100)))


def _clamp_samples(n: int) -> int:
    return max(MIN_REQUESTED, min(512, n))


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


def _extra_bool(extra: dict[str, Any], key: str, default: bool = False) -> bool:
    raw = extra.get(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes"}
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


def _resolve_robustness_dataset(
    ctx: ProbeContext,
) -> tuple[str | None, str | None, str | None]:
    """Return (logical_key, evaluation_domain, resolution_source) or (None, None, None)."""
    cfg = ctx.probe_config
    explicit = cfg.datasets.get("robustness")
    if explicit:
        try:
            spec = get_dataset_spec(explicit)
        except KeyError:
            return explicit, None, "probe_config"
        return explicit, spec.evaluation_domain, "probe_config"

    compat = resolve_robustness_compat(ctx.model_ref, revision=ctx.model_revision)
    if compat is not None:
        return (
            compat.robustness_dataset_key,
            compat.evaluation_domain,
            "versioned_compat",
        )
    return None, None, None


def _check_domain_compat(
    *,
    dataset_domain: str | None,
    compat_domain: str | None,
    allow_domain_mismatch: bool,
) -> tuple[bool, bool]:
    """Return (hard_domain_mismatch, mapping_blocked_pre)."""
    if dataset_domain is None:
        return False, False
    if compat_domain is None:
        return False, False
    if dataset_domain == compat_domain:
        return False, False
    if allow_domain_mismatch:
        return False, True
    return True, False


def _resolve_inference_config(spec: DatasetSpec) -> InferenceConfig:
    return InferenceConfig(
        task_type=task_type_from_spec(spec.task_type),
        decision=DecisionMode.ARGMAX,
        device="cpu",
    )


def _base_metrics(
    *,
    logical_key: str | None,
    budget: float,
    max_changes: int,
    seed: int,
    max_samples: int,
    dataset_info: dict[str, Any],
) -> dict[str, Any]:
    return {
        "attack": "char_swap",
        "norm": "discrete",
        "epsilon": budget,
        "max_changes": max_changes,
        "seed": seed,
        "n_samples": max_samples,
        "n_requested": max_samples,
        "dataset": dataset_info,
        "clean_accuracy": None,
        "robust_accuracy": None,
        "degradation_ratio": None,
        "relative_degradation": None,
        "accuracy_drop": None,
        "attack_success_rate": None,
        "aspect_scoring": None,
        "scored_risk_id": None,
        "risks_triggered": [],
        "proposed_mapping": False,
        "note": _NOTE,
    }


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
        allow_domain_mismatch = _extra_bool(extra, "allow_domain_mismatch", False)

        logical_key, declared_domain, resolution_source = _resolve_robustness_dataset(ctx)
        dataset_info: dict[str, Any] = {
            "logical_key": logical_key,
            "resolution_source": resolution_source,
            "evaluation_domain": declared_domain,
        }
        base_metrics = _base_metrics(
            logical_key=logical_key,
            budget=budget,
            max_changes=max_changes,
            seed=seed,
            max_samples=max_samples,
            dataset_info=dataset_info,
        )
        flags: list[str] = []

        if logical_key is None:
            flags.extend(["no_compatible_dataset", "attack_skipped"])
            skip_reason = (
                "no explicit robustness dataset: set probe_config.datasets.robustness "
                "or add versioned entry in supported_robustness_compat_v1.yaml"
            )
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.4,
                status=ProbeEvaluationStatus.NOT_APPLICABLE,
                status_reason=skip_reason,
            )

        try:
            spec = get_dataset_spec(logical_key)
        except KeyError:
            flags.extend(["dataset_load_failed", "attack_skipped"])
            skip_reason = f"unknown dataset logical_key={logical_key}"
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        if spec.task_type == "regression":
            flags.extend(["unsupported_task", "attack_skipped"])
            skip_reason = "regression robustness not pinned for v1.0"
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.4,
                status=ProbeEvaluationStatus.NOT_APPLICABLE,
                status_reason=skip_reason,
            )

        dataset_info.update(
            {
                "hf_path": spec.hf_path,
                "revision": spec.revision,
                "modality": spec.modality,
                "config_name": spec.config_name,
                "task_type": spec.task_type,
                "evaluation_domain": spec.evaluation_domain or declared_domain,
            }
        )

        if spec.modality != "nlp":
            flags.extend(["unsupported_modality", "attack_skipped"])
            skip_reason = f"modality={spec.modality} (NLP path only)"
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.4,
                status=ProbeEvaluationStatus.NOT_APPLICABLE,
                status_reason=skip_reason,
            )

        meta = ctx.model_metadata or {}
        if not _is_text_classification(meta):
            flags.extend(["unsupported_modality", "attack_skipped"])
            skip_reason = "model is not text-classification / sentiment"
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.4,
                status=ProbeEvaluationStatus.NOT_APPLICABLE,
                status_reason=skip_reason,
            )

        compat = resolve_robustness_compat(ctx.model_ref, revision=ctx.model_revision)
        compat_domain = compat.evaluation_domain if compat else None
        pin_domain = spec.evaluation_domain
        domain_mismatch, mapping_blocked_pre = _check_domain_compat(
            dataset_domain=pin_domain,
            compat_domain=compat_domain,
            allow_domain_mismatch=allow_domain_mismatch,
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
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        inference_config = _resolve_inference_config(spec)
        hf_token = self._hf_token()
        try:
            result = self._resolve_runner().run(
                model_ref=ctx.model_ref,
                model_revision=ctx.model_revision,
                samples=samples,
                max_changes=max_changes,
                seed=seed,
                hf_token=hf_token,
                inference_config=inference_config,
            )
        except Exception as exc:  # noqa: BLE001 — execution failure → FAILED
            logger.warning("robustness_model_or_attack_failed err=%s", exc)
            flags.extend(["model_load_failed", "attack_skipped"])
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "n_samples": len(samples),
                    "skip_reason": str(exc),
                },
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        if result.insufficient_evidence:
            eval_out = evaluate_classification_robustness(
                aligned=[],
                n_requested=result.n_samples,
                n_label_compatible=result.n_label_compatible,
                label_compat_fraction=result.label_compat_fraction,
                n_successfully_perturbed=result.n_successfully_perturbed,
                perturbation_coverage=result.perturbation_coverage,
                seed=seed,
                domain_mismatch=domain_mismatch,
                allow_domain_mismatch=allow_domain_mismatch,
                mapping_blocked_pre=mapping_blocked_pre,
            )
            return self._finish_from_eval(
                ctx,
                eval_out=eval_out,
                base_metrics=base_metrics,
                result=result,
                extra_flags=flags,
            )

        eval_out = evaluate_classification_robustness(
            aligned=result.aligned_rows,
            n_requested=result.n_samples,
            n_label_compatible=result.n_label_compatible,
            label_compat_fraction=result.label_compat_fraction,
            n_successfully_perturbed=result.n_successfully_perturbed,
            perturbation_coverage=result.perturbation_coverage,
            seed=seed,
            domain_mismatch=domain_mismatch,
            allow_domain_mismatch=allow_domain_mismatch,
            mapping_blocked_pre=mapping_blocked_pre,
        )
        return self._finish_from_eval(
            ctx,
            eval_out=eval_out,
            base_metrics=base_metrics,
            result=result,
            extra_flags=flags,
        )

    def _finish_from_eval(
        self,
        ctx: ProbeContext,
        *,
        eval_out: Any,
        base_metrics: dict[str, Any],
        result: RobustnessRunResult,
        extra_flags: list[str],
    ) -> ProbeOutput:
        metrics = {
            **base_metrics,
            **eval_out.metrics,
            "aspect_scoring": eval_out.aspect_scoring,
            "scored_risk_id": eval_out.scored_risk_id,
            "risks_triggered": eval_out.risks_triggered,
            "reliability": eval_out.reliability,
            "uncertainty": eval_out.uncertainty,
            "limitations": eval_out.limitations,
            "n_samples": eval_out.metrics.get("n_evaluated", result.n_evaluated),
        }
        flags = list(dict.fromkeys(extra_flags + eval_out.flags))
        return self._finish(
            ctx,
            metrics=metrics,
            flags=flags,
            confidence=eval_out.confidence,
            status=eval_out.status,
            status_reason=eval_out.status_reason,
            result=result,
            eval_out=eval_out,
        )

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
        status: ProbeEvaluationStatus = ProbeEvaluationStatus.EVALUATED,
        status_reason: str | None = None,
        result: RobustnessRunResult | None = None,
        eval_out: Any = None,
    ) -> ProbeOutput:
        drop_ci = None
        if eval_out is not None:
            unc = eval_out.uncertainty or {}
            drop_ci = unc.get("accuracy_drop")
        artifact = {
            "probe": "robustness",
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "methodology": "tl-methodology-v1.0",
            "config": {
                "attack": metrics.get("attack"),
                "epsilon": metrics.get("epsilon"),
                "max_changes": metrics.get("max_changes"),
                "seed": metrics.get("seed"),
                "n_samples": metrics.get("n_samples"),
                "n_requested": metrics.get("n_requested"),
                "dataset": metrics.get("dataset"),
            },
            "coverage": {
                "n_label_compatible": metrics.get("n_label_compatible"),
                "n_successfully_perturbed": metrics.get("n_successfully_perturbed"),
                "n_perturb_failed": metrics.get("n_perturb_failed"),
                "perturbation_coverage": metrics.get("perturbation_coverage"),
                "label_compat_fraction": metrics.get("label_compat_fraction"),
            },
            "results": {
                "clean_accuracy": metrics.get("clean_accuracy"),
                "robust_accuracy": metrics.get("robust_accuracy"),
                "degradation_ratio": metrics.get("degradation_ratio"),
                "relative_degradation": metrics.get("relative_degradation"),
                "accuracy_drop": metrics.get("accuracy_drop"),
                "attack_success_rate": metrics.get("attack_success_rate"),
                "aspect_scoring": metrics.get("aspect_scoring"),
                "scored_risk_id": metrics.get("scored_risk_id"),
                "risks_triggered": metrics.get("risks_triggered"),
                "skip_reason": metrics.get("skip_reason"),
            },
            "uncertainty": metrics.get("uncertainty"),
            "reliability": metrics.get("reliability"),
            "limitations": metrics.get("limitations"),
            "flags": flags,
            "proposed_mapping": False,
            "per_sample": result.aligned_rows[:20] if result else [],
        }
        if drop_ci:
            artifact["results"]["accuracy_drop_ci_lower"] = drop_ci.get("ci_lower")
            artifact["results"]["accuracy_drop_ci_upper"] = drop_ci.get("ci_upper")
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
                probe_name="robustness",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise
        persisted = {
            **metrics,
            "probe_status": status.value,
            "probe_status_reason": status_reason,
            "status": status.value,
            "methodology_version": "tl-methodology-v1.0",
        }
        if eval_out and eval_out.scored_risk_id == SCORED_RISK_ID:
            unc = eval_out.uncertainty or {}
            drop = unc.get("accuracy_drop") or {}
            persisted["drop_ci_lower"] = drop.get("ci_lower")
            persisted["drop_ci_upper"] = drop.get("ci_upper")
        return ProbeOutput(
            dimension=FriesDimension.ROBUSTNESS,
            metric_values=persisted,
            confidence=confidence,
            evidence_refs=[ref],
            flags=flags,
            status=status,
            status_reason=status_reason,
        )
