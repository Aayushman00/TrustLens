"""Fairness probe — group disparity evidence for a user-defined local dataset."""

from __future__ import annotations

import json
import logging
from functools import partial
from typing import Any

from app.datasets.user_dataset import (
    UserDatasetError,
    discover_group_values,
    load_rows_for_evaluation_with_label_mapping,
)
from app.db.enums import FriesDimension, ProbeEvaluationStatus
from app.db.repositories.dataset_content import DatasetContentRepository
from app.inference.base import InferenceConfig, InferenceBackend, TaskType
from app.inference.errors import InferenceError
from app.inference.local_hf import LocalHFBackend
from app.inference.model_snapshot_check import verify_loaded_model_matches_snapshot
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.fairness_metrics import compute_fairness_bundle
from app.probes.fairness_multiclass import evaluate_multiclass_fairness
from app.probes.fairness_stats import (
    CI_WIDE_THRESHOLD,
    METHODOLOGY_VERSION,
    _dp_gap_from_resampled,
    _eo_gap_from_resampled,
    _f1_gap_from_resampled,
    bootstrap_gap_ci,
    filter_compared_groups,
    group_accuracies_from_aligned,
)
from app.schemas.evaluation_contract_v2 import EvaluationContractV2
from app.storage.evidence_store import EvidenceStoreError, format_sha256, hashes_equal

logger = logging.getLogger("trustlens.probes.fairness")

_DEFAULT_MIN_GROUP_N = 30
_DEFAULT_SEED = 42
_NOTE = (
    "Metrics are objective evidence only — not a normative fair/unfair judgment, "
    "not O/S/D, and not product FRIES"
)


def _extra_int(extra: dict[str, Any], key: str, default: int) -> int:
    raw = extra.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


