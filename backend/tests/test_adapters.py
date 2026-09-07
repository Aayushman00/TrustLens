"""ModelInputAdapter unit tests (network-free)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.inference.adapters.hatexplain import HatexplainPostTokensAdapter
from app.inference.adapters.plain_text import PlainTextAdapter
from app.inference.adapters.registry import get_adapter
from app.inference.errors import INVALID_INPUT, InferenceError

_OBSERVED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "hatexplain_observed_raw.json"
)


def _load_observed_fixture() -> dict:
    return json.loads(_OBSERVED_FIXTURE.read_text(encoding="utf-8"))


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


def test_hatexplain_observed_raw_row_normalizes() -> None:
    """Regression: labels in live JSON are strings, not ints."""
    fixture = _load_observed_fixture()
    raw = fixture["raw"]
    expected = fixture["expected"]
    adapter = HatexplainPostTokensAdapter()
    row = adapter.normalize_row(raw)
    assert row is not None
    assert row["text"] == expected["text"]
    assert row["label"] == expected["label"]
    assert row["sensitive"] == expected["sensitive"]


def test_hatexplain_string_label_majority_vote() -> None:
    adapter = HatexplainPostTokensAdapter()
    raw = {
        "post_tokens": ["hello", "world"],
        "annotators": [
            {"label": "hatespeech", "annotator_id": 1, "target": ["African"]},
            {"label": "hatespeech", "annotator_id": 2, "target": ["African"]},
            {"label": "offensive", "annotator_id": 3, "target": ["African"]},
        ],
    }
    row = adapter.normalize_row(raw)
    assert row is not None
    assert row["label"] == 0
    assert row["sensitive"] == "African"


def test_hatexplain_rejects_unknown_label_string() -> None:
    adapter = HatexplainPostTokensAdapter()
    raw = {
        "post_tokens": ["x"],
        "annotators": [{"label": "not_a_class", "annotator_id": 1, "target": ["A"]}],
    }
    assert adapter.normalize_row(raw) is None


def test_hatexplain_token_order_preserved() -> None:
    adapter = HatexplainPostTokensAdapter()
    raw = {
        "post_tokens": ["the", "uk", "has"],
        "annotators": [
            {"label": "normal", "annotator_id": 1, "target": ["Indian"]},
        ],
    }
    row = adapter.normalize_row(raw)
    assert row is not None
    assert row["text"] == "the uk has"


def test_hatexplain_normalize_majority_int_labels_still_supported() -> None:
    adapter = HatexplainPostTokensAdapter()
    raw = {
        "post_tokens": ["hello", "world"],
        "annotators": [
            {"label": 0, "target": ["African"]},
            {"label": 0, "target": ["African"]},
            {"label": 2, "target": ["African"]},
        ],
    }
    row = adapter.normalize_row(raw)
    assert row is not None
    assert row["text"] == "hello world"
    assert row["label"] == 0
    assert row["sensitive"] == "African"


def test_hatexplain_drops_missing_target() -> None:
    adapter = HatexplainPostTokensAdapter()
    raw = {
        "post_tokens": ["x"],
        "annotators": [{"label": 1, "target": []}],
    }
    assert adapter.normalize_row(raw) is None


def test_hatexplain_batch_alignment_preserved() -> None:
    adapter = HatexplainPostTokensAdapter()
    raws = [
        {
            "post_tokens": ["a", "b"],
            "annotators": [{"label": "normal", "target": ["G1"]}],
        },
        {
            "post_tokens": ["c"],
            "annotators": [{"label": "offensive", "target": ["G2"]}],
        },
    ]
    rows = [adapter.normalize_row(r) for r in raws]
    assert rows[0] is not None and rows[1] is not None
    assert adapter.adapt_batch(rows) == ["a b", "c"]
    assert rows[0]["label"] == 1
    assert rows[1]["label"] == 2


def test_hatexplain_order_preserved() -> None:
    adapter = HatexplainPostTokensAdapter()
    rows = [
        {"text": "a", "label": 0, "sensitive": "G1"},
        {"text": "b", "label": 1, "sensitive": "G2"},
    ]
    assert adapter.adapt_batch(rows) == ["a", "b"]


def test_adapter_factory() -> None:
    assert get_adapter("plain_text_v1").adapter_id == "plain_text_v1"
    assert (
        get_adapter("hatexplain_post_tokens_v1").adapter_id
        == "hatexplain_post_tokens_v1"
    )
