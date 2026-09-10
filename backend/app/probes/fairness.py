"""Fairness probe — group disparity evidence (tabular proxy or model-faithful pairing)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.datasets.loader import DatasetLoadError, load_fairness_subset, load_pairing_subset
from app.datasets.registry import DatasetSpec, get_dataset_spec
from app.datasets.user_dataset import (
    UserDatasetError,
    discover_group_values,
    load_rows_for_evaluation,
    load_rows_for_evaluation_with_label_mapping,
)
from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.db.repositories.dataset_content import DatasetContentRepository
from app.inference.adapters import get_adapter
from app.inference.base import InferenceConfig, InferenceBackend, TaskType
from app.inference.errors import InferenceError
from app.inference.local_hf import LocalHFBackend
from app.inference.pairing import SupportedPairing, get_pairing_by_id
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.fairness_metrics import compute_fairness_bundle
from app.probes.fairness_multiclass import MulticlassFairnessResult, evaluate_multiclass_fairness
from app.probes.fairness_stats import (
    METHODOLOGY_VERSION,
    filter_compared_groups,
    group_accuracies_from_aligned,
)
from app.schemas.evaluation_contract_v2 import EvaluationContractV2
from app.storage.evidence_store import EvidenceStoreError, format_sha256, hashes_equal

logger = logging.getLogger("trustlens.probes.fairness")

_PROXY_LR_DATASET_KEY = "adult_fairness"
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
        """Dispatch strictly on ``ctx.evaluation_contract`` (Phase 7).

        There is no implicit dataset fallback: an evaluation with no pairing
        and no explicit admin ``proxy_lr`` contract never runs Adult LR.
        """
        contract = ctx.evaluation_contract
        if isinstance(contract, EvaluationContractV2):
            return self._run_v2(ctx, contract)

        cfg = ctx.probe_config
        extra = cfg.extra or {}
        seed = _extra_int(extra, "seed", _DEFAULT_SEED)
        max_samples = _clamp_samples(
            _extra_int(extra, "max_samples", _DEFAULT_MAX_SAMPLES)
        )
        min_group_n = _extra_int(extra, "min_group_n", _DEFAULT_MIN_GROUP_N)
        if min_group_n < 1:
            min_group_n = _DEFAULT_MIN_GROUP_N

        kind = contract.kind if contract is not None else None

        if kind == "pairing":
            pairing = get_pairing_by_id(contract.pairing_id) if contract.pairing_id else None
            if pairing is None:
                return self._run_no_contract(
                    ctx,
                    contract=contract,
                    reason=(
                        f"evaluation contract references unknown "
                        f"pairing_id={contract.pairing_id!r}"
                    ),
                )
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

        if kind == "proxy_lr":
            if contract.dataset_key != _PROXY_LR_DATASET_KEY:
                return self._run_no_contract(
                    ctx,
                    contract=contract,
                    reason=(
                        "proxy_lr evaluation contract requires "
                        f"dataset_key={_PROXY_LR_DATASET_KEY!r}, got "
                        f"{contract.dataset_key!r}"
                    ),
                )
            sensitive_attribute = _resolve_sensitive(cfg, extra, None)
            return self._run_legacy(
                ctx,
                logical_key=_PROXY_LR_DATASET_KEY,
                sensitive_attribute=sensitive_attribute,
                seed=seed,
                max_samples=max_samples,
                min_group_n=min_group_n,
            )

        if kind == "user_dataset":
            included_raw = extra.get("included_group_values")
            included_group_values = (
                set(included_raw) if isinstance(included_raw, list) else None
            )
            return self._run_user_dataset(
                ctx,
                contract=contract,
                seed=seed,
                min_group_n=min_group_n,
                included_group_values=included_group_values,
                extra=extra,
            )

        # kind in {None, "documentation_only", "registry"}, or any other
        # value that does not authorize Fairness: no Adult fallback, ever.
        reason = (
            "no fairness evaluation contract (pairing or explicit admin "
            "proxy_lr) was selected for this evaluation"
            if contract is None
            else (
                f"evaluation contract kind={contract.kind!r} does not "
                "authorize a Fairness run"
            )
        )
        return self._run_no_contract(ctx, contract=contract, reason=reason)

    def _run_no_contract(
        self,
        ctx: ProbeContext,
        *,
        contract: Any,
        reason: str,
    ) -> ProbeOutput:
        """No pairing / no explicit proxy_lr: NOT_APPLICABLE, never Adult."""
        metrics: dict[str, Any] = {
            "fairness_mode": "not_applicable",
            "predictor": None,
            "demographic_parity_difference": None,
            "equalized_odds_difference": None,
            "subgroup_f1_spread": None,
            "groups": None,
            "proposed_mapping": False,
            "needs_human_review": False,
            "note": _NOTE,
            "skip_reason": reason,
            "model_ref": ctx.model_ref,
            "model_revision": ctx.model_revision,
            "dataset_key": contract.dataset_key if contract is not None else None,
            "dataset_revision": contract.dataset_revision if contract is not None else None,
            "pairing_id": contract.pairing_id if contract is not None else None,
            "evaluation_class": contract.kind if contract is not None else "missing",
            "inference_executed": False,
        }
        flags = ["no_fairness_contract", "metrics_skipped"]
        return self._finish(
            ctx,
            metrics=metrics,
            flags=flags,
            confidence=0.4,
            status=ProbeEvaluationStatus.NOT_APPLICABLE,
            status_reason=reason,
        )

    def _run_v2(self, ctx: ProbeContext, contract: EvaluationContractV2) -> ProbeOutput:
        """EvaluationContractV2 dispatch (Task 4.5).

        Mirrors ``_run_user_dataset`` below almost line-for-line — same
        hash-verify-before-use gate, same ``discover_group_values``/row-loading
        shape, same downstream ``compute_fairness_bundle``/
        ``evaluate_multiclass_fairness`` calls — substituting:
        - ``contract.fairness.dataset_content_id`` (+ a DB lookup via
          ``DatasetContentRepository``) for the legacy ``UserDataset``'s
          mutable ``dataset_uri``/``dataset_content_hash`` pair,
        - the confirmed ``label_mapping`` (dataset value -> model output
          index) for the legacy path's internally computed alphabetical
          ``0..k-1`` encoding — see
          ``load_rows_for_evaluation_with_label_mapping``.
        """
        cfg = ctx.probe_config
        extra = cfg.extra or {}
        seed = _extra_int(extra, "seed", _DEFAULT_SEED)

        if contract.fairness is None:
            return self._run_no_contract(
                ctx,
                contract=None,
                reason="Fairness was not configured for this evaluation",
            )
        fc = contract.fairness
        label_encoding = {e.dataset_value: e.model_label_index for e in fc.label_mapping}

        flags: list[str] = ["evaluation_contract_v2", "user_defined_local_dataset"]
        base_metrics: dict[str, Any] = {
            "fairness_mode": "not_evaluated",
            "predictor": "inference_backend",
            "evaluation_class": "user_dataset_v2",
            "inference_executed": False,
            "model_ref": contract.model_ref,
            "model_revision": contract.model_revision,
            "dataset_key": None,
            "dataset_revision": None,
            "dataset_content_id": str(fc.dataset_content_id),
            "dataset_format": "csv",
            "target_column": fc.target_column,
            "group_column": fc.sensitive_column,
            "text_column": fc.text_column,
            "sensitive_attribute": fc.sensitive_column,
            "min_group_n": fc.min_group_n,
            "seed": seed,
            "label_mapping": [e.model_dump() for e in fc.label_mapping],
            "note": _NOTE,
        }

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

        content_row = DatasetContentRepository(ctx.session).get_by_id(fc.dataset_content_id)
        if content_row is None:
            skip_reason = f"dataset content {fc.dataset_content_id} not found"
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

        # Hash-verify-before-use: DatasetContentStore's object key is itself
        # derived from the content hash (Task 1.2), so on the pure happy path
        # a get() by storage_uri can only return bytes matching that hash —
        # unlike the legacy UserDataset path, where the storage key is a
        # mutable, client-chosen filename and the hash check is the *only*
        # thing catching drifted content. Here the check is redundant on the
        # happy path but not meaningless: it still catches an object at that
        # key having been mutated out-of-band (a direct S3 write bypassing
        # DatasetContentStore.put(), bit rot, or a misrouted bucket/env), at
        # negligible cost. Kept for defense in depth, same posture as every
        # other evidence-integrity gate in this codebase.
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
            observed_groups, missing_summary = discover_group_values(
                data, group_column=fc.sensitive_column
            )
        except UserDatasetError as exc:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": str(exc)},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        dataset_row_count = sum(int(g["count"]) for g in observed_groups)

        try:
            rows, exclusions = load_rows_for_evaluation_with_label_mapping(
                data,
                target_column=fc.target_column,
                group_column=fc.sensitive_column,
                text_column=fc.text_column,
                # v2's contract carries no manual group-exclusion field yet;
                # thin-group filtering still happens downstream via
                # filter_compared_groups/min_group_n, same as the pairing path.
                excluded_group_values=set(),
                label_encoding=label_encoding,
            )
        except UserDatasetError as exc:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
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
                "dataset_row_count": dataset_row_count,
                "observed_groups": observed_groups,
                "missing_rows": missing_summary,
                "excluded_rows": {
                    "missing_target": exclusions["rows_dropped_missing_target"],
                    "missing_text": exclusions["rows_dropped_missing_text"],
                    "missing_group": exclusions["rows_dropped_missing_group"],
                    "unmapped_label": exclusions["rows_dropped_unmapped_label"],
                },
                "label_encoding": exclusions["label_encoding"],
                "n_evaluated": len(rows),
            }
        )

        label_values_seen = exclusions["label_values_seen"]
        if len(rows) == 0 or len(label_values_seen) < 2:
            skip_reason = (
                "fewer than 2 distinct target classes remain after exclusions"
                if rows
                else "no rows remain after missing-value/label-mapping exclusions"
            )
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        min_group_n = fc.min_group_n
        is_binary = len(label_values_seen) == 2
        backend = self._resolve_backend()
        inference_meta: dict[str, Any] | None = None
        y_pred: list[int] = []
        try:
            config = InferenceConfig(
                task_type=(
                    TaskType.BINARY_CLASSIFICATION
                    if is_binary
                    else TaskType.MULTICLASS_CLASSIFICATION
                ),
            )
            backend.load(contract.model_ref, revision=contract.model_revision, config=config)
            texts = [r["text"] for r in rows]
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
                "inference_backend": batch.metadata.backend,
                "num_labels": batch.metadata.num_labels,
                "execution_device": batch.metadata.execution_device,
                "gpu_available": batch.metadata.gpu_available,
                "gpu_name": batch.metadata.gpu_name,
                "cuda_available": batch.metadata.cuda_available,
                "device_reason": batch.metadata.device_reason,
                "fallback_reason": batch.metadata.fallback_reason,
            }
        except InferenceError as exc:
            logger.warning("v2_dataset_inference_failed err=%s", exc)
            flags.extend(["predictor_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": exc.message},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=exc.message,
            )
        finally:
            backend.close()

        if len(y_pred) != len(rows):
            skip_reason = "prediction count does not match input count"
            flags.extend(["predictor_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        base_metrics.update({"inference": inference_meta, "inference_executed": True})

        if is_binary:
            y_true = [r["label"] for r in rows]
            sensitive = [r["sensitive"] for r in rows]
            try:
                bundle = compute_fairness_bundle(y_true, y_pred, sensitive)
            except ValueError as exc:
                flags.append("metrics_skipped")
                return self._finish(
                    ctx,
                    metrics={**base_metrics, "skip_reason": str(exc)},
                    flags=flags,
                    confidence=0.4,
                    status=ProbeEvaluationStatus.FAILED,
                    status_reason=str(exc),
                )
            aligned_for_report = [
                {"label": y_true[i], "y_hat": y_pred[i], "sensitive": sensitive[i]}
                for i in range(len(rows))
            ]
            per_group_all = group_accuracies_from_aligned(aligned_for_report)
            _compared, excluded = filter_compared_groups(per_group_all, min_group_n)
            if excluded:
                flags.append("thin_groups_excluded")
            if int(bundle["min_group_n_observed"]) < min_group_n:
                flags.append("insufficient_slice_size")
            base_metrics.update(
                {
                    "fairness_mode": "user_defined_local",
                    "demographic_parity_difference": bundle["demographic_parity_difference"],
                    "equalized_odds_difference": bundle["equalized_odds_difference"],
                    "subgroup_f1_spread": bundle["subgroup_f1_spread"],
                    "groups": bundle["groups"],
                    "min_group_n_observed": bundle["min_group_n_observed"],
                    "excluded_groups": excluded,
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

        aligned = [
            {
                "text": rows[i]["text"],
                "label": rows[i]["label"],
                "sensitive": rows[i]["sensitive"],
                "y_hat": y_pred[i],
            }
            for i in range(len(rows))
        ]
        min_total_n = _extra_int(extra, "min_total_n", 200)
        mc_result = evaluate_multiclass_fairness(
            aligned,
            seed=seed,
            min_total_n=min_total_n,
            min_group_n=min_group_n,
            sensitive_attribute=fc.sensitive_column,
        )
        base_metrics.update(mc_result.metrics)
        base_metrics["min_total_n"] = min_total_n
        base_metrics["fairness_mode"] = (
            "user_defined_local"
            if mc_result.status != ProbeEvaluationStatus.FAILED
            else "not_evaluated"
        )
        persisted = {
            **base_metrics,
            "uncertainty": mc_result.uncertainty,
            "reliability": mc_result.reliability,
            "limitations": mc_result.limitations,
            "scored_risk_id": mc_result.scored_risk_id,
            "risks_triggered": mc_result.risks_triggered,
            "aspect_scoring": mc_result.aspect_scoring,
            "methodology_version": METHODOLOGY_VERSION,
        }
        all_flags = flags + mc_result.flags
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(persisted, separators=(",", ":"), default=str).encode("utf-8"),
                content_type="application/json",
                probe_name="fairness",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise
        return ProbeOutput(
            dimension=FriesDimension.FAIRNESS,
            metric_values=persisted,
            confidence=mc_result.confidence,
            evidence_refs=[ref],
            flags=all_flags,
            status=mc_result.status,
            status_reason=mc_result.status_reason,
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
                device=str(pairing.preprocessing.get("device", "auto")),
                max_length=int(pairing.preprocessing.get("max_length", 256)),
                binary_threshold=float(
                    pairing.output_decoding.binary_threshold
                ),
            )
            contract = ctx.evaluation_contract
            load_model_ref = contract.model_ref if contract is not None else pairing.model_ref
            load_model_revision = (
                contract.model_revision if contract is not None else pairing.model_revision
            )
            loaded = backend.load(
                load_model_ref,
                revision=load_model_revision,
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
                "inference_backend": batch.metadata.backend,
                "num_labels": batch.metadata.num_labels,
                "execution_device": batch.metadata.execution_device,
                "gpu_available": batch.metadata.gpu_available,
                "gpu_name": batch.metadata.gpu_name,
                "cuda_available": batch.metadata.cuda_available,
                "device_reason": batch.metadata.device_reason,
                "fallback_reason": batch.metadata.fallback_reason,
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
                "model_ref": ctx.model_ref,
                "model_revision": ctx.model_revision,
                "dataset_key": pairing.dataset,
                "dataset_revision": spec.revision,
                "evaluation_class": "pairing",
                "inference_executed": True,
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
        # Never claim model_faithful unless the pinned model actually loaded
        # and produced predictions — a validation/load/inference failure
        # before that point is not a faithful result.
        fairness_mode = (
            "model_faithful" if status != ProbeEvaluationStatus.FAILED else "not_evaluated"
        )
        metrics: dict[str, Any] = {
            "fairness_mode": fairness_mode,
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
            "model_ref": ctx.model_ref,
            "model_revision": ctx.model_revision,
            "dataset_key": pairing.dataset,
            "dataset_revision": spec.revision,
            "evaluation_class": "pairing",
            "inference_executed": inference_meta is not None,
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
            "model_ref": ctx.model_ref,
            "model_revision": ctx.model_revision,
            "dataset_key": logical_key,
            "pairing_id": None,
            "evaluation_class": "proxy_lr",
            "inference_executed": False,
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

    def _run_user_dataset(
        self,
        ctx: ProbeContext,
        *,
        contract: Any,
        seed: int,
        min_group_n: int,
        included_group_values: set[str] | None,
        extra: dict[str, Any],
    ) -> ProbeOutput:
        """User-defined local CSV dataset — exact selected model, no substitution.

        Reuses ``compute_fairness_bundle``/``evaluate_multiclass_fairness``
        unchanged; only row loading/group discovery differ from the pairing
        path (a user CSV instead of a pinned HF dataset).
        """
        flags: list[str] = ["user_defined_local_dataset"]
        base_metrics: dict[str, Any] = {
            "fairness_mode": "not_evaluated",
            "predictor": "inference_backend",
            "evaluation_class": "user_dataset",
            "inference_executed": False,
            "model_ref": ctx.model_ref,
            "model_revision": ctx.model_revision,
            "dataset_key": None,
            "dataset_revision": None,
            "user_dataset_id": contract.user_dataset_id,
            "dataset_format": "csv",
            "dataset_content_hash": contract.dataset_content_hash,
            "target_column": contract.target_column,
            "group_column": contract.group_column,
            "text_column": contract.text_column,
            "sensitive_attribute": contract.group_column,
            "min_group_n": min_group_n,
            "seed": seed,
            "note": _NOTE,
        }

        if ctx.dataset_store is None:
            skip_reason = "dataset storage is not configured on this TrustLens instance"
            flags.append("dataset_store_unavailable")
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        try:
            data = ctx.dataset_store.get_dataset(storage_uri=contract.dataset_uri)
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

        if not hashes_equal(format_sha256(data), contract.dataset_content_hash or ""):
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
            observed_groups, missing_summary = discover_group_values(
                data, group_column=contract.group_column
            )
        except UserDatasetError as exc:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": str(exc)},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=str(exc),
            )

        dataset_row_count = sum(int(g["count"]) for g in observed_groups)
        all_values = {g["value"] for g in observed_groups if g["value"] != "(missing)"}
        user_excluded = (
            set() if included_group_values is None else all_values - set(included_group_values)
        )

        try:
            rows, exclusions = load_rows_for_evaluation(
                data,
                target_column=contract.target_column,
                group_column=contract.group_column,
                text_column=contract.text_column,
                excluded_group_values=user_excluded,
            )
        except UserDatasetError as exc:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
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
                "dataset_row_count": dataset_row_count,
                "observed_groups": observed_groups,
                "missing_rows": missing_summary,
                "excluded_rows": {
                    "missing_target": exclusions["rows_dropped_missing_target"],
                    "missing_text": exclusions["rows_dropped_missing_text"],
                    "missing_group": exclusions["rows_dropped_missing_group"],
                    "user_excluded_group": exclusions["rows_dropped_excluded_group"],
                },
                "user_excluded_groups": sorted(user_excluded),
                "label_encoding": exclusions["label_encoding"],
                "n_evaluated": len(rows),
            }
        )

        label_values_seen = exclusions["label_values_seen"]
        if len(rows) == 0 or len(label_values_seen) < 2:
            skip_reason = (
                "fewer than 2 distinct target classes remain after exclusions"
                if rows
                else "no rows remain after missing-value/group exclusions"
            )
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        is_binary = len(label_values_seen) == 2
        backend = self._resolve_backend()
        inference_meta: dict[str, Any] | None = None
        y_pred: list[int] = []
        try:
            config = InferenceConfig(
                task_type=(
                    TaskType.BINARY_CLASSIFICATION
                    if is_binary
                    else TaskType.MULTICLASS_CLASSIFICATION
                ),
            )
            backend.load(contract.model_ref, revision=contract.model_revision, config=config)
            texts = [r["text"] for r in rows]
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
                "inference_backend": batch.metadata.backend,
                "num_labels": batch.metadata.num_labels,
                "execution_device": batch.metadata.execution_device,
                "gpu_available": batch.metadata.gpu_available,
                "gpu_name": batch.metadata.gpu_name,
                "cuda_available": batch.metadata.cuda_available,
                "device_reason": batch.metadata.device_reason,
                "fallback_reason": batch.metadata.fallback_reason,
            }
        except InferenceError as exc:
            logger.warning("user_dataset_inference_failed err=%s", exc)
            flags.extend(["predictor_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": exc.message},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=exc.message,
            )
        finally:
            backend.close()

        if len(y_pred) != len(rows):
            skip_reason = "prediction count does not match input count"
            flags.extend(["predictor_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": skip_reason},
                flags=flags,
                confidence=0.35,
                status=ProbeEvaluationStatus.FAILED,
                status_reason=skip_reason,
            )

        base_metrics.update({"inference": inference_meta, "inference_executed": True})

        if is_binary:
            y_true = [r["label"] for r in rows]
            sensitive = [r["sensitive"] for r in rows]
            try:
                bundle = compute_fairness_bundle(y_true, y_pred, sensitive)
            except ValueError as exc:
                flags.append("metrics_skipped")
                return self._finish(
                    ctx,
                    metrics={**base_metrics, "skip_reason": str(exc)},
                    flags=flags,
                    confidence=0.4,
                    status=ProbeEvaluationStatus.FAILED,
                    status_reason=str(exc),
                )
            # Reporting-only group-size exclusion metadata — compute_fairness_bundle
            # itself is called with the unfiltered rows above, unchanged.
            aligned_for_report = [
                {"label": y_true[i], "y_hat": y_pred[i], "sensitive": sensitive[i]}
                for i in range(len(rows))
            ]
            per_group_all = group_accuracies_from_aligned(aligned_for_report)
            _compared, excluded = filter_compared_groups(per_group_all, min_group_n)
            if excluded:
                flags.append("thin_groups_excluded")
            if int(bundle["min_group_n_observed"]) < min_group_n:
                flags.append("insufficient_slice_size")
            base_metrics.update(
                {
                    "fairness_mode": "user_defined_local",
                    "demographic_parity_difference": bundle["demographic_parity_difference"],
                    "equalized_odds_difference": bundle["equalized_odds_difference"],
                    "subgroup_f1_spread": bundle["subgroup_f1_spread"],
                    "groups": bundle["groups"],
                    "min_group_n_observed": bundle["min_group_n_observed"],
                    "excluded_groups": excluded,
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

        aligned = [
            {
                "text": rows[i]["text"],
                "label": rows[i]["label"],
                "sensitive": rows[i]["sensitive"],
                "y_hat": y_pred[i],
            }
            for i in range(len(rows))
        ]
        min_total_n = _extra_int(extra, "min_total_n", 200)
        mc_result = evaluate_multiclass_fairness(
            aligned,
            seed=seed,
            min_total_n=min_total_n,
            min_group_n=min_group_n,
            sensitive_attribute=contract.group_column,
        )
        base_metrics.update(mc_result.metrics)
        base_metrics["min_total_n"] = min_total_n
        base_metrics["fairness_mode"] = (
            "user_defined_local"
            if mc_result.status != ProbeEvaluationStatus.FAILED
            else "not_evaluated"
        )
        persisted = {
            **base_metrics,
            "uncertainty": mc_result.uncertainty,
            "reliability": mc_result.reliability,
            "limitations": mc_result.limitations,
            "scored_risk_id": mc_result.scored_risk_id,
            "risks_triggered": mc_result.risks_triggered,
            "aspect_scoring": mc_result.aspect_scoring,
            "methodology_version": METHODOLOGY_VERSION,
        }
        all_flags = flags + mc_result.flags
        try:
            ref = ctx.evidence_store.put_artifact(
                data=json.dumps(persisted, separators=(",", ":"), default=str).encode("utf-8"),
                content_type="application/json",
                probe_name="fairness",
                evaluation_id=ctx.evaluation_id,
            )
        except EvidenceStoreError:
            raise
        return ProbeOutput(
            dimension=FriesDimension.FAIRNESS,
            metric_values=persisted,
            confidence=mc_result.confidence,
            evidence_refs=[ref],
            flags=all_flags,
            status=mc_result.status,
            status_reason=mc_result.status_reason,
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
