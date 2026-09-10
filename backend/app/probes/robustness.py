"""Robustness probe — clean vs discrete char-swap accuracy (tl-methodology-v1.0).

NLP text-classification path only, for a user-defined local dataset. Emits
Layer A evidence with gates and R-ROB-PERT detection — does **not** map
metrics to O/S/D.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.datasets.user_dataset import (
    UserDatasetError,
    load_samples_for_robustness_with_label_mapping,
)
from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.db.repositories.dataset_content import DatasetContentRepository
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.robustness_eval import evaluate_classification_robustness
from app.probes.robustness_nlp import RobustnessRunner, RobustnessRunResult, TransformersCharSwapRunner
from app.probes.robustness_stats import SCORED_RISK_ID
from app.schemas.evaluation_contract_v2 import EvaluationContractV2
from app.storage.evidence_store import EvidenceStoreError, format_sha256, hashes_equal

logger = logging.getLogger("trustlens.probes.robustness")

_DEFAULT_BUDGET = 0.03
_DEFAULT_SEED = 42
_DEFAULT_MAX_SAMPLES = 200
_NOTE = "Layer A evidence only — R-ROB-PERT detection does not assign O/S/D"


def _budget_to_max_changes(budget: float) -> int:
    return max(1, min(8, round(budget * 100)))


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


def _base_metrics(
    *,
    logical_key: str | None,
    budget: float,
    max_changes: int,
    seed: int,
    max_samples: int,
    dataset_info: dict[str, Any],
    contract: Any | None,
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
        # Frozen evaluation-contract identity — never a freshly
        # substituted/auto-selected dataset or a live Model.revision read.
        "model_ref": contract.model_ref if contract is not None else None,
        "model_revision": contract.model_revision if contract is not None else None,
        "dataset_key": logical_key,
        "dataset_revision": None,
        "task_type": None,
        "evaluation_class": "missing",
        "inference_executed": False,
    }


class RobustnessProbe:
    """NLP robustness via a user-defined local dataset + discrete char-swap attack."""

    def __init__(self, runner: RobustnessRunner | None = None) -> None:
        self._runner = runner

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.ROBUSTNESS

    def _resolve_runner(self) -> RobustnessRunner:
        return self._runner if self._runner is not None else TransformersCharSwapRunner()

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        contract_any = ctx.evaluation_contract
        if isinstance(contract_any, EvaluationContractV2):
            return self._run_v2(ctx, contract_any)

        skip_reason = "no EvaluationContractV2 was attached to this evaluation"
        base_metrics = _base_metrics(
            logical_key=None,
            budget=_DEFAULT_BUDGET,
            max_changes=_budget_to_max_changes(_DEFAULT_BUDGET),
            seed=_DEFAULT_SEED,
            max_samples=0,
            dataset_info={"logical_key": None, "resolution_source": None, "evaluation_domain": None},
            contract=None,
        )
        return self._finish(
            ctx,
            metrics={**base_metrics, "skip_reason": skip_reason},
            flags=["no_robustness_contract", "attack_skipped"],
            confidence=0.4,
            status=ProbeEvaluationStatus.NOT_APPLICABLE,
            status_reason=skip_reason,
        )

    def _run_v2(self, ctx: ProbeContext, contract: EvaluationContractV2) -> ProbeOutput:
        """EvaluationContractV2 dispatch (Task 4.5).

        Mirrors ``robustness_nlp.TransformersCharSwapRunner.run``'s sample
        shape (``[{"text": str, "label": int}, ...]``) and this file's own
        pinned-dataset ``run()`` path below it for the runner-call/
        ``evaluate_classification_robustness``/``_finish_from_eval`` stages —
        those are reused completely unchanged. Only the front end differs:
        samples come from a user CSV (fetched via ``DatasetContentStore`` by
        ``contract.robustness.dataset_content_id``, hash-verified, then
        loaded through ``load_samples_for_robustness_with_label_mapping``
        using the confirmed ``label_mapping``) instead of a pinned HF
        dataset subset.
        """
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
        max_changes = _budget_to_max_changes(budget)

        if contract.robustness is None:
            skip_reason = "Robustness was not configured for this evaluation"
            base_metrics = _base_metrics(
                logical_key=None,
                budget=budget,
                max_changes=max_changes,
                seed=seed,
                max_samples=0,
                dataset_info={"logical_key": None, "resolution_source": None, "evaluation_domain": None},
                contract=None,
            )
            base_metrics["model_ref"] = contract.model_ref
            base_metrics["model_revision"] = contract.model_revision
            base_metrics["evaluation_class"] = "user_dataset_v2"
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=["no_robustness_contract"],
                confidence=0.4,
                status=ProbeEvaluationStatus.NOT_APPLICABLE,
                status_reason=skip_reason,
            )

        rc = contract.robustness
        label_encoding = {e.dataset_value: e.model_label_index for e in rc.label_mapping}
        flags: list[str] = ["evaluation_contract_v2", "user_defined_local_dataset"]
        base_metrics = _base_metrics(
            logical_key=None,
            budget=budget,
            max_changes=max_changes,
            seed=seed,
            max_samples=0,
            dataset_info={"logical_key": None, "resolution_source": "user_dataset_v2", "evaluation_domain": None},
            contract=None,
        )
        base_metrics.update(
            {
                "model_ref": contract.model_ref,
                "model_revision": contract.model_revision,
                "evaluation_class": "user_dataset_v2",
                "dataset_content_id": str(rc.dataset_content_id),
                "dataset_format": "csv",
                "target_column": rc.target_column,
                "text_column": rc.text_column,
                "label_mapping": [e.model_dump() for e in rc.label_mapping],
            }
        )

        if ctx.dataset_content_store is None or ctx.session is None:
            skip_reason = "dataset content storage is not configured on this TrustLens instance"
            flags.append("dataset_store_unavailable")
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        content_row = DatasetContentRepository(ctx.session).get_by_id(rc.dataset_content_id)
        if content_row is None:
            skip_reason = f"dataset content {rc.dataset_content_id} not found"
            flags.append("dataset_fetch_failed")
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        try:
            data = ctx.dataset_content_store.get(content_row.storage_uri)
        except EvidenceStoreError as exc:
            flags.append("dataset_fetch_failed")
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": str(exc)},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        # Hash-verify-before-use: see the identical comment in
        # fairness.py::_run_v2 — DatasetContentStore's key is derived from
        # the content hash itself, so this is redundant-but-harmless on the
        # happy path and is kept as a cheap defense against an out-of-band
        # mutation of the object at that key.
        if not hashes_equal(format_sha256(data), content_row.content_hash):
            skip_reason = "dataset content hash mismatch — refusing to evaluate drifted data"
            flags.append("dataset_hash_mismatch")
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        try:
            samples, exclusions = load_samples_for_robustness_with_label_mapping(
                data,
                target_column=rc.target_column,
                text_column=rc.text_column,
                label_encoding=label_encoding,
            )
        except UserDatasetError as exc:
            flags.extend(["dataset_load_failed", "attack_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": str(exc)},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        base_metrics.update(
            {
                "n_requested": len(samples),
                "n_samples": len(samples),
                "excluded_rows": {
                    "missing_target": exclusions["rows_dropped_missing_target"],
                    "missing_text": exclusions["rows_dropped_missing_text"],
                    "unmapped_label": exclusions["rows_dropped_unmapped_label"],
                },
                "label_encoding": exclusions["label_encoding"],
            }
        )

        if not samples:
            skip_reason = "no samples remain after missing-value/label-mapping exclusions"
            flags.extend(["dataset_load_failed", "attack_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        hf_token = self._hf_token()
        try:
            result = self._resolve_runner().run(
                model_ref=contract.model_ref,
                model_revision=contract.model_revision,
                samples=samples,
                max_changes=max_changes,
                seed=seed,
                hf_token=hf_token,
                expected_label_snapshot=contract.model_label_snapshot,
            )
        except Exception as exc:  # noqa: BLE001 — execution failure → FAILED
            logger.warning("robustness_v2_model_or_attack_failed err=%s", exc)
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

        base_metrics["inference_executed"] = not result.insufficient_evidence
        if result.device_info is not None:
            base_metrics["inference"] = {
                "device": result.device_info.device,
                "device_name": result.device_info.device_name,
                "backend": result.device_info.backend,
                "inference_backend": result.device_info.backend,
                "execution_device": result.device_info.execution_device,
                "gpu_available": result.device_info.gpu_available,
                "gpu_name": result.device_info.gpu_name,
                "cuda_available": result.device_info.cuda_available,
                "device_reason": result.device_info.device_reason,
                "fallback_reason": result.device_info.fallback_reason,
            }

        eval_out = evaluate_classification_robustness(
            aligned=result.aligned_rows,
            n_requested=result.n_samples,
            n_label_compatible=result.n_label_compatible,
            label_compat_fraction=result.label_compat_fraction,
            n_successfully_perturbed=result.n_successfully_perturbed,
            perturbation_coverage=result.perturbation_coverage,
            seed=seed,
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
            "model_revision": metrics.get("model_revision"),
            "dataset_key": metrics.get("dataset_key"),
            "dataset_revision": metrics.get("dataset_revision"),
            "task_type": metrics.get("task_type"),
            "label_space": metrics.get("label_space"),
            "evaluation_class": metrics.get("evaluation_class"),
            "inference_executed": metrics.get("inference_executed"),
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
