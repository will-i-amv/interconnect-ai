"""Hybrid RAG, vector store, and tariff indexing pipeline for InterconnectAI."""

from typing import Any

from src.rag.bm25 import BM25Index, tokenize_regulatory_text
from src.rag.chunker import HierarchicalTariffChunker
from src.rag.embeddings import (
    BaseEmbeddingService,
    DeterministicMockEmbeddingService,
    FastEmbedEmbeddingService,
    get_embedding_service,
)
from src.rag.pdf_parser import (
    LayoutAwarePDFParser,
    MarkdownTariffParser,
    ParsedDocument,
    ParsedSection,
    detect_jurisdiction,
)
from src.rag.retriever import HybridRetriever
from src.rag.vector_store import QdrantVectorStore

__all__ = [
    # Parsers & Chunkers
    "HierarchicalTariffChunker",
    "LayoutAwarePDFParser",
    "MarkdownTariffParser",
    "ParsedDocument",
    "ParsedSection",
    "detect_jurisdiction",
    "ingest_tariffs",
    # Embeddings
    "BaseEmbeddingService",
    "DeterministicMockEmbeddingService",
    "FastEmbedEmbeddingService",
    "get_embedding_service",
    # Storage & Indices
    "BM25Index",
    "QdrantVectorStore",
    "tokenize_regulatory_text",
    # Hybrid Retrieval
    "HybridRetriever",
]


def __getattr__(name: str) -> Any:
    """Lazy import for ingest_tariffs to prevent runtime warning when running as main."""
    if name == "ingest_tariffs":
        from src.rag.ingest import ingest_tariffs

        return ingest_tariffs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
