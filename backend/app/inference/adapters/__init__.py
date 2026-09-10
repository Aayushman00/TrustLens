"""Model input adapters — dataset row -> InferenceBackend inputs.

NOT to be confused with the unrelated app.adapters (Hugging Face Hub
metadata resolution, used at model import time — never loads weights).
This module converts one already-loaded-model-ready dataset row into text
for a probe's inference call.
"""

from app.inference.adapters.base import ModelInputAdapter
from app.inference.adapters.registry import get_adapter, register_adapter

__all__ = ["ModelInputAdapter", "get_adapter", "register_adapter"]
