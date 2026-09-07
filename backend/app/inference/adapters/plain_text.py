"""plain_text_v1 — rows already contain a ``text`` field."""

from __future__ import annotations

from typing import Any

from app.inference.errors import INVALID_INPUT, InferenceError

_ADAPTER_ID = "plain_text_v1"


class PlainTextAdapter:
    adapter_id = _ADAPTER_ID

    def normalize_row(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        label = raw.get("label")
        sensitive = raw.get("sensitive")
        if label is None or sensitive is None:
            return None
        if isinstance(sensitive, str) and not sensitive.strip():
            return None
        return {
            "text": text.strip(),
            "label": int(label),
            "sensitive": sensitive if not isinstance(sensitive, str) else sensitive.strip(),
        }

    def adapt_batch(self, rows: list[dict[str, Any]]) -> list[str]:
        texts: list[str] = []
        for i, row in enumerate(rows):
            text = row.get("text")
            if not isinstance(text, str) or not text.strip():
                raise InferenceError(
                    INVALID_INPUT,
                    "plain_text_v1 requires non-empty text on each row",
                    details={"row_index": i},
                )
            texts.append(text.strip())
        return texts
