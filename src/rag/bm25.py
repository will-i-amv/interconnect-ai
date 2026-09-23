"""BM25 keyword search index tailored for regulatory tariffs and engineering standards."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from src.schemas.tariff import TariffChunk, TariffJurisdiction

logger = logging.getLogger(__name__)

# Basic English stop words that carry minimal distinguishing value in legal/tariff retrieval
STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "during",
        "each",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }
)


def tokenize_regulatory_text(text: str) -> list[str]:
    """Tokenize regulatory text while preserving numbers, percentages, and hyphenated terms.

    Preserves technical tokens like 'UL 1741-SB', '15%', 'Screen D', '2.0s', 'IEEE-1547'.
    """
    raw_tokens = re.findall(r"[a-zA-Z0-9]+(?:[-_.][a-zA-Z0-9]+)*%?", text.lower())
    filtered = [t for t in raw_tokens if t not in STOP_WORDS and len(t) >= 1]
    return filtered


class BM25Index:
    """Keyword search index based on BM25Okapi with domain tokenization."""

    def __init__(
        self,
        chunks: Sequence[TariffChunk] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
        epsilon: float = 0.25,
    ) -> None:
        """Initialize BM25 index with tuning parameters."""
        self._k1 = k1
        self._b = b
        self._epsilon = epsilon
        self._chunks: list[TariffChunk] = []
        self._corpus: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

        if chunks:
            self.index_chunks(chunks)

    @property
    def chunks(self) -> list[TariffChunk]:
        """Return indexed chunks."""
        return self._chunks

    def __len__(self) -> int:
        """Return number of indexed chunks."""
        return len(self._chunks)

    def index_chunks(self, chunks: Sequence[TariffChunk]) -> int:
        """Index a collection of TariffChunks into the BM25 model."""
        self._chunks = list(chunks)
        self._corpus = [tokenize_regulatory_text(c.content) for c in self._chunks]
        if self._corpus:
            self._bm25 = BM25Okapi(
                self._corpus,
                k1=self._k1,
                b=self._b,
                epsilon=self._epsilon,
            )
        else:
            self._bm25 = None
        return len(self._chunks)

    def search(
        self,
        query: str,
        top_k: int = 10,
        jurisdiction: TariffJurisdiction | None = None,
    ) -> list[tuple[TariffChunk, float]]:
        """Search the BM25 index with a keyword query.

        Args:
            query: User or screening query string.
            top_k: Maximum number of matches to return.
            jurisdiction: Optional jurisdiction filter.

        Returns:
            List of (TariffChunk, score) tuples sorted descending by score.
        """
        if not self._bm25 or not self._chunks:
            return []

        tokenized_query = tokenize_regulatory_text(query)
        if not tokenized_query:
            return []

        scores = self._bm25.get_scores(tokenized_query)
        # Clip negative scores to 0.0
        scores = np.maximum(scores, 0.0)

        # Apply jurisdiction filter if present
        candidate_indices: list[int] = []
        for idx, chunk in enumerate(self._chunks):
            if jurisdiction is not None and chunk.jurisdiction != jurisdiction:
                continue
            if scores[idx] > 0.0:
                candidate_indices.append(idx)

        # Sort candidate indices by score descending
        candidate_indices.sort(key=lambda idx: float(scores[idx]), reverse=True)
        top_indices = candidate_indices[:top_k]

        return [(self._chunks[i], float(scores[i])) for i in top_indices]

    def save(self, file_path: Path | str) -> None:
        """Serialize chunks and tokenized corpus to a JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "k1": self._k1,
            "b": self._b,
            "epsilon": self._epsilon,
            "chunks": [c.model_dump(mode="json") for c in self._chunks],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved BM25 index with %d chunks to %s", len(self._chunks), path)

    @classmethod
    def load(cls, file_path: Path | str) -> BM25Index:
        """Deserialize and re-index a BM25Index from a saved JSON file."""
        path = Path(file_path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        chunks = [TariffChunk.model_validate(c) for c in data.get("chunks", [])]
        instance = cls(
            chunks=chunks,
            k1=data.get("k1", 1.5),
            b=data.get("b", 0.75),
            epsilon=data.get("epsilon", 0.25),
        )
        logger.info("Loaded BM25 index with %d chunks from %s", len(chunks), path)
        return instance
