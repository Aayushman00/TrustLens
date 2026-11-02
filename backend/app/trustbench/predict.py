"""Shared predict_proba adapter for the v2 probes: P(toxic) per text, rounded to 4 dp.

Batch 256, seq 128 (training length), fp16 autocast on CUDA. torch / transformers are imported
lazily so the probes and their tests never need them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

BATCH = 256
MAX_LENGTH = 128


def _load(model_dir: Path, device: str) -> tuple[Any, Any]:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device).eval()
    return tok, model


def load_predict_proba(model_dir: Path, device: str) -> Callable[[list[str]], list[float]]:
    import torch

    tok, model = _load(Path(model_dir), device)
    dev = torch.device(device)

    def predict_proba(texts: list[str]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(texts), BATCH):
            enc = tok(texts[i:i + BATCH], truncation=True, max_length=MAX_LENGTH, padding=True,
                      return_tensors="pt").to(dev)
            with torch.no_grad(), torch.autocast(dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
                logits = model(**enc).logits.float()
            out += [round(float(x), 4) for x in torch.softmax(logits, -1)[:, 1].cpu()]
        return out

    return predict_proba
