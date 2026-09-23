"""Automated tests for Qdrant vector store, BM25 indexing, and Hybrid Retriever (T-105)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.rag.bm25 import BM25Index, tokenize_regulatory_text
from src.rag.embeddings import (
    DeterministicMockEmbeddingService,
    FastEmbedEmbeddingService,
    get_embedding_service,
)
from src.rag.ingest import ingest_tariffs
from src.rag.retriever import HybridRetriever
from src.rag.vector_store import QdrantVectorStore
from src.schemas.tariff import RetrievedChunk, TariffChunk, TariffJurisdiction


@pytest.fixture
def mock_embedding_service() -> DeterministicMockEmbeddingService:
    """Fixture providing a deterministic 384-dimensional mock embedding service."""
    return DeterministicMockEmbeddingService(dimension=384)


@pytest.fixture
def sample_chunks() -> list[TariffChunk]:
    """Sample realistic regulatory chunks for fast unit tests."""
    return [
        TariffChunk(
            chunk_id="TEST_RULE21_SCREEN_D",
            document_title="Electric Rule 21",
            jurisdiction=TariffJurisdiction.CA_RULE_21,
            source_filename="rule21.pdf",
            page_number=14,
            section_hierarchy=["Rule 21", "Section D", "Screen D"],
            section_title="Screen D - 15% Penetration",
            content=(
                "[Document: Electric Rule 21 | Jurisdiction: CA_RULE_21 | "
                "Path: Rule 21 > Section D > Screen D | Page: 14]\n"
                "Screen D: 15% Feeder Penetration Screen. Aggregate generation on the line section "
                "must not exceed 15% of annual peak load."
            ),
            raw_text=(
                "Screen D: 15% Feeder Penetration Screen. Aggregate generation on the "
                "line section must not exceed 15% of annual peak load."
            ),
            char_count=180,
            word_count=28,
            metadata={"screen_id": "D", "threshold_pct": 15.0},
        ),
        TariffChunk(
            chunk_id="TEST_RULE21_SCREEN_B",
            document_title="Electric Rule 21",
            jurisdiction=TariffJurisdiction.CA_RULE_21,
            source_filename="rule21.pdf",
            page_number=8,
            section_hierarchy=["Rule 21", "Section D", "Screen B"],
            section_title="Screen B - Certified Equipment",
            content=(
                "[Document: Electric Rule 21 | Jurisdiction: CA_RULE_21 | "
                "Path: Rule 21 > Section D > Screen B | Page: 8]\n"
                "Screen B: Certified Inverter Screen. The inverter must be certified under "
                "UL 1741-SB and comply with IEEE 1547-2018 interoperability requirements."
            ),
            raw_text=(
                "Screen B: Certified Inverter Screen. The inverter must be certified under "
                "UL 1741-SB and comply with IEEE 1547-2018 interoperability requirements."
            ),
            char_count=195,
            word_count=27,
            metadata={"screen_id": "B", "certification": "UL 1741-SB"},
        ),
        TariffChunk(
            chunk_id="TEST_IEEE1547_ANTI_ISLANDING",
            document_title="IEEE Standard 1547-2018",
            jurisdiction=TariffJurisdiction.IEEE_1547,
            source_filename="ieee1547.pdf",
            page_number=22,
            section_hierarchy=["IEEE 1547-2018", "Clause 8", "Clause 8.1"],
            section_title="Clause 8.1 - Anti-Islanding Protection",
            content=(
                "[Document: IEEE Standard 1547-2018 | Jurisdiction: IEEE_1547 | "
                "Path: IEEE 1547-2018 > Clause 8 > Clause 8.1 | Page: 22]\n"
                "Clause 8.1: Unintentional islanding protection. The DER shall detect an "
                "unintentional island and cease to energize the area EPS within 2.0s of formation."
            ),
            raw_text=(
                "Clause 8.1: Unintentional islanding protection. The DER shall detect an "
                "unintentional island and cease to energize the area EPS within 2.0s of formation."
            ),
            char_count=210,
            word_count=30,
            metadata={"clause": "8.1", "trip_time_seconds": 2.0},
        ),
    ]


def test_deterministic_mock_embedding_service(
    mock_embedding_service: DeterministicMockEmbeddingService,
) -> None:
    """Verify mock embedding produces expected dimension and unit norm."""
    vec = mock_embedding_service.embed_text("Screen D 15% penetration")
    assert len(vec) == 384
    norm = np.linalg.norm(vec)
    assert pytest.approx(norm, rel=1e-4) == 1.0

    # Test determinism: same text yields same vector
    vec2 = mock_embedding_service.embed_text("Screen D 15% penetration")
    assert vec == vec2

    # Different text yields different vector
    vec3 = mock_embedding_service.embed_text("UL 1741-SB certified inverter")
    assert vec != vec3

    # Batch embedding
    batch = mock_embedding_service.embed_batch(["text1", "text2"])
    assert len(batch) == 2
    assert len(batch[0]) == 384


def test_qdrant_vector_store_in_memory(
    sample_chunks: list[TariffChunk],
    mock_embedding_service: DeterministicMockEmbeddingService,
) -> None:
    """Verify in-memory QdrantVectorStore indexing and search."""
    store = QdrantVectorStore(location=":memory:")
    count = store.index_chunks(
        chunks=sample_chunks,
        embedding_service=mock_embedding_service,
        collection_name="test_tariffs",
    )
    assert count == 3
    assert store.count("test_tariffs") == 3

    # Search with embedding of Screen D
    query_vec = mock_embedding_service.embed_text(sample_chunks[0].content)
    results = store.search(
        query_vector=query_vec,
        top_k=2,
        collection_name="test_tariffs",
    )
    assert len(results) == 2
    best_chunk, score = results[0]
    assert best_chunk.chunk_id == "TEST_RULE21_SCREEN_D"
    assert pytest.approx(score, rel=1e-3) == 1.0


def test_qdrant_remote_connection_if_available(
    sample_chunks: list[TariffChunk],
    mock_embedding_service: DeterministicMockEmbeddingService,
) -> None:
    """Test remote Qdrant Docker container if reachable, with cleanup."""
    try:
        store = QdrantVectorStore(url="http://localhost:6333")
        # Probe remote health
        store.client.get_collections()
    except Exception:
        pytest.skip("Remote Qdrant service not reachable at http://localhost:6333")

    collection_name = "test_remote_integration"
    try:
        indexed = store.index_chunks(
            chunks=sample_chunks,
            embedding_service=mock_embedding_service,
            collection_name=collection_name,
            recreate_collection=True,
        )
        assert indexed == 3
        assert store.count(collection_name) == 3

        query_vec = mock_embedding_service.embed_text(sample_chunks[1].content)
        results = store.search(
            query_vector=query_vec,
            top_k=1,
            collection_name=collection_name,
        )
        assert len(results) == 1
        assert results[0][0].chunk_id == "TEST_RULE21_SCREEN_B"
    finally:
        store.delete_collection(collection_name)


def test_bm25_tokenization_and_keyword_search(sample_chunks: list[TariffChunk]) -> None:
    """Verify domain tokenization and exact keyword matching."""
    tokens = tokenize_regulatory_text("Screen D: 15% penetration under UL 1741-SB and 2.0s trip!")
    assert "screen" in tokens
    assert "15%" in tokens
    assert "ul" in tokens
    assert "1741-sb" in tokens
    assert "2.0s" in tokens
    assert "and" not in tokens  # Stop word removed

    index = BM25Index(sample_chunks)
    assert len(index) == 3

    # Query for 15% penetration
    results = index.search("15% penetration feeder peak load", top_k=2)
    assert len(results) >= 1
    assert results[0][0].chunk_id == "TEST_RULE21_SCREEN_D"
    assert results[0][1] > 0.0

    # Query for UL 1741-SB
    results_ul = index.search("UL 1741-SB certified inverter", top_k=1)
    assert len(results_ul) == 1
    assert results_ul[0][0].chunk_id == "TEST_RULE21_SCREEN_B"

    # Query for anti-islanding 2.0s
    results_island = index.search("anti-islanding 2.0s unintentional island", top_k=1)
    assert len(results_island) == 1
    assert results_island[0][0].chunk_id == "TEST_IEEE1547_ANTI_ISLANDING"


def test_bm25_persistence(sample_chunks: list[TariffChunk], tmp_path: Path) -> None:
    """Verify BM25 index save and load round-trip."""
    index = BM25Index(sample_chunks)
    save_file = tmp_path / "bm25_index.json"
    index.save(save_file)
    assert save_file.exists()

    loaded_index = BM25Index.load(save_file)
    assert len(loaded_index) == 3
    results = loaded_index.search("15% penetration", top_k=1)
    assert len(results) == 1
    assert results[0][0].chunk_id == "TEST_RULE21_SCREEN_D"


def test_hybrid_retriever_reciprocal_rank_fusion(
    sample_chunks: list[TariffChunk],
    mock_embedding_service: DeterministicMockEmbeddingService,
) -> None:
    """Verify RRF rank calculation and combined scoring."""
    store = QdrantVectorStore(location=":memory:")
    bm25 = BM25Index()

    retriever = HybridRetriever(
        vector_store=store,
        bm25_index=bm25,
        embedding_service=mock_embedding_service,
        rrf_k=60,
        collection_name="test_rrf",
    )

    retriever.index(sample_chunks)

    # Search for Screen B
    retrieved = retriever.retrieve(
        query="UL 1741-SB certified smart inverter",
        top_k=2,
    )
    assert len(retrieved) >= 1
    top_hit = retrieved[0]
    assert isinstance(top_hit, RetrievedChunk)
    assert top_hit.chunk.chunk_id == "TEST_RULE21_SCREEN_B"
    assert top_hit.fused_score > 0
    assert top_hit.bm25_rank == 1

    # Verify RRF formula for top hit:
    # If ranked in both dense (rank r_d) and bm25 (rank r_b), score = 1/(60+r_d) + 1/(60+r_b)
    expected_score = 0.0
    if top_hit.dense_rank is not None:
        expected_score += 1.0 / (60 + top_hit.dense_rank)
    if top_hit.bm25_rank is not None:
        expected_score += 1.0 / (60 + top_hit.bm25_rank)
    assert pytest.approx(top_hit.fused_score, rel=1e-3) == expected_score


def test_hybrid_retriever_jurisdiction_filter(
    sample_chunks: list[TariffChunk],
    mock_embedding_service: DeterministicMockEmbeddingService,
) -> None:
    """Verify filtering by jurisdiction restricts results to that regulatory body."""
    store = QdrantVectorStore(location=":memory:")
    bm25 = BM25Index()
    retriever = HybridRetriever(
        vector_store=store,
        bm25_index=bm25,
        embedding_service=mock_embedding_service,
        collection_name="test_jurisdiction_filter",
    )
    retriever.index(sample_chunks)

    # Filter for IEEE_1547 only
    results_ieee = retriever.retrieve(
        query="interconnection standard requirements",
        top_k=10,
        jurisdiction=TariffJurisdiction.IEEE_1547,
    )
    assert len(results_ieee) >= 1
    for r in results_ieee:
        assert r.chunk.jurisdiction == TariffJurisdiction.IEEE_1547

    # Filter for CA_RULE_21 only
    results_r21 = retriever.retrieve(
        query="protection requirements",
        top_k=10,
        jurisdiction=TariffJurisdiction.CA_RULE_21,
    )
    assert len(results_r21) >= 1
    for r in results_r21:
        assert r.chunk.jurisdiction == TariffJurisdiction.CA_RULE_21


def test_hybrid_retriever_end_to_end_with_ingested_tariffs(tmp_path: Path) -> None:
    """Test full pipeline: ingest benchmark tariffs, index, and retrieve."""
    tariff_dir = Path("dataset/tariffs")
    if not tariff_dir.exists():
        pytest.skip("dataset/tariffs directory not found")

    # Ingest actual regulatory tariffs
    chunks, summary = ingest_tariffs(tariff_dir=tariff_dir, dry_run=True)
    assert len(chunks) > 0
    assert summary.total_chunks > 0

    store = QdrantVectorStore(location=":memory:")
    bm25 = BM25Index()
    mock_service = get_embedding_service(use_mock=True)

    retriever = HybridRetriever(
        vector_store=store,
        bm25_index=bm25,
        embedding_service=mock_service,
        collection_name="benchmark_tariffs",
    )
    retriever.index(chunks)

    # Query 1: 15% penetration
    r1 = retriever.retrieve("15% penetration screen annual peak load", top_k=3)
    assert len(r1) > 0
    assert any("Screen D" in hit.chunk.section_title or "15%" in hit.chunk.content for hit in r1)

    # Query 2: UL 1741-SB certification
    r2 = retriever.retrieve("UL 1741-SB certified inverter equipment", top_k=3)
    assert len(r2) > 0
    assert any("1741" in hit.chunk.content for hit in r2)


def test_fastembed_service_initialization() -> None:
    """Verify FastEmbedEmbeddingService can be instantiated and probe dimensions."""
    service = FastEmbedEmbeddingService(model_name="BAAI/bge-small-en-v1.5")
    # Lazy dimension is 384
    assert service.dimension == 384
