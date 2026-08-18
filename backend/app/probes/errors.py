"""Probe plugin errors (Phase 9)."""

from __future__ import annotations


class ProbeError(Exception):
    """Invalid probe output or probe execution failure (pipeline → FAILED)."""
