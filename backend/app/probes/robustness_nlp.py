"""NLP char-swap robustness runner (Phase 11 + Phase 2 methodology).

Uses InferenceBackend for model load/predict; attack logic stays here.
"""

from __future__ import annotations

import logging
import random
import string
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.inference.base import DecisionMode, DeviceInfo, InferenceConfig, InferenceBackend, TaskType
from app.inference.errors import MODEL_LOAD_ERROR, InferenceError
from app.inference.local_hf import LocalHFBackend
from app.inference.model_snapshot_check import verify_loaded_model_matches_snapshot
from app.schemas.evaluation_contract_v2 import ModelLabelSnapshot

logger = logging.getLogger("trustlens.probes.robustness")

_ALPHABET = string.ascii_lowercase + string.digits


@dataclass(frozen=True)
class RobustnessRunResult:
    clean_accuracy: float | None = None
    robust_accuracy: float | None = None
    attack_success_rate: float | None = None
    n_samples: int = 0
    n_evaluated: int = 0
    n_label_compatible: int = 0
    n_successfully_perturbed: int = 0
    n_perturb_failed: int = 0
    perturbation_coverage: float = 0.0
    label_compat_fraction: float = 0.0
    aligned_rows: list[dict[str, Any]] = field(default_factory=list)
    insufficient_evidence: bool = False
    insufficient_reason: str | None = None
    device_info: DeviceInfo | None = None


class RobustnessRunner(Protocol):
    def run(
        self,
        *,
        model_ref: str,
        model_revision: str | None,
        samples: list[dict[str, Any]],
        max_changes: int,
        seed: int,
        hf_token: str | None = None,
        inference_config: InferenceConfig | None = None,
        expected_label_snapshot: ModelLabelSnapshot | None = None,
    ) -> RobustnessRunResult: ...


def char_swap_attack(text: str, *, max_changes: int, rng: random.Random) -> str:
    """Substitute up to ``max_changes`` alphanumeric characters (deterministic RNG)."""
    chars = list(text)
    indices = [i for i, ch in enumerate(chars) if ch.isalnum()]
    if not indices or max_changes <= 0:
        return text
    rng.shuffle(indices)
    for idx in indices[:max_changes]:
        original = chars[idx]
        candidates = [c for c in _ALPHABET if c != original.lower()]
        if not candidates:
            continue
        replacement = rng.choice(candidates)
        chars[idx] = replacement.upper() if original.isupper() else replacement
    return "".join(chars)


def perturbation_succeeded(original: str, attacked: str) -> bool:
    """True when char-swap could perturb an eligible row."""
    if not original:
        return False
    has_alnum = any(ch.isalnum() for ch in original)
    if not has_alnum:
        return False
    return attacked != original


def task_type_from_spec(task_type: str | None) -> TaskType:
    if task_type == "binary_classification":
        return TaskType.BINARY_CLASSIFICATION
    if task_type == "regression":
        return TaskType.REGRESSION
    return TaskType.MULTICLASS_CLASSIFICATION


