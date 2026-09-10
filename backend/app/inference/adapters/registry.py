"""Adapter factory keyed by ``adapter_id``."""

from __future__ import annotations

from app.inference.adapters.base import ModelInputAdapter
from app.inference.adapters.plain_text import PlainTextAdapter

_REGISTRY: dict[str, ModelInputAdapter] = {
    PlainTextAdapter.adapter_id: PlainTextAdapter(),
}


def get_adapter(adapter_id: str) -> ModelInputAdapter:
    try:
        return _REGISTRY[adapter_id]
    except KeyError as exc:
        raise KeyError(f"unknown input adapter_id={adapter_id!r}") from exc


def register_adapter(adapter: ModelInputAdapter) -> None:
    _REGISTRY[adapter.adapter_id] = adapter
