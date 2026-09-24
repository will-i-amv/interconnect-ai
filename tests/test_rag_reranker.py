"""Automated tests for cross-encoder reranker and citation tracking (T-106)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.rag.bm25 import BM25Index
from src.rag.embeddings import DeterministicMockEmbeddingService
from src.rag.ingest import ingest_tariffs
from src.rag.reranker import (
    BGEReranker,
    DeterministicMockReranker,
    build_citation,
    get_reranker,
)
from src.rag.retriever import HybridRetriever
from src.rag.vector_store import QdrantVectorStore
from src.schemas.tariff import (
    RerankedResult,
    TariffChunk,
    TariffCitation,
    TariffJurisdiction,
)


@pytest.fixture
def sample_tariff_chunks() -> list[TariffChunk]:
    """Sample realistic regulatory chunks for unit tests."""
    return [
        TariffChunk(
            chunk_id="TEST_RULE21_SCREEN_D",
            document_title="Electric Rule 21",
            jurisdiction=TariffJurisdiction.CA_RULE_21,
            source_filename="ca_rule_21_extract.pdf",
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
            source_filename="ca_rule_21_extract.pdf",
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
            source_filename="ieee_1547_2018_extract.pdf",
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


def test_build_citation_fields_and_page_numbers(
    sample_tariff_chunks: list[TariffChunk],
) -> None:
    """Verify build_citation creates a valid TariffCitation with exact page numbers."""
    chunk_r21 = sample_tariff_chunks[0]
    citation_r21 = build_citation(chunk=chunk_r21, score=0.952)

    assert isinstance(citation_r21, TariffCitation)
    assert citation_r21.page_number == 14
    assert citation_r21.jurisdiction == TariffJurisdiction.CA_RULE_21
    assert citation_r21.citation_label == "[CA Rule 21 § Screen D - 15% Penetration, p. 14]"
    assert "Screen D: 15% Feeder Penetration Screen" in citation_r21.exact_quote
    assert citation_r21.relevance_score == 0.952
    assert citation_r21.chunk_id == "TEST_RULE21_SCREEN_D"

    # Verify IEEE 1547 label formatting
    chunk_ieee = sample_tariff_chunks[2]
    citation_ieee = build_citation(chunk=chunk_ieee, score=0.88)
    assert citation_ieee.page_number == 22
    assert citation_ieee.jurisdiction == TariffJurisdiction.IEEE_1547
    assert citation_ieee.citation_label == (
        "[IEEE 1547-2018 § Clause 8.1 - Anti-Islanding Protection, p. 22]"
    )


def test_deterministic_mock_reranker_scoring(
    sample_tariff_chunks: list[TariffChunk],
) -> None:
    """Verify DeterministicMockReranker correctly ranks relevant chunks."""
    reranker = DeterministicMockReranker()

    # Query targeting Screen D
    results_d = reranker.rerank(
        query="feeder penetration threshold 15 percent peak load Screen D",
        candidates=sample_tariff_chunks,
        top_n=2,
    )
    assert len(results_d) == 2
    assert results_d[0].chunk.chunk_id == "TEST_RULE21_SCREEN_D"
    assert results_d[0].rank == 1
    assert 0.0 <= results_d[0].score <= 1.0
    assert results_d[0].score >= results_d[1].score
    assert results_d[0].citation.page_number == 14

    # Query targeting UL 1741-SB
    results_b = reranker.rerank(
        query="UL 1741-SB certified smart inverter equipment Screen B",
        candidates=sample_tariff_chunks,
        top_n=1,
    )
    assert len(results_b) == 1
    assert results_b[0].chunk.chunk_id == "TEST_RULE21_SCREEN_B"
    assert results_b[0].citation.page_number == 8


def test_bge_reranker_initialization() -> None:
    """Verify BGEReranker configuration and default model parameters."""
    reranker = BGEReranker(
        model_name="BAAI/bge-reranker-base",
        providers=["CPUExecutionProvider"],
    )
    assert reranker._model_name == "BAAI/bge-reranker-base"
    assert reranker._providers == ["CPUExecutionProvider"]
    assert reranker._session is None  # Lazy loading


def test_get_reranker_factory() -> None:
    """Verify get_reranker factory function."""
    mock_reranker = get_reranker(use_mock=True)
    assert isinstance(mock_reranker, DeterministicMockReranker)

    prod_reranker = get_reranker(use_mock=False)
    assert isinstance(prod_reranker, BGEReranker)


def test_hybrid_retriever_two_stage_retrieve_and_rerank(
    sample_tariff_chunks: list[TariffChunk],
) -> None:
    """Verify full 2-stage retrieval pipeline: Hybrid retrieval followed by Reranking."""
    store = QdrantVectorStore(location=":memory:")
    bm25 = BM25Index()
    mock_embed = DeterministicMockEmbeddingService()
    reranker = DeterministicMockReranker()

    retriever = HybridRetriever(
        vector_store=store,
        bm25_index=bm25,
        embedding_service=mock_embed,
        collection_name="test_two_stage",
    )
    retriever.index(sample_tariff_chunks)

    # Perform two-stage retrieve and rerank
    query = "anti-islanding protection trip time 2.0 seconds Clause 8"
    reranked = retriever.retrieve_and_rerank(
        query=query,
        reranker=reranker,
        top_k=2,
        candidate_pool_size=3,
    )

    assert len(reranked) == 2
    top_result = reranked[0]
    assert isinstance(top_result, RerankedResult)
    assert top_result.chunk.chunk_id == "TEST_IEEE1547_ANTI_ISLANDING"
    assert top_result.rank == 1
    assert top_result.citation.page_number == 22
    assert "IEEE 1547-2018" in top_result.citation.citation_label
    assert top_result.original_fused_score is not None


def test_two_stage_pipeline_with_ingested_benchmark_tariffs() -> None:
    """Test full 2-stage retrieval with actual ingested regulatory tariffs."""
    tariff_dir = Path("dataset/tariffs")
    if not tariff_dir.exists():
        pytest.skip("dataset/tariffs directory not found")

    chunks, _ = ingest_tariffs(tariff_dir=tariff_dir, dry_run=True)
    assert len(chunks) > 0

    store = QdrantVectorStore(location=":memory:")
    bm25 = BM25Index()
    embedder = DeterministicMockEmbeddingService()
    reranker = DeterministicMockReranker()

    retriever = HybridRetriever(
        vector_store=store,
        bm25_index=bm25,
        embedding_service=embedder,
        collection_name="benchmark_two_stage",
    )
    retriever.index(chunks)

    # Query for Screen D
    results = retriever.retrieve_and_rerank(
        query="Screen D 15% aggregate feeder penetration limit",
        reranker=reranker,
        top_k=3,
        candidate_pool_size=10,
    )
    assert len(results) > 0
    top_hit = results[0]
    assert "Screen D" in top_hit.chunk.section_title or "15%" in top_hit.chunk.content
    assert top_hit.citation.page_number >= 1
    assert top_hit.citation.citation_label != ""