class TransformersCharSwapRunner:
    """Score clean vs char-swapped text via InferenceBackend."""

    def __init__(self, backend: InferenceBackend | None = None) -> None:
        self._backend = backend

    def _resolve_backend(self) -> InferenceBackend:
        return self._backend if self._backend is not None else LocalHFBackend()

    def run(
        self,
        *,
        model_ref: str,
        model_revision: str | None,
        samples: list[dict[str, Any]],
        max_changes: int,
        seed: int,
        hf_token: str | None = None,
        inference_config: InferenceConfig | None = None,
        expected_label_snapshot: ModelLabelSnapshot | None = None,
    ) -> RobustnessRunResult:
        backend = self._resolve_backend()
        config = inference_config or InferenceConfig(
            task_type=TaskType.MULTICLASS_CLASSIFICATION,
            decision=DecisionMode.ARGMAX,
            device="auto",
        )
        try:
            loaded = backend.load(
                model_ref,
                revision=model_revision,
                config=config,
                hf_token=hf_token,
            )
        except InferenceError:
            raise
        except Exception as exc:
            raise InferenceError(
                MODEL_LOAD_ERROR,
                f"failed to load model {model_ref}",
                details={"cause": str(exc)},
            ) from exc

        if expected_label_snapshot is not None:
            # Re-verify here, not just at draft intake: expected_label_snapshot
            # was frozen when the draft was validated, but the pinned revision
            # could still resolve to different weights by the time the worker
            # actually loads them. Trusting intake alone would silently run
            # the attack under the wrong label semantics — this hard-fails
            # instead.
            try:
                verify_loaded_model_matches_snapshot(loaded, expected_label_snapshot)
            except InferenceError:
                backend.close()
                raise

        device_info = backend.device_info()
        num_labels = loaded.num_labels
        rng = random.Random(seed)
        n_requested = len(samples)

        eval_indices: list[int] = []
        clean_texts: list[str] = []
        attacked_texts: list[str] = []
        labels: list[int] = []
        perturb_ok: list[bool] = []

        for idx, sample in enumerate(samples):
            label = int(sample["label"])
            if isinstance(num_labels, int) and (label < 0 or label >= num_labels):
                continue
            text = str(sample["text"])
            eval_indices.append(idx)
            labels.append(label)
            clean_texts.append(text)
            attacked = char_swap_attack(text, max_changes=max_changes, rng=rng)
            attacked_texts.append(attacked)
            perturb_ok.append(perturbation_succeeded(text, attacked))

        n_label_compatible = len(eval_indices)
        label_compat_fraction = (
            n_label_compatible / n_requested if n_requested else 0.0
        )
        n_successfully_perturbed = sum(1 for ok in perturb_ok if ok)
        n_perturb_failed = n_label_compatible - n_successfully_perturbed
        perturbation_coverage = (
            n_successfully_perturbed / n_label_compatible if n_label_compatible else 0.0
        )

        if not eval_indices:
            backend.close()
            return RobustnessRunResult(
                n_samples=n_requested,
                n_evaluated=0,
                n_label_compatible=0,
                n_successfully_perturbed=0,
                n_perturb_failed=0,
                perturbation_coverage=0.0,
                label_compat_fraction=label_compat_fraction,
                insufficient_evidence=True,
                insufficient_reason="no label-compatible samples after filter",
                device_info=device_info,
            )

        try:
            clean_preds = [
                int(p.y_hat) for p in backend.predict_batch(clean_texts).predictions
            ]
            robust_preds = [
                int(p.y_hat) for p in backend.predict_batch(attacked_texts).predictions
            ]
        except InferenceError:
            raise
        finally:
            backend.close()

        if len(clean_preds) != len(labels) or len(robust_preds) != len(labels):
            raise RuntimeError("prediction length mismatch")

        aligned_rows: list[dict[str, Any]] = []
        for label, yc, yr, text, attacked in zip(
            labels, clean_preds, robust_preds, clean_texts, attacked_texts, strict=True
        ):
            aligned_rows.append(
                {
                    "label": label,
                    "y_hat_clean": yc,
                    "y_hat_robust": yr,
                    "text": text,
                    "attacked_text": attacked,
                }
            )

        evaluated = len(labels)
        clean_correct = sum(1 for y, p in zip(labels, clean_preds, strict=True) if p == y)
        robust_correct = sum(1 for y, p in zip(labels, robust_preds, strict=True) if p == y)
        flipped = sum(
            1
            for y, c, r in zip(labels, clean_preds, robust_preds, strict=True)
            if c == y and r != y
        )

        clean_acc = clean_correct / evaluated
        robust_acc = robust_correct / evaluated
        asr = flipped / evaluated
        logger.info(
            "robustness_nlp_done model_ref=%s n=%s clean=%.4f robust=%.4f coverage=%.4f",
            model_ref,
            evaluated,
            clean_acc,
            robust_acc,
            perturbation_coverage,
        )
        return RobustnessRunResult(
            clean_accuracy=clean_acc,
            robust_accuracy=robust_acc,
            attack_success_rate=asr,
            n_samples=n_requested,
            n_evaluated=evaluated,
            n_label_compatible=n_label_compatible,
            n_successfully_perturbed=n_successfully_perturbed,
            n_perturb_failed=n_perturb_failed,
            perturbation_coverage=perturbation_coverage,
            label_compat_fraction=label_compat_fraction,
            aligned_rows=aligned_rows,
            device_info=device_info,
        )
