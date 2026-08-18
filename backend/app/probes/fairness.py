"""Fairness probe — demographic parity / equalized odds / F1 spread (Phase 12).

Uses a pinned tabular Adult subset (or injected fixture). Metrics are objective
evidence only — never a fair/unfair verdict and never O/S/D or product FRIES.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.datasets.loader import DatasetLoadError, load_fairness_subset
from app.datasets.registry import get_dataset_spec
from app.db.enums import FriesDimension
from app.probes.base import ProbeContext, ProbeOutput
from app.probes.fairness_metrics import compute_fairness_bundle
from app.storage.evidence_store import EvidenceStoreError

logger = logging.getLogger("trustlens.probes.fairness")

_DEFAULT_DATASET_KEY = "adult_fairness"
_DEFAULT_SENSITIVE = "sex"
_DEFAULT_MIN_GROUP_N = 30
_DEFAULT_MAX_SAMPLES = 256
_DEFAULT_SEED = 42
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


def _resolve_sensitive(cfg: Any, extra: dict[str, Any]) -> str:
    slices = cfg.slice_definitions or {}
    for source in (slices, extra):
        raw = source.get("sensitive_attribute")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return _DEFAULT_SENSITIVE


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
        # Degenerate subset — constant predictions keep metrics defined.
        return [int(y_arr[0])] * len(rows)

    clf = LogisticRegression(max_iter=500, random_state=seed)
    clf.fit(x, y_arr)
    return [int(p) for p in clf.predict(x)]


class FairnessProbe:
    """Tabular group-fairness metrics via Adult pin or injected fixture."""

    def __init__(
        self,
        *,
        loader: FairnessLoader | None = None,
        predictor: FairnessPredictor | Callable[..., list[int]] | None = None,
    ) -> None:
        self._loader = loader
        self._predictor = predictor

    @property
    def dimension(self) -> FriesDimension:
        return FriesDimension.FAIRNESS

    def _resolve_loader(self) -> FairnessLoader:
        return self._loader if self._loader is not None else load_fairness_subset

    def _resolve_predictor(self) -> FairnessPredictor:
        if self._predictor is not None:
            return self._predictor  # type: ignore[return-value]
        return predict_with_logistic_regression

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
        sensitive_attribute = _resolve_sensitive(cfg, extra)
        logical_key = cfg.datasets.get("fairness") or _DEFAULT_DATASET_KEY

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
            "note": _NOTE,
        }

        try:
            spec = get_dataset_spec(logical_key)
        except KeyError:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
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

        if spec.modality not in {"tabular", "other"}:
            flags.extend(["unsupported_modality", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "skip_reason": (
                        f"modality={spec.modality} "
                        "(tabular Adult path only; SST-2 is not used for DP/EO)"
                    ),
                },
                flags=flags,
                confidence=0.4,
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
            )

        if not rows:
            flags.extend(["dataset_load_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={**base_metrics, "skip_reason": "empty fairness subset"},
                flags=flags,
                confidence=0.35,
            )

        y_true = [int(r["label"]) for r in rows]
        sensitive = [r["sensitive"] for r in rows]
        try:
            y_pred = list(self._resolve_predictor()(rows, seed=seed))
        except Exception as exc:  # noqa: BLE001 — soft-fail to keep evaluation alive
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
            )

        if len(y_pred) != len(rows):
            flags.extend(["predictor_failed", "metrics_skipped"])
            return self._finish(
                ctx,
                metrics={
                    **base_metrics,
                    "n_samples": len(rows),
                    "skip_reason": "predictor returned wrong length",
                },
                flags=flags,
                confidence=0.35,
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
        confidence = 0.75 if "insufficient_slice_size" in flags else 0.85
        return self._finish(ctx, metrics=metrics, flags=flags, confidence=confidence)

    def _finish(
        self,
        ctx: ProbeContext,
        *,
        metrics: dict[str, Any],
        flags: list[str],
        confidence: float,
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
            },
            "results": {
                "demographic_parity_difference": metrics.get(
                    "demographic_parity_difference"
                ),
                "equalized_odds_difference": metrics.get("equalized_odds_difference"),
                "subgroup_f1_spread": metrics.get("subgroup_f1_spread"),
                "groups": metrics.get("groups"),
                "skip_reason": metrics.get("skip_reason"),
            },
            "flags": flags,
            "proposed_mapping": False,
            "needs_human_review": bool(metrics.get("needs_human_review")),
            "note": _NOTE,
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
        return ProbeOutput(
            dimension=FriesDimension.FAIRNESS,
            metric_values=metrics,
            confidence=confidence,
            evidence_refs=[ref],
            flags=flags,
        )
