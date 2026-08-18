"""Render canonical report_v1 JSON → HTML (Jinja2) → PDF (WeasyPrint).

The PDF is optional by design: WeasyPrint needs OS libraries (Pango/HarfBuzz)
that exist in the API Docker image but often not on dev hosts. Any PDF failure
degrades to JSON+HTML only (``pdf_uri=None``) with a logged skip.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import get_settings

logger = logging.getLogger("trustlens.reports")

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
REPORT_TEMPLATE = "report_v1.html"


@lru_cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def render_html(report_json: dict[str, Any]) -> str:
    """Project the canonical JSON document into the report_v1 HTML template."""
    return _environment().get_template(REPORT_TEMPLATE).render(report=report_json)


def render_pdf(html: str) -> bytes | None:
    """HTML → PDF bytes, or None when disabled or WeasyPrint is unavailable."""
    if not get_settings().report_pdf_enabled:
        logger.warning("report_pdf_skipped reason=disabled (REPORT_PDF_ENABLED=false)")
        return None
    try:
        # Lazy import: pulls in OS-level Pango/HarfBuzz; raises OSError on
        # hosts without them (e.g. Windows dev machines).
        import weasyprint
    except (ImportError, OSError) as exc:
        logger.warning("report_pdf_skipped reason=import_failed error=%s", exc)
        return None
    try:
        pdf = weasyprint.HTML(string=html).write_pdf()
    except Exception as exc:  # noqa: BLE001 — PDF must never break report generation
        logger.warning("report_pdf_skipped reason=render_failed error=%s", exc)
        return None
    return bytes(pdf)
