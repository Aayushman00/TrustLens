"""Shared ATX model-card markdown helpers (Phase 13–14).

Used by Explainability and Safety probes for heading split / body nontriviality.
"""

from __future__ import annotations

import re
from typing import Any

MIN_BODY_CHARS = 20

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_heading(text: str) -> str:
    cleaned = _PUNCT_RE.sub(" ", text.lower())
    return " ".join(cleaned.split())


def nontrivial(text: str | None) -> bool:
    return bool(text and len(text.strip()) >= MIN_BODY_CHARS)


def field_nontrivial(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return nontrivial(value)
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def split_card_sections(card_text: str) -> dict[str, str]:
    """Split markdown card into ``{heading_text: body}`` (first heading wins)."""
    if not card_text or not card_text.strip():
        return {}
    sections: dict[str, str] = {}
    current_heading: str | None = None
    body_lines: list[str] = []
    for line in card_text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            if current_heading is not None and current_heading not in sections:
                sections[current_heading] = "\n".join(body_lines).strip()
            current_heading = match.group(2).strip()
            body_lines = []
            continue
        if current_heading is not None:
            body_lines.append(line)
    if current_heading is not None and current_heading not in sections:
        sections[current_heading] = "\n".join(body_lines).strip()
    return sections


def match_aliases(
    normalized_heading: str,
    aliases_map: dict[str, tuple[str, ...]],
) -> str | None:
    """Prefer the longest alias match so 'bias and risks' ≠ bare 'bias'."""
    best_key: str | None = None
    best_len = -1
    for key, aliases in aliases_map.items():
        for alias in aliases:
            if normalized_heading == alias or alias in normalized_heading:
                if len(alias) > best_len:
                    best_key = key
                    best_len = len(alias)
    return best_key
