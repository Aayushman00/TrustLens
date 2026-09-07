"""Fairness probe — group disparity evidence (tabular proxy or model-faithful pairing)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.datasets.loader import DatasetLoadError, load_fairness_subset, load_pairing_subset
from app.datasets.registry import DatasetSpec, get_dataset_spec
from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.inference.adapters import get_adapter
from app.inference.base import InferenceConfig, InferenceBackend, TaskType
from app.inference.errors import InferenceError
from app.inference.local_hf import LocalHFBackend
from app.inference.pairing import SupportedPairing, resolve_pairing
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.fairness_metrics import compute_fairness_bundle
from app.probes.fairness_multiclass import MulticlassFairnessResult, evaluate_multiclass_fairness
from app.probes.fairness_stats import METHODOLOGY_VERSION
from app.storage.evidence_store import EvidenceStoreError

logger = logging.getLogger("trustlens.probes.fairness")

_DEFAULT_DATASET_KEY = "adult_fairness"
_DEFAULT_SENSITIVE = "sex"
_DEFAULT_MIN_GROUP_N = 30
_DEFAULT_MAX_SAMPLES = 256
_DEFAULT_SEED = 42
_PROXY_NOTE = (
    "Predictions from sklearn LogisticRegression on tabular features — not the imported model"
)
_NOTE = (
    "Metrics are objective evidence only — not a normative fair/unfair judgment, "
    "not O/S/D, and not product FRIES"
)


class FairnessLoader(Protocol):
    def __call__(
        self,
        logical_key: str,
        *,
        n: int,
        seed: int,
        sensitive_attribute: str,
        spec: Any = None,
    ) -> list[dict[str, Any]]: ...


class FairnessPredictor(Protocol):
    def __call__(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        seed: int,
    ) -> list[int]: ...


def _clamp_samples(n: int) -> int:
    return max(20, min(1000, n))


def _extra_int(extra: dict[str, Any], key: str, default: int) -> int:
    raw = extra.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _resolve_sensitive(cfg: Any, extra: dict[str, Any], spec: DatasetSpec | None) -> str:
    """Legacy Adult path: dataset default, then user config, then ``sex``."""
    if spec and spec.fairness and spec.fairness.default_sensitive_attribute:
        return spec.fairness.default_sensitive_attribute
    slices = cfg.slice_definitions or {}
    for source in (slices, extra):
        raw = source.get("sensitive_attribute")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return _DEFAULT_SENSITIVE


def _resolve_sensitive_pairing(
    cfg: Any,
    extra: dict[str, Any],
    spec: DatasetSpec,
) -> str:
    """Pairing path: user config first, then dataset pin default (never model-inferred)."""
    slices = cfg.slice_definitions or {}
    for source in (extra, slices):
        raw = source.get("sensitive_attribute")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    if spec.fairness and spec.fairness.default_sensitive_attribute:
        return spec.fairness.default_sensitive_attribute
    return ""


def _validate_sensitive_attribute(name: str, spec: DatasetSpec) -> str | None:
    """Return human-readable error reason, or None when valid."""
    if spec.fairness is None:
        return "dataset has no fairness configuration block"
    if not isinstance(name, str) or not name.strip():
        return "sensitive_attribute is missing or empty"
    allowed = [a.name for a in spec.fairness.sensitive_attributes]
    if name.strip() not in allowed:
        return (
            f"sensitive_attribute={name!r} not declared in dataset fairness registry; "
            f"allowed={allowed}"
        )
    return None


def _applicability_class(pairing: SupportedPairing, spec: DatasetSpec) -> str:
    if pairing.task_type == "multiclass_classification" and spec.modality == "nlp":
        return "MULTICLASS_TEXT_CLF"
    if pairing.task_type == "binary_classification" and spec.modality == "nlp":
        return "BINARY_TEXT_CLF"
    if pairing.task_type == "binary_classification" and spec.modality == "tabular":
        return "BINARY_TABULAR_CLF"
    return "UNKNOWN_TASK"
def predict_with_logistic_regression(
    rows: Sequence[dict[str, Any]],
    *,
    seed: int,
) -> list[int]:
    """Fit a tiny LR on non-sensitive features within the subset; return Ŷ."""
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise RuntimeError(
            "scikit-learn and numpy are required for live fairness predictions"
        ) from exc

    y = [int(r["label"]) for r in rows]
    feature_keys = sorted({k for r in rows for k in (r.get("features") or {})})
    if not feature_keys:
        raise RuntimeError("no feature columns available for fairness predictor")

    encoders: dict[str, dict[Any, int]] = {}
    matrix: list[list[float]] = []
    for r in rows:
        feats = r.get("features") or {}
        vec: list[float] = []
        for key in feature_keys:
            val = feats.get(key)
            if isinstance(val, bool):
                vec.append(float(int(val)))
            elif isinstance(val, (int, float)):
                vec.append(float(val))
            else:
                mapping = encoders.setdefault(key, {})
                if val not in mapping:
                    mapping[val] = len(mapping)
                vec.append(float(mapping[val]))
        matrix.append(vec)

    x = np.asarray(matrix, dtype=float)
    y_arr = np.asarray(y, dtype=int)
    if len(set(y_arr.tolist())) < 2:
        return [int(y_arr[0])] * len(rows)

    clf = LogisticRegression(max_iter=500, random_state=seed)
    clf.fit(x, y_arr)
    return [int(p) for p in clf.predict(x)]


class FairnessProbe:
    """Fairness evidence via supported pairing (model-faithful) or Adult proxy."""

    def __init__(
        self,
        *,
        loader: FairnessLoader | None = None,
        predictor: FairnessPredictor | Callable[..., list[int]] | None = None,
        inference: InferenceBackend | None = None,
    ) -> None:
        self._loader = loader
        self._predictor = predictor
        self._inference = inference

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.FAIRNESS

    def _resolve_loader(self) -> FairnessLoader:
        return self._loader if self._loader is not None else load_fairness_subset

    def _resolve_predictor(self) -> FairnessPredictor:
        if self._predictor is not None:
            return self._predictor  # type: ignore[return-value]
        return predict_with_logistic_regression

    def _resolve_backend(self) -> InferenceBackend:
        return self._inference if self._inference is not None else LocalHFBackend()

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        cfg = ctx.probe_config
        extra = cfg.extra or {}
        seed = _extra_int(extra, "seed", _DEFAULT_SEED)
        max_samples = _clamp_samples(
            _extra_int(extra, "max_samples", _DEFAULT_MAX_SAMPLES)
        )
        min_group_n = _extra_int(extra, "min_group_n", _DEFAULT_MIN_GROUP_N)
        if min_group_n < 1:
            min_group_n = _DEFAULT_MIN_GROUP_N

        pairing = resolve_pairing(ctx.model_ref, revision=ctx.model_revision)
        if pairing is not None:
            spec_for_pairing = get_dataset_spec(pairing.dataset)
            fairness_cfg = spec_for_pairing.fairness
            min_total_n = fairness_cfg.min_total_n if fairness_cfg else 200
            min_group_n_cfg = fairness_cfg.min_group_n if fairness_cfg else 50
            max_samples = _clamp_samples(
                max(
                    _extra_int(extra, "max_samples", _DEFAULT_MAX_SAMPLES),
                    min_total_n,
                )
            )
            min_group_n = min_group_n_cfg
            return self._run_pairing_faithful(
                ctx,
                pairing=pairing,
                seed=seed,
                max_samples=max_samples,
                min_group_n=min_group_n,
                min_total_n=min_total_n,
            )

        logical_key = cfg.datasets.get("fairness") or _DEFAULT_DATASET_KEY
        sensitive_attribute = _resolve_sensitive(cfg, extra, None)
        return self._run_legacy(
            ctx,
            logical_key=logical_key,
            sensitive_attribute=sensitive_attribute,
            seed=seed,
            max_samples=max_samples,
            min_group_n=min_group_n,
        )

    def _run_pairing_faithful(
        self,
        ctx: ProbeContext,
        *,
        pairing: SupportedPairing,
        seed: int,
        max_samples: int,
        min_group_n: int,
        min_total_n: int,
    ) -> ProbeOutput:
        flags: list[str] = ["model_faithful_pairing"]
        spec = get_dataset_spec(pairing.dataset)
        extra = ctx.probe_config.extra or {}
        sensitive_attribute = _resolve_sensitive_pairing(
            ctx.probe_config, extra, spec
        )
        validation_err = _validate_sensitive_attribute(sensitive_attribute, spec)
        if validation_err:
            flag = (
                "missing_sensitive_attribute"
                if not sensitive_attribute.strip()
                else "invalid_sensitive_attribute"
            )
            if spec.fairness is None:
                flag = "missing_fairness_config"
            return self._finish_methodology(
                ctx,
                pairing=pairing,
                spec=spec,
                n_requested=max_samples,
                n_evaluated=0,
                n_dropped=0,
                sensitive_attribute=sensitive_attribute or None,
                inference_meta=None,
                evaluation_rows_sample=[],
                result=None,
                flags=flags + [flag, "metrics_skipped"],
                status=ProbeEvaluationStatus.FAILED,
                status_reason=validation_err,
                aspect_scoring="not_scored",
                confidence=0.35,
            )

        try:
            adapter = get_adapter(pairing.input_adapter)
            rows, n_dropped = load_pairing_subset(
                pairing.dataset,
                adapter=adapter,
                n=max_samples,
                seed=seed,
                spec=spec,
            )
        except (DatasetLoadError, KeyError) as exc:
            logger.warning("pairing_dataset_failed err=%s", exc)
            return self._finish_methodology(
                ctx,
                pairing=pairing,
                spec=spec,
                n_requested=max_samples,
                n_evaluated=0,
                n_dropped=0,
                sensitive_attribute=sensitive_attribute,
                inference_meta=None,
                evaluation_rows_sample=[],
                result=None,
                flags=flags + ["dataset_load_failed", "metrics_skipped"],
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
                aspect_scoring="not_scored",
                confidence=0.35,
            )

        backend = self._resolve_backend()
        inference_meta: dict[str, Any] | None = None
        y_pred: list[int] = []
        try:
            config = InferenceConfig(
                task_type=pairing.task_type_enum(),
                decision=pairing.decision_mode(),
                device=str(pairing.preprocessing.get("device", "cpu")),
                max_length=int(pairing.preprocessing.get("max_length", 256)),
                binary_threshold=float(
                    pairing.output_decoding.binary_threshold
                ),
            )
            loaded = backend.load(
                pairing.model_ref,
                revision=pairing.model_revision,
                config=config,
            )
            pairing.check_loaded_model(loaded, id2label=loaded.id2label)
            texts = adapter.adapt_batch(rows)
            batch = backend.predict_batch(texts)
            y_pred = [int(p.y_hat) for p in batch.predictions]
            inference_meta = {
                "model_ref": batch.metadata.model_ref,
                "revision": batch.metadata.revision,
                "task_type": batch.metadata.task_type,
                "device": batch.metadata.device,
                "device_name": batch.metadata.device_name,
                "dtype": batch.metadata.dtype,
                "batch_size": batch.metadata.batch_size,
                "backend": batch.metadata.backend,
                "num_labels": batch.metadata.num_labels,
            }
        except InferenceError as exc:
            logger.warning("pairing_inference_failed err=%s", exc)
            return self._finish_methodology(
                ctx,
                pairing=pairing,
                spec=spec,
                n_requested=max_samples,
                n_evaluated=len(rows),
                n_dropped=n_dropped,
                sensitive_attribute=sensitive_attribute,
                inference_meta=None,
                evaluation_rows_sample=[],
                result=None,
                flags=flags + ["predictor_failed", "metrics_skipped"],
                status=ProbeEvaluationStatus.FAILED,
                status_reason=exc.message,
                aspect_scoring="not_scored",
                confidence=0.35,
            )
        finally:
            backend.close()

        if len(y_pred) != len(rows):
            skip_reason = "prediction count does not match input count"
            return self._finish_methodology(
                ctx,
                pairing=pairing,
                spec=spec,
                n_requested=max_samples,
                n_evaluated=len(rows),
                n_dropped=n_dropped,
                sensitive_attribute=sensitive_attribute,
                inference_meta=inference_meta,
                evaluation_rows_sample=[],
                result=None,
                flags=flags + ["predictor_failed", "metrics_skipped"],
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
                aspect_scoring="not_scored",
                confidence=0.35,
            )

        aligned = [
            {
                "text": rows[i]["text"],
                "label": int(rows[i]["label"]),
                "sensitive": rows[i]["sensitive"],
                "y_hat": y_pred[i],
            }
            for i in range(len(rows))
        ]

        if pairing.task_type == "binary_classification":
            base_metrics: dict[str, Any] = {
                "sensitive_attribute": sensitive_attribute,
                "min_group_n": min_group_n,
                "seed": seed,
                "n_samples": len(rows),
                "n_dropped": n_dropped,
                "n_evaluated": len(aligned),
                "fairness_mode": "model_faithful",
                "predictor": "inference_backend",
                "task_type": pairing.task_type,
                "pairing_id": pairing.id,
                "adapter_id": pairing.input_adapter,
                "inference": inference_meta,
                "evaluation_rows_sample": aligned[:5],
            }
            y_true = [r["label"] for r in rows]
            sensitive = [r["sensitive"] for r in rows]
            try:
                bundle = compute_fairness_bundle(y_true, y_pred, sensitive)
            except ValueError as exc:
                return self._finish(
                    ctx,
                    metrics={**base_metrics, "skip_reason": str(exc)},
                    flags=flags + ["metrics_skipped"],
                    confidence=0.4,
                    status=ProbeEvaluationStatus.FAILED,
                    status_reason=str(exc),
                )
            if int(bundle["min_group_n_observed"]) < min_group_n:
                flags.append("insufficient_slice_size")
            base_metrics.update(
                {
                    "demographic_parity_difference": bundle["demographic_parity_difference"],
                    "equalized_odds_difference": bundle["equalized_odds_difference"],
                    "subgroup_f1_spread": bundle["subgroup_f1_spread"],
                    "groups": bundle["groups"],
                    "min_group_n_observed": bundle["min_group_n_observed"],
                    "proposed_mapping": False,
                    "needs_human_review": True,
                }
            )
            confidence = 0.75 if "insufficient_slice_size" in flags else 0.85
            return self._finish(
                ctx,
                metrics=base_metrics,
                flags=flags,
                confidence=confidence,
                status=ProbeEvaluationStatus.EVALUATED,
            )

        mc_result = evaluate_multiclass_fairness(
            aligned,
            seed=seed,
            min_total_n=min_total_n,
            min_group_n=min_group_n,
            sensitive_attribute=sensitive_attribute,
        )
        return self._finish_methodology(
            ctx,
            pairing=pairing,
            spec=spec,
            n_requested=max_samples,
            n_evaluated=len(aligned),
            n_dropped=n_dropped,
            sensitive_attribute=sensitive_attribute,
            inference_meta=inference_meta,
            evaluation_rows_sample=aligned[:5],
            result=mc_result,
            flags=mc_result.flags,
            status=mc_result.status,
            status_reason=mc_result.status_reason,
            aspect_scoring=mc_result.aspect_scoring,
            confidence=mc_result.confidence,
        )

    def _finish_methodology(
        self,
        ctx: ProbeContext,
        *,
        pairing: SupportedPairing,
        spec: DatasetSpec,
        n_requested: int,
        n_evaluated: int,
        n_dropped: int,
        sensitive_attribute: str | None,
        inference_meta: dict[str, Any] | None,
        evaluation_rows_sample: list[dict[str, Any]],
        result: MulticlassFairnessResult | None,
        flags: list[str],
        status: ProbeEvaluationStatus,
        status_reason: str | None,
        aspect_scoring: str,
        confidence: float,
    ) -> ProbeOutput:
        metrics: dict[str, Any] = {
            "fairness_mode": "model_faithful",
            "predictor": "inference_backend",
            "task_type": pairing.task_type,
            "pairing_id": pairing.id,
            "adapter_id": pairing.input_adapter,
            "sensitive_attribute": sensitive_attribute,
            "n_requested": n_requested,
            "n_evaluated": n_evaluated,
            "n_dropped": n_dropped,
            "seed": ctx.probe_config.extra.get("seed", _DEFAULT_SEED)
            if ctx.probe_config.extra
            else _DEFAULT_SEED,
            "inference": inference_meta,
            "evaluation_rows_sample": evaluation_rows_sample,
            "proposed_mapping": False,
            "needs_human_review": True,
            "aspect_scoring": aspect_scoring,
            "osd_proposals": [],
        }
        uncertainty: dict[str, Any] = {}
        reliability: dict[str, Any] = {"gates_passed": True, "failed_gates": []}
        risks_triggered: list[str] = []
        scored_risk_id: str | None = None
        limitations: list[str] = []

        if result is not None:
            metrics.update(result.metrics)
            uncertainty = result.uncertainty
            reliability = result.reliability
            risks_triggered = result.risks_triggered
            scored_risk_id = result.scored_risk_id
            limitations = result.limitations
            aspect_scoring = result.aspect_scoring
        else:
            metrics.setdefault("demographic_parity_difference", "NOT_APPLICABLE")
            metrics.setdefault("equalized_odds_difference", "NOT_APPLICABLE")
            metrics.setdefault("subgroup_worst_group_acc_gap", None)

        artifact = {
            "methodology_version": METHODOLOGY_VERSION,
            "probe": "fairness",
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "model_revision": ctx.model_revision,
            "task_type": pairing.task_type,
            "applicability_class": _applicability_class(pairing, spec),
            "dataset": {
                "logical_key": pairing.dataset,
                "hf_path": spec.hf_path,
                "revision": spec.revision,
                "n_requested": n_requested,
                "n_evaluated": n_evaluated,
                "n_dropped": n_dropped,
                "seed": metrics["seed"],
                "sensitive_attribute": sensitive_attribute,
            },
            "status": status.value,
            "status_reason": status_reason,
            "aspect_scoring": aspect_scoring,
            "metrics": metrics,
            "uncertainty": uncertainty,
            "reliability": reliability,
            "risks_triggered": risks_triggered,
            "scored_risk_id": scored_risk_id,
            "osd_proposals": [],
            "flags": flags,
            "limitations": limitations,
            "note": _NOTE,
            "pairing": {
                "id": pairing.id,
                "model_ref": pairing.model_ref,
                "model_revision": pairing.model_revision,
                "input_adapter": pairing.input_adapter,
            },
        }
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
                probe_name="fairness",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise
        persisted = {
            **metrics,
            "probe_status": status.value,
            "probe_status_reason": status_reason,
            "scored_risk_id": scored_risk_id,
            "risks_triggered": risks_triggered,
            "uncertainty": uncertainty,
            "reliability": reliability,
            "limitations": limitations,
            "methodology_version": METHODOLOGY_VERSION,
        }
        return ProbeOutput(
            dimension=FriesDimension.FAIRNESS,
            metric_values=persisted,
            confidence=confidence,
            evidence_refs=[ref],
            flags=flags,
            status=status,
            status_reason=status_reason,
        )

    def _run_legacy(
        self,
        ctx: ProbeContext,
        *,
        logical_key: str,
        sensitive_attribute: str,
        seed: int,
        max_samples: int,
        min_group_n: int,
    ) -> ProbeOutput:
        flags: list[str] = []
        dataset_info: dict[str, Any] = {"logical_key": logical_key}
        base_metrics: dict[str, Any] = {
            "sensitive_attribute": sensitive_attribute,
            "min_group_n": min_group_n,
            "seed": seed,
            "n_samples": max_samples,
            "dataset": dataset_info,
            "demographic_parity_difference": None,
            "equalized_odds_difference": None,
            "subgroup_f1_spread": None,
            "groups": None,
            "proposed_mapping": False,
            "needs_human_review": False,
            "fairness_mode": "proxy_lr",
            "predictor": "sklearn_logistic_regression",
            "note": _NOTE,
            "proxy_limitation": _PROXY_NOTE,
        }

        try:
            spec = get_dataset_spec(logical_key)
        except KeyError:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            skip_reason = f"unknown dataset logical_key={logical_key}"
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        dataset_info.update(
            {
                "hf_path": spec.hf_path,
                "revision": spec.revision,
                "modality": spec.modality,
                "config_name": spec.config_name,
            }
        )

        if spec.modality not in {"tabular", "other"}:
            flags.extend(["unsupported_modality", "metrics_skipped"])
            skip_reason = (
                f"modality={spec.modality} — no supported pairing for model_ref={ctx.model_ref}"
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
            rows = self._resolve_loader()(
                logical_key,
                n=max_samples,
                seed=seed,
                sensitive_attribute=sensitive_attribute,
                spec=spec,
            )
        except DatasetLoadError as exc:
            logger.warning("fairness_dataset_failed err=%s", exc)
            msg = str(exc).lower()
            if "sensitive" in msg:
                flags.append("missing_sensitive_attribute")
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": str(exc)},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        if not rows:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            skip_reason = "empty fairness subset"
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        y_true = [int(r["label"]) for r in rows]
        sensitive = [r["sensitive"] for r in rows]
        try:
            y_pred = list(self._resolve_predictor()(rows, seed=seed))
        except Exception as exc:  # noqa: BLE001
            logger.warning("fairness_predictor_failed err=%s", exc)
            flags.extend(["predictor_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "n_samples": len(rows),
                    "skip_reason": str(exc),
                },
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        if len(y_pred) != len(rows):
            flags.extend(["predictor_failed", "metrics_skipped"])
            skip_reason = "predictor returned wrong length"
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "n_samples": len(rows),
                    "skip_reason": skip_reason,
                },
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        try:
            bundle = compute_fairness_bundle(y_true, y_pred, sensitive)
        except ValueError as exc:
            flags.extend(["metrics_skipped"])
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "n_samples": len(rows),
                    "skip_reason": str(exc),
                },
                flags=flags,
                confidence=0.4,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        if int(bundle["min_group_n_observed"]) < min_group_n:
            flags.append("insufficient_slice_size")

        metrics = {
            **base_metrics,
            "n_samples": len(rows),
            "demographic_parity_difference": bundle["demographic_parity_difference"],
            "equalized_odds_difference": bundle["equalized_odds_difference"],
            "subgroup_f1_spread": bundle["subgroup_f1_spread"],
            "groups": bundle["groups"],
            "min_group_n_observed": bundle["min_group_n_observed"],
            "needs_human_review": True,
        }
        flags.append("proxy_lr")
        confidence = 0.75 if "insufficient_slice_size" in flags else 0.85
        return self._finish(
            ctx,
            metrics=metrics,
            flags=flags,
            confidence=confidence,
            status=ProbeEvaluationStatus.PROXY,
        )

    def _finish(
        self,
        ctx: ProbeContext,
        *,
        metrics: dict[str, Any],
        flags: list[str],
        confidence: float,
        status: ProbeEvaluationStatus = ProbeEvaluationStatus.EVALUATED,
        status_reason: str | None = None,
    ) -> ProbeOutput:
        artifact = {
            "probe": "fairness",
            "evaluation_id": str(ctx.evaluation_id),
            "model_ref": ctx.model_ref,
            "config": {
                "sensitive_attribute": metrics.get("sensitive_attribute"),
                "min_group_n": metrics.get("min_group_n"),
                "seed": metrics.get("seed"),
                "n_samples": metrics.get("n_samples"),
                "dataset": metrics.get("dataset"),
                "pairing": metrics.get("pairing"),
            },
            "results": {
                "demographic_parity_difference": metrics.get(
                    "demographic_parity_difference"
                ),
                "equalized_odds_difference": metrics.get("equalized_odds_difference"),
                "subgroup_f1_spread": metrics.get("subgroup_f1_spread"),
                "subgroup_worst_group_acc_gap": metrics.get(
                    "subgroup_worst_group_acc_gap"
                ),
                "groups": metrics.get("groups"),
                "n_evaluated": metrics.get("n_evaluated"),
                "skip_reason": metrics.get("skip_reason"),
            },
            "flags": flags,
            "proposed_mapping": False,
            "needs_human_review": bool(metrics.get("needs_human_review")),
            "note": _NOTE,
            "probe_status": status.value,
            "probe_status_reason": status_reason,
        }
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(artifact, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
                probe_name="fairness",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise
        persisted = {
            **metrics,
            "probe_status": status.value,
            "probe_status_reason": status_reason,
        }
        return ProbeOutput(
            dimension=FriesDimension.FAIRNESS,
            metric_values=persisted,
            confidence=confidence,
            evidence_refs=[ref],
            flags=flags,
            status=status,
            status_reason=status_reason,
        )
