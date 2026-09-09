"""Model input adapters — dataset row → InferenceBackend inputs."""

from app.inference.adapters.base import ModelInputAdapter
from app.inference.adapters.registry import get_adapter, register_adapter

__all__ = ["ModelInputAdapter", "get_adapter", "register_adapter"]
