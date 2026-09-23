"""Device-agnostic embedding services for dense vector search."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

import numpy as np


class BaseEmbeddingService(ABC):
    """Abstract base class for dense text embedding generation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality produced by this embedding model."""
        ...

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embed a single query or text passage into a normalized vector."""
        ...

    @abstractmethod
    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a collection of text passages in batch."""
        ...


class FastEmbedEmbeddingService(BaseEmbeddingService):
    """Production embedding service powered by FastEmbed and ONNX Runtime.

    Features device-agnostic runtime fallback (CUDA/CPU) and lazy model initialization.
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    DEFAULT_DIMENSION = 384

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: str | None = None,
        threads: int | None = None,
        providers: list[str] | None = None,
    ) -> None:
        """Initialize FastEmbed embedding model configuration.

        Args:
            model_name: FastEmbed supported model name (defaults to bge-small-en-v1.5).
            cache_dir: Optional directory to store downloaded ONNX models.
            threads: Optional thread count for ONNX runtime inference.
            providers: Optional ONNX execution providers
                (e.g. ['CUDAExecutionProvider', 'CPUExecutionProvider']).
        """
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._threads = threads
        self._providers = providers
        self._model: Any = None
        self._dim = self.DEFAULT_DIMENSION

    def _get_model(self) -> Any:
        """Lazy-load the underlying FastEmbed TextEmbedding instance."""
        if self._model is None:
            from fastembed import TextEmbedding

            kwargs: dict[str, Any] = {"model_name": self._model_name}
            if self._cache_dir:
                kwargs["cache_dir"] = self._cache_dir
            if self._threads:
                kwargs["threads"] = self._threads
            if self._providers:
                kwargs["providers"] = self._providers

            self._model = TextEmbedding(**kwargs)
            # Discover dimension from a sample probe if needed
            probe = next(self._model.embed(["probe"]))
            self._dim = len(probe)
        return self._model

    @property
    def dimension(self) -> int:
        """Vector dimensionality."""
        return self._dim

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        model = self._get_model()
        vectors = list(model.embed([text]))
        norm = float(np.linalg.norm(vectors[0]))
        if norm > 0:
            return (vectors[0] / norm).tolist()
        return vectors[0].tolist()

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of text strings into normalized vectors."""
        if not texts:
            return []
        model = self._get_model()
        vectors = list(model.embed(list(texts)))
        normalized_results: list[list[float]] = []
        for vec in vectors:
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                normalized_results.append((vec / norm).tolist())
            else:
                normalized_results.append(vec.tolist())
        return normalized_results


class DeterministicMockEmbeddingService(BaseEmbeddingService):
    """Fast, deterministic pseudo-random embedding service for testing and CI.

    Produces unit-normalized vectors of a fixed dimensionality using SHA-256 seeding,
    ensuring identical inputs generate identical embeddings without network access or ONNX weights.
    """

    def __init__(self, dimension: int = 384) -> None:
        """Initialize mock embedding service with specific dimensionality."""
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        """Vector dimensionality."""
        return self._dimension

    def _generate_vector(self, text: str) -> list[float]:
        """Generate a deterministic unit-normalized vector using feature hashing."""
        from src.rag.bm25 import tokenize_regulatory_text

        tokens = tokenize_regulatory_text(text)
        if not tokens:
            vec = np.zeros(self._dimension, dtype=np.float32)
            vec[0] = 1.0
            return vec.tolist()

        vec = np.zeros(self._dimension, dtype=np.float32)
        for token in tokens:
            h = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "big") % self._dimension
            sign = 1.0 if (h[4] % 2 == 0) else -1.0
            vec[idx] += sign

        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_text(self, text: str) -> list[float]:
        """Embed single text string deterministically."""
        return self._generate_vector(text)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed batch of text strings deterministically."""
        return [self._generate_vector(t) for t in texts]


def get_embedding_service(
    model_name: str | None = None,
    use_mock: bool = False,
    dimension: int = 384,
) -> BaseEmbeddingService:
    """Factory helper to obtain an embedding service.

    Args:
        model_name: Name of model for FastEmbed (defaults to BAAI/bge-small-en-v1.5).
        use_mock: If True, returns DeterministicMockEmbeddingService (ideal for testing).
        dimension: Dimensionality (used if mock).

    Returns:
        Instance of BaseEmbeddingService.
    """
    if use_mock:
        return DeterministicMockEmbeddingService(dimension=dimension)
    return FastEmbedEmbeddingService(
        model_name=model_name or FastEmbedEmbeddingService.DEFAULT_MODEL
    )
