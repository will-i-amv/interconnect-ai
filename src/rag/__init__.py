"""Hybrid RAG and tariff indexing pipeline for InterconnectAI."""

from typing import Any

from src.rag.chunker import HierarchicalTariffChunker
from src.rag.pdf_parser import (
    LayoutAwarePDFParser,
    MarkdownTariffParser,
    ParsedDocument,
    ParsedSection,
    detect_jurisdiction,
)

__all__ = [
    "HierarchicalTariffChunker",
    "LayoutAwarePDFParser",
    "MarkdownTariffParser",
    "ParsedDocument",
    "ParsedSection",
    "detect_jurisdiction",
    "ingest_tariffs",
]


def __getattr__(name: str) -> Any:
    """Lazy import for ingest_tariffs to prevent runtime warning when running as main."""
    if name == "ingest_tariffs":
        from src.rag.ingest import ingest_tariffs

        return ingest_tariffs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
