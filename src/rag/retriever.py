"""Hybrid retriever combining dense semantic search and BM25 sparse keyword search via RRF."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from src.rag.bm25 import BM25Index
from src.rag.embeddings import BaseEmbeddingService
from src.rag.vector_store import QdrantVectorStore
from src.schemas.tariff import RetrievedChunk, TariffChunk, TariffJurisdiction

logger = logging.getLogger(__name__)

DEFAULT_RRF_K = 60
DEFAULT_DENSE_WEIGHT = 1.0
DEFAULT_BM25_WEIGHT = 1.0


class HybridRetriever:
    """Hybrid search retriever combining Qdrant dense vector search with BM25 keyword search.

    Combines candidate result lists using Reciprocal Rank Fusion (RRF):
        RRF_Score(d) = sum_{m in {dense, bm25}} (weight_m / (k + rank_m(d)))
    """

    def __init__(
        self,
        vector_store: QdrantVectorStore,
        bm25_index: BM25Index,
        embedding_service: BaseEmbeddingService,
        rrf_k: int = DEFAULT_RRF_K,
        dense_weight: float = DEFAULT_DENSE_WEIGHT,
        bm25_weight: float = DEFAULT_BM25_WEIGHT,
        collection_name: str = "tariffs",
    ) -> None:
        """Initialize the hybrid retriever.

        Args:
            vector_store: Initialized QdrantVectorStore instance.
            bm25_index: Initialized BM25Index instance.
            embedding_service: Service to generate query embeddings.
            rrf_k: RRF smoothing constant (default: 60).
            dense_weight: Weight multiplier for dense search ranks (default: 1.0).
            bm25_weight: Weight multiplier for BM25 search ranks (default: 1.0).
            collection_name: Qdrant collection name to search.
        """
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.embedding_service = embedding_service
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight
        self.collection_name = collection_name

    def index(
        self,
        chunks: Sequence[TariffChunk],
        recreate_collection: bool = False,
    ) -> int:
        """Index chunks into both Qdrant vector store and BM25 index.

        Args:
            chunks: Collection of TariffChunk objects to index.
            recreate_collection: If True, recreates the Qdrant collection.

        Returns:
            Number of indexed chunks.
        """
        chunk_list = list(chunks)
        # Index in Qdrant
        self.vector_store.index_chunks(
            chunks=chunk_list,
            embedding_service=self.embedding_service,
            collection_name=self.collection_name,
            recreate_collection=recreate_collection,
        )
        # Index in BM25
        self.bm25_index.index_chunks(chunk_list)
        return len(chunk_list)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        jurisdiction: TariffJurisdiction | None = None,
        dense_top_k: int = 20,
        bm25_top_k: int = 20,
    ) -> list[RetrievedChunk]:
        """Perform hybrid retrieval using Reciprocal Rank Fusion.

        Args:
            query: User or screening evaluation query text.
            top_k: Number of fused results to return.
            jurisdiction: Optional regulatory jurisdiction filter.
            dense_top_k: Number of candidates to retrieve from dense vector search.
            bm25_top_k: Number of candidates to retrieve from BM25 sparse search.

        Returns:
            Ranked list of RetrievedChunk models sorted by fused_score descending.
        """
        if not query.strip():
            return []

        # 1. Dense retrieval
        query_vector = self.embedding_service.embed_text(query)
        dense_results = self.vector_store.search(
            query_vector=query_vector,
            top_k=dense_top_k,
            jurisdiction=jurisdiction,
            collection_name=self.collection_name,
        )

        # 2. BM25 sparse retrieval
        bm25_results = self.bm25_index.search(
            query=query,
            top_k=bm25_top_k,
            jurisdiction=jurisdiction,
        )

        # Map by chunk_id -> metadata
        candidates: dict[str, TariffChunk] = {}
        dense_ranks: dict[str, int] = {}
        dense_scores: dict[str, float] = {}
        bm25_ranks: dict[str, int] = {}
        bm25_scores: dict[str, float] = {}

        for rank_idx, (chunk, score) in enumerate(dense_results, start=1):
            candidates[chunk.chunk_id] = chunk
            dense_ranks[chunk.chunk_id] = rank_idx
            dense_scores[chunk.chunk_id] = score

        for rank_idx, (chunk, score) in enumerate(bm25_results, start=1):
            candidates[chunk.chunk_id] = chunk
            bm25_ranks[chunk.chunk_id] = rank_idx
            bm25_scores[chunk.chunk_id] = score

        # 3. Reciprocal Rank Fusion (RRF)
        fused_items: list[
            tuple[float, TariffChunk, int | None, float | None, int | None, float | None]
        ] = []

        for chunk_id, chunk in candidates.items():
            fused_score = 0.0

            d_rank = dense_ranks.get(chunk_id)
            d_score = dense_scores.get(chunk_id)
            if d_rank is not None:
                fused_score += self.dense_weight * (1.0 / (self.rrf_k + d_rank))

            b_rank = bm25_ranks.get(chunk_id)
            b_score = bm25_scores.get(chunk_id)
            if b_rank is not None:
                fused_score += self.bm25_weight * (1.0 / (self.rrf_k + b_rank))

            fused_items.append((fused_score, chunk, d_rank, d_score, b_rank, b_score))

        # Sort descending by fused score
        fused_items.sort(key=lambda item: item[0], reverse=True)

        top_fused = fused_items[:top_k]

        return [
            RetrievedChunk(
                chunk=chunk,
                fused_score=round(fused_score, 6),
                dense_rank=d_rank,
                dense_score=round(d_score, 6) if d_score is not None else None,
                bm25_rank=b_rank,
                bm25_score=round(b_score, 4) if b_score is not None else None,
            )
            for fused_score, chunk, d_rank, d_score, b_rank, b_score in top_fused
        ]
