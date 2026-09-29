"""Automated tests for split-screen review console and PDF viewer components (T-113)."""

from __future__ import annotations

from pathlib import Path

import pytest

from frontend.components.pdf_viewer import (
    get_pdf_page_count,
    render_pdf_page_to_bytes,
)
from src.utils.dataset import load_application


def test_pdf_page_count() -> None:
    """Verify get_pdf_page_count returns valid page numbers for application PDFs."""
    pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")
    sld_path = pkg["single_line_diagram_path"]

    count = get_pdf_page_count(sld_path)
    assert count >= 1

    # Nonexistent path returns 0
    assert get_pdf_page_count("/tmp/nonexistent_document_123.pdf") == 0


def test_pdf_page_rasterization() -> None:
    """Verify PDF page rasterizes to valid PNG image bytes."""
    pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")
    sld_path = pkg["single_line_diagram_path"]

    img_bytes = render_pdf_page_to_bytes(sld_path, page_index=0, dpi=100)
    assert isinstance(img_bytes, bytes)
    assert len(img_bytes) > 1000
    # Standard PNG header signature
    assert img_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_pdf_page_rasterization_clamping() -> None:
    """Verify page_index is clamped safely within available bounds."""
    pkg = load_application("APP-001-PASS-ROOFTOP-SOLAR")
    sld_path = pkg["single_line_diagram_path"]

    # Request page 50 on a 1-page document; should clamp to page 0 without error
    img_bytes = render_pdf_page_to_bytes(sld_path, page_index=50, dpi=80)
    assert img_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_pdf_rasterization_missing_file_raises() -> None:
    """Verify FileNotFoundError is raised when target PDF does not exist."""
    with pytest.raises(FileNotFoundError):
        render_pdf_page_to_bytes(Path("/tmp/missing_file_xyz.pdf"))
