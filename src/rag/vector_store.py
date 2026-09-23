"""Qdrant vector store integration for regulatory tariff embeddings and semantic search."""

from __future__ import annotations

import contextlib
import logging
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from src.rag.embeddings import BaseEmbeddingService
from src.schemas.tariff import TariffChunk, TariffJurisdiction

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = "tariffs"
DEFAULT_VECTOR_SIZE = 384


def _chunk_id_to_uuid(chunk_id: str) -> str:
    """Convert arbitrary chunk string ID to a deterministic UUID for Qdrant point IDs."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


class QdrantVectorStore:
    """Wrapper around QdrantClient providing collection management, indexing, and vector search."""

    def __init__(
        self,
        url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        path: str | Path | None = None,
        location: str | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        """Initialize Qdrant client connection.

        If client is directly provided, it is used.
        Otherwise, precedence:
          1. Explicit url (e.g. 'http://localhost:6333')
          2. Explicit location (e.g. ':memory:')
          3. Explicit path (local disk storage)
          4. Host and port
          5. Default fallback to 'http://localhost:6333', with graceful
             fallback to ':memory:' on error.
        """
        if client is not None:
            self._client = client
        elif location is not None:
            self._client = QdrantClient(location=location)
        elif path is not None:
            self._client = QdrantClient(path=str(path))
        elif url is not None:
            self._client = QdrantClient(url=url)
        elif host is not None:
            self._client = QdrantClient(host=host, port=port or 6333)
        else:
            # Try remote localhost first, fallback to in-memory if unreachable
            try:
                test_client = QdrantClient(url="http://localhost:6333", timeout=2.0)
                test_client.get_collections()
                self._client = test_client
            except Exception as exc:
                logger.warning(
                    "Remote Qdrant at localhost:6333 unreachable (%s). Using in-memory store.",
                    exc,
                )
                self._client = QdrantClient(location=":memory:")

    @property
    def client(self) -> QdrantClient:
        """Return the underlying QdrantClient."""
        return self._client

    def ensure_collection(
        self,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        distance: models.Distance = models.Distance.COSINE,
        recreate: bool = False,
    ) -> None:
        """Ensure the specified collection exists with the desired vector configuration."""
        collection_exists = False
        try:
            collection_exists = self._client.collection_exists(collection_name)
        except Exception:
            # Fallback for environments where collection_exists is not available
            collections = [c.name for c in self._client.get_collections().collections]
            collection_exists = collection_name in collections

        if collection_exists and recreate:
            logger.info("Recreating collection '%s'", collection_name)
            self._client.delete_collection(collection_name)
            collection_exists = False

        if not collection_exists:
            logger.info(
                "Creating collection '%s' with vector size %d and distance %s",
                collection_name,
                vector_size,
                distance,
            )
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=distance,
                ),
            )

    def index_chunks(
        self,
        chunks: Sequence[TariffChunk],
        embedding_service: BaseEmbeddingService,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        batch_size: int = 64,
        recreate_collection: bool = False,
    ) -> int:
        """Embed and upsert tariff chunks into the Qdrant collection.

        Args:
            chunks: Collection of TariffChunk models to index.
            embedding_service: Service to generate embeddings for chunks.
            collection_name: Name of target collection.
            batch_size: Number of chunks to process and upsert per batch.
            recreate_collection: If True, recreates the collection before indexing.

        Returns:
            Total number of chunks successfully indexed.
        """
        if not chunks:
            return 0

        self.ensure_collection(
            collection_name=collection_name,
            vector_size=embedding_service.dimension,
            recreate=recreate_collection,
        )

        total_indexed = 0
        chunk_list = list(chunks)

        for i in range(0, len(chunk_list), batch_size):
            batch = chunk_list[i : i + batch_size]
            # Embed the context-prefixed content for maximum retrieval precision
            texts_to_embed = [chunk.content for chunk in batch]
            embeddings = embedding_service.embed_batch(texts_to_embed)

            points: list[models.PointStruct] = []
            for chunk, vector in zip(batch, embeddings, strict=True):
                point_id = _chunk_id_to_uuid(chunk.chunk_id)
                payload: dict[str, Any] = chunk.model_dump(mode="json")
                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    )
                )

            self._client.upsert(collection_name=collection_name, points=points)
            total_indexed += len(points)

        logger.info(
            "Successfully indexed %d chunks into collection '%s'",
            total_indexed,
            collection_name,
        )
        return total_indexed

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        jurisdiction: TariffJurisdiction | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> list[tuple[TariffChunk, float]]:
        """Perform dense vector cosine similarity search.

        Args:
            query_vector: Dense embedding vector for the query.
            top_k: Number of highest-scoring chunks to return.
            jurisdiction: Optional regulatory jurisdiction filter.
            collection_name: Name of collection to search.

        Returns:
            List of (TariffChunk, similarity_score) tuples ordered descending by score.
        """
        query_filter: models.Filter | None = None
        if jurisdiction is not None:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="jurisdiction",
                        match=models.MatchValue(value=jurisdiction.value),
                    )
                ]
            )

        # qdrant-client 1.9+ supports query_points
        results = self._client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        ).points

        scored_chunks: list[tuple[TariffChunk, float]] = []
        for scored_point in results:
            if scored_point.payload is not None:
                chunk = TariffChunk.model_validate(scored_point.payload)
                scored_chunks.append((chunk, float(scored_point.score)))

        return scored_chunks

    def count(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> int:
        """Return total number of points in the collection."""
        try:
            res = self._client.count(collection_name=collection_name)
            return res.count
        except Exception:
            return 0

    def delete_collection(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> bool:
        """Delete collection if it exists."""
        try:
            return bool(self._client.delete_collection(collection_name=collection_name))
        except Exception:
            return False

    def close(self) -> None:
        """Close Qdrant client connection."""
        with contextlib.suppress(Exception):
            self._client.close()
