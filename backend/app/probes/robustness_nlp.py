"""NLP char-swap robustness runner (Phase 11).

Lazy-imports torch/transformers. CPU-only. Discrete attack with fixed max_changes.
"""

from __future__ import annotations

import logging
import random
import string
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger("trustlens.probes.robustness")

_ALPHABET = string.ascii_lowercase + string.digits


@dataclass(frozen=True)
class RobustnessRunResult:
    clean_accuracy: float
    robust_accuracy: float
    attack_success_rate: float
    n_samples: int
    n_evaluated: int


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


class TransformersCharSwapRunner:
    """Load a sequence-classification model and score clean vs char-swapped text."""

    def run(
        self,
        *,
        model_ref: str,
        model_revision: str | None,
        samples: list[dict[str, Any]],
        max_changes: int,
        seed: int,
        hf_token: str | None = None,
    ) -> RobustnessRunResult:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "torch/transformers required for RobustnessProbe NLP runner"
            ) from exc

        device = torch.device("cpu")
        token_kwargs: dict[str, Any] = {}
        model_kwargs: dict[str, Any] = {}
        if model_revision:
            token_kwargs["revision"] = model_revision
            model_kwargs["revision"] = model_revision
        if hf_token:
            token_kwargs["token"] = hf_token
            model_kwargs["token"] = hf_token

        tokenizer = AutoTokenizer.from_pretrained(model_ref, **token_kwargs)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_ref, **model_kwargs
        )
        model.to(device)
        model.eval()

        def predict(text: str) -> int:
            encoded = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=256,
                padding=False,
            )
            encoded = {k: v.to(device) for k, v in encoded.items()}
            with torch.no_grad():
                logits = model(**encoded).logits
            return int(torch.argmax(logits, dim=-1).item())

        rng = random.Random(seed)
        n = len(samples)
        clean_correct = 0
        robust_correct = 0
        flipped = 0
        evaluated = 0

        for sample in samples:
            text = str(sample["text"])
            label = int(sample["label"])
            # Skip labels outside model head if possible
            num_labels = getattr(model.config, "num_labels", None)
            if isinstance(num_labels, int) and (label < 0 or label >= num_labels):
                continue
            evaluated += 1
            clean_pred = predict(text)
            if clean_pred == label:
                clean_correct += 1
            attacked = char_swap_attack(text, max_changes=max_changes, rng=rng)
            robust_pred = predict(attacked)
            if robust_pred == label:
                robust_correct += 1
            if clean_pred == label and robust_pred != label:
                flipped += 1

        if evaluated == 0:
            raise RuntimeError("no samples evaluated (label/model mismatch)")

        clean_acc = clean_correct / evaluated
        robust_acc = robust_correct / evaluated
        asr = flipped / evaluated
        logger.info(
            "robustness_nlp_done model_ref=%s n=%s clean=%.4f robust=%.4f",
            model_ref,
            evaluated,
            clean_acc,
            robust_acc,
        )
        return RobustnessRunResult(
            clean_accuracy=clean_acc,
            robust_accuracy=robust_acc,
            attack_success_rate=asr,
            n_samples=n,
            n_evaluated=evaluated,
        )
