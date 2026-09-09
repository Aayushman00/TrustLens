"""hatexplain_post_tokens_v1 — HateXplain ``post_tokens`` + annotator majority vote."""

from __future__ import annotations

import json
import random
import urllib.request
from collections import Counter
from typing import Any

from app.inference.errors import INVALID_INPUT, InferenceError

_ADAPTER_ID = "hatexplain_post_tokens_v1"

# Canonical URLs referenced by the pinned Hub dataset loading script at
# Hate-speech-CNERG/hatexplain (revision in datasets_v1.yaml).
_HATEXPLAIN_DATA_URL = (
    "https://raw.githubusercontent.com/punyajoy/HateXplain/master/Data/dataset.json"
)
_HATEXPLAIN_SPLITS_URL = (
    "https://raw.githubusercontent.com/punyajoy/HateXplain/master/Data/post_id_divisions.json"
)

# Observed in canonical dataset.json: annotator labels are strings, not ints.
_LABEL_TO_INDEX: dict[str, int] = {
    "hatespeech": 0,
    "hate speech": 0,
    "normal": 1,
    "offensive": 2,
}


def _parse_label(value: Any) -> int | None:
    """Map HateXplain annotator label (string or int) to class index 0..2."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value in _LABEL_TO_INDEX.values() else None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _LABEL_TO_INDEX:
            return _LABEL_TO_INDEX[normalized]
        if normalized.replace(" ", "") == "hatespeech":
            return 0
    return None


def _majority_label(annotators: list[dict[str, Any]]) -> int | None:
    labels = [
        parsed
        for ann in annotators
        if isinstance(ann, dict)
        for parsed in [_parse_label(ann.get("label"))]
        if parsed is not None
    ]
    if not labels:
        return None
    return Counter(labels).most_common(1)[0][0]


def _majority_target(annotators: list[dict[str, Any]]) -> str | None:
    targets: list[str] = []
    for ann in annotators:
        raw = ann.get("target")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    targets.append(item.strip())
        elif isinstance(raw, str) and raw.strip():
            targets.append(raw.strip())
    if not targets:
        return None
    return Counter(targets).most_common(1)[0][0]


class HatexplainPostTokensAdapter:
    adapter_id = _ADAPTER_ID

    def normalize_row(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        tokens = raw.get("post_tokens")
        if not isinstance(tokens, list) or not tokens:
            return None
        if not all(isinstance(t, str) for t in tokens):
            return None
        text = " ".join(tokens).strip()
        if not text:
            return None
        annotators = raw.get("annotators")
        if not isinstance(annotators, list) or not annotators:
            return None
        label = _majority_label(annotators)
        sensitive = _majority_target(annotators)
        if label is None or sensitive is None:
            return None
        return {"text": text, "label": int(label), "sensitive": sensitive}

    def adapt_batch(self, rows: list[dict[str, Any]]) -> list[str]:
        texts: list[str] = []
        for i, row in enumerate(rows):
            text = row.get("text")
            if not isinstance(text, str) or not text.strip():
                raise InferenceError(
                    INVALID_INPUT,
                    "hatexplain_post_tokens_v1 requires normalized text on each row",
                    details={"row_index": i},
                )
            texts.append(text.strip())
        return texts


def fetch_hatexplain_raw_rows(
    *,
    n: int,
    seed: int,
    split: str = "train",
) -> list[dict[str, Any]]:
    """Load raw HateXplain rows from canonical JSON (Hub script source URLs)."""
    with urllib.request.urlopen(_HATEXPLAIN_DATA_URL, timeout=60) as resp:
        dataset = json.loads(resp.read().decode("utf-8"))
    with urllib.request.urlopen(_HATEXPLAIN_SPLITS_URL, timeout=60) as resp:
        divisions = json.loads(resp.read().decode("utf-8"))
    ids = divisions.get(split) or divisions.get("train") or []
    rng = random.Random(seed)
    rng.shuffle(ids)
    rows: list[dict[str, Any]] = []
    for post_id in ids:
        if len(rows) >= n:
            break
        raw = dataset.get(post_id)
        if isinstance(raw, dict):
            row = dict(raw)
            row["id"] = post_id
            rows.append(row)
    return rows
