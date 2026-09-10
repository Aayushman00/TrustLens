"""ModelInputAdapter unit tests (network-free)."""

from __future__ import annotations

import pytest

from app.inference.adapters.plain_text import PlainTextAdapter
from app.inference.adapters.registry import get_adapter
from app.inference.errors import INVALID_INPUT, InferenceError


def test_plain_text_adapter_identity() -> None:
    adapter = PlainTextAdapter()
    raw = {"text": "hello", "label": 1, "sensitive": "A"}
    row = adapter.normalize_row(raw)
    assert row == {"text": "hello", "label": 1, "sensitive": "A"}
    assert adapter.adapt_batch([row]) == ["hello"]


def test_plain_text_adapter_rejects_empty() -> None:
    adapter = PlainTextAdapter()
    with pytest.raises(InferenceError) as exc:
        adapter.adapt_batch([{"text": "", "label": 0, "sensitive": "A"}])
    assert exc.value.code == INVALID_INPUT


def test_adapter_factory() -> None:
    assert get_adapter("plain_text_v1").adapter_id == "plain_text_v1"
