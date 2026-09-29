"""Embedded multi-page vector PDF viewer component for Streamlit using PyMuPDF."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf
import streamlit as st

logger = logging.getLogger(__name__)


def get_pdf_page_count(pdf_path: str | Path) -> int:
    """Return the total number of pages in a PDF file."""
    p = Path(pdf_path)
    if not p.is_file():
        return 0
    try:
        with pymupdf.open(p) as doc:
            return len(doc)
    except Exception as exc:
        logger.warning("Failed to inspect PDF page count for %s: %s", p, exc)
        return 0


def render_pdf_page_to_bytes(pdf_path: str | Path, page_index: int = 0, dpi: int = 150) -> bytes:
    """Rasterize a specified PDF page to PNG image bytes.

    Args:
        pdf_path: Path to the target PDF document.
        page_index: 0-based page index.
        dpi: Resolution for rasterization (default: 150 dpi).

    Returns:
        PNG image bytes of the rendered page.
    """
    p = Path(pdf_path)
    if not p.is_file():
        raise FileNotFoundError(f"PDF document not found: {p}")

    with pymupdf.open(p) as doc:
        total = len(doc)
        if total == 0:
            raise ValueError(f"PDF document has 0 pages: {p}")
        clamped_idx = max(0, min(page_index, total - 1))
        page = doc.load_page(clamped_idx)
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")


def render_pdf_viewer(
    files: dict[str, str],
    key_prefix: str = "pdf_viewer",
) -> None:
    """Render an interactive multi-page PDF viewer with document selection and controls."""
    valid_files: dict[str, str] = {
        label: path for label, path in files.items() if path and Path(path).is_file()
    }

    if not valid_files:
        st.warning("No PDF documents available for this application package.")
        return

    # Document Selection Bar
    doc_labels = list(valid_files.keys())
    selected_doc_label = st.selectbox(
        "Select Document to Inspect",
        options=doc_labels,
        key=f"{key_prefix}_doc_select",
    )

    active_path = Path(valid_files[selected_doc_label])
    page_count = get_pdf_page_count(active_path)

    if page_count == 0:
        st.error(f"Selected document '{active_path.name}' cannot be rendered.")
        return

    # Page Navigation and Zoom Bar
    nav_col1, nav_col2, nav_col3 = st.columns([2, 3, 2])

    page_state_key = f"{key_prefix}_page_{active_path.stem}"
    if page_state_key not in st.session_state:
        st.session_state[page_state_key] = 0

    current_page = st.session_state[page_state_key]

    with nav_col1:
        if st.button("⏮️ Prev", key=f"{key_prefix}_prev", disabled=current_page <= 0):
            st.session_state[page_state_key] = max(0, current_page - 1)
            st.rerun()

    with nav_col2:
        st.markdown(
            f"<div style='text-align: center; font-weight: 600; padding-top: 6px; "
            f"color: #cbd5e1; font-size: 0.88rem;'>"
            f"Page {current_page + 1} of {page_count}"
            f"</div>",
            unsafe_allow_html=True,
        )

    with nav_col3:
        if st.button(
            "Next ⏭️",
            key=f"{key_prefix}_next",
            disabled=current_page >= page_count - 1,
        ):
            st.session_state[page_state_key] = min(page_count - 1, current_page + 1)
            st.rerun()

    # Render Document Page
    try:
        page_bytes = render_pdf_page_to_bytes(
            active_path,
            page_index=st.session_state[page_state_key],
            dpi=150,
        )
        st.image(page_bytes, use_container_width=True)
    except Exception as exc:
        st.error(f"Error rendering PDF page: {exc}")

    # Document Actions: Download original vector PDF
    try:
        raw_pdf_bytes = active_path.read_bytes()
        st.download_button(
            label=f"⬇️ Download {active_path.name}",
            data=raw_pdf_bytes,
            file_name=active_path.name,
            mime="application/pdf",
            key=f"{key_prefix}_download_{active_path.stem}",
            use_container_width=True,
        )
    except Exception as exc:
        logger.debug("Failed to read raw PDF for download: %s", exc)