class FairnessProbe:
    """Fairness evidence via a user-defined, content-addressed local dataset."""

    def __init__(self, *, inference: InferenceBackend | None = None) -> None:
        self._inference = inference

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.FAIRNESS

    def _resolve_backend(self) -> InferenceBackend:
        return self._inference if self._inference is not None else LocalHFBackend()

    def run(self, ctx: ProbeContext) -> ProbeOutput:
        """Dispatch strictly on ``ctx.evaluation_contract`` (Phase 7).

        There is no implicit dataset fallback: an evaluation with no
        confirmed Fairness contract on its ``EvaluationContractV2`` never
        runs anything — it is NOT_APPLICABLE, always.
        """
        contract = ctx.evaluation_contract
        if isinstance(contract, EvaluationContractV2):
            return self._run_v2(ctx, contract)
        return self._run_no_contract(ctx, reason="no EvaluationContractV2 was attached to this evaluation")

    def _run_no_contract(
        self,
        ctx: ProbeContext,
        *,
        reason: str,
    ) -> ProbeOutput:
        """No EvaluationContractV2 at all: NOT_APPLICABLE, never a fallback."""
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
            "evaluation_class": "missing",
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
        """Sole Fairness evaluation path: EvaluationContractV2 dispatch.

        Fetches ``contract.fairness.dataset_content_id`` via
        ``DatasetContentRepository``, hash-verifies the bytes before use,
        then loads rows using the user-confirmed ``label_mapping`` (dataset
        value -> model output index) via
        ``load_rows_for_evaluation_with_label_mapping``, before running
        inference and ``compute_fairness_bundle``/``evaluate_multiclass_fairness``.
        """
        cfg = ctx.probe_config
        extra = cfg.extra or {}
        seed = _extra_int(extra, "seed", _DEFAULT_SEED)

        if contract.fairness is None:
            return self._run_no_contract(
                ctx,
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
            # V2 has no dataset_key/dataset_revision concept at all (that was
            # the deleted pinned-dataset-registry identity) — these stay
            # None by design, not omitted, so ProbeEvidenceRead's generic
            # metrics.get("dataset_key") read (shared with legacy rows)
            # never KeyErrors on a V2 row.
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
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=skip_reason)

        content_row = DatasetContentRepository(ctx.session).get_by_id(fc.dataset_content_id)
        if content_row is None:
            skip_reason = f"dataset content {fc.dataset_content_id} not found"
            flags.append("dataset_fetch_failed")
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=skip_reason)

        try:
            data = ctx.dataset_content_store.get(content_row.storage_uri)
        except EvidenceStoreError as exc:
            flags.append("dataset_fetch_failed")
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=str(exc))

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
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=skip_reason)

        try:
            observed_groups, missing_summary = discover_group_values(
                data, group_column=fc.sensitive_column
            )
        except UserDatasetError as exc:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=str(exc))

        dataset_row_count = sum(int(g["count"]) for g in observed_groups)

        try:
            rows, exclusions = load_rows_for_evaluation_with_label_mapping(
                data,
                target_column=fc.target_column,
                group_column=fc.sensitive_column,
                text_column=fc.text_column,
                # v2's contract carries no manual group-exclusion field yet;
                # thin-group filtering still happens downstream via
                # filter_compared_groups/min_group_n.
                excluded_group_values=set(),
                label_encoding=label_encoding,
            )
        except UserDatasetError as exc:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=str(exc))

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
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=skip_reason)

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
            loaded = backend.load(contract.model_ref, revision=contract.model_revision, config=config)
            # Re-verify here, not just at draft intake: contract.model_label_snapshot
            # was frozen when the draft was validated, but the pinned revision
            # could still resolve to different weights by the time the worker
            # actually loads them (a repo owner force-pushing the same tag,
            # e.g.). Trusting intake alone would silently score under the
            # wrong label semantics — this hard-fails instead.
            verify_loaded_model_matches_snapshot(loaded, contract.model_label_snapshot)
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
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=exc.message)
        finally:
            backend.close()

        if len(y_pred) != len(rows):
            skip_reason = "prediction count does not match input count"
            flags.extend(["predictor_failed", "metrics_skipped"])
            return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=skip_reason)

        base_metrics.update({"inference": inference_meta, "inference_executed": True})

        if is_binary:
            y_true = [r["label"] for r in rows]
            sensitive = [r["sensitive"] for r in rows]
            positive_label_index = fc.positive_label_index
            try:
                bundle = compute_fairness_bundle(
                    y_true, y_pred, sensitive, positive_label_index=positive_label_index
                )
            except ValueError as exc:
                flags.append("metrics_skipped")
                return self._fail(ctx, base_metrics=base_metrics, flags=flags, reason=str(exc), confidence=0.4)
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

            # Bootstrap CI on all three point estimates, reusing the same
            # resampling machinery evaluate_multiclass_fairness uses (via
            # stat_fn) instead of a second implementation. Only DP's CI
            # width gates scoring (G-FAIR-CI-WIDE) -- DP is the headline
            # binary fairness number; EO/F1-spread get a non-blocking
            # warning flag so a wide CI there is visible without blocking
            # an otherwise-usable result.
            dp_ci = bootstrap_gap_ci(
                aligned_for_report,
                min_group_n=min_group_n,
                seed=seed,
                stat_fn=partial(_dp_gap_from_resampled, positive_label_index=positive_label_index),
            )
            eo_ci = bootstrap_gap_ci(
                aligned_for_report,
                min_group_n=min_group_n,
                seed=seed,
                stat_fn=partial(_eo_gap_from_resampled, positive_label_index=positive_label_index),
            )
            f1_ci = bootstrap_gap_ci(
                aligned_for_report,
                min_group_n=min_group_n,
                seed=seed,
                stat_fn=partial(_f1_gap_from_resampled, positive_label_index=positive_label_index),
            )
            for ci_name, ci in (("eo", eo_ci), ("f1", f1_ci)):
                if (
                    ci["ci_lower"] is not None
                    and ci["ci_upper"] is not None
                    and (ci["ci_upper"] - ci["ci_lower"]) > CI_WIDE_THRESHOLD
                ):
                    flags.append(f"wide_ci_{ci_name}")

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
                    "dp_ci": dp_ci,
                    "eo_ci": eo_ci,
                    "f1_ci": f1_ci,
                    "positive_label_index": positive_label_index,
                }
            )

            if (
                dp_ci["ci_lower"] is not None
                and dp_ci["ci_upper"] is not None
                and (dp_ci["ci_upper"] - dp_ci["ci_lower"]) > CI_WIDE_THRESHOLD
            ):
                flags.append("wide_ci_dp")
                return self._finish(
                    ctx,
                    metrics=base_metrics,
                    flags=flags,
                    confidence=0.75,
                    status=ProbeEvaluationStatus.EVALUATED,
                    status_reason=(
                        "G-FAIR-CI-WIDE: demographic_parity_difference CI width "
                        f"exceeds {CI_WIDE_THRESHOLD} — scoring blocked"
                    ),
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

    def _fail(
        self,
        ctx: ProbeContext,
        *,
        base_metrics: dict[str, Any],
        flags: list[str],
        reason: str,
        confidence: float = 0.35,
    ) -> ProbeOutput:
        """Shared shape for every FAILED early-return in ``_run_v2`` — same
        ``metrics={**base_metrics, "skip_reason": reason}``/``status=FAILED``
        pattern repeated at each failure point, differing only in ``flags``,
        ``reason``, and (once) ``confidence``."""
        return self._finish(
            ctx,
            metrics={**base_metrics, "skip_reason": reason},
            flags=flags,
            confidence=confidence,
            status=ProbeEvaluationStatus.FAILED,
            status_reason=reason,
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
                "dp_ci": metrics.get("dp_ci"),
                "eo_ci": metrics.get("eo_ci"),
                "f1_ci": metrics.get("f1_ci"),
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
