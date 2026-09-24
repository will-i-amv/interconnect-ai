"""Pydantic schemas for regulatory tariff chunks and RAG ingestion manifests."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TariffJurisdiction(StrEnum):
    """Supported electric utility regulatory jurisdictions and standard bodies."""

    CA_RULE_21 = "CA_RULE_21"
    IEEE_1547 = "IEEE_1547"
    FERC_ORDER_2023 = "FERC_ORDER_2023"
    OTHER = "OTHER"


class TariffChunk(BaseModel):
    """Standardized, grounded text chunk for dense vector and BM25 hybrid indexing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(
        ..., description="Unique deterministic identifier (e.g. CA_RULE_21_P2_SEC_D_0)"
    )
    document_title: str = Field(..., description="Full canonical title of the regulatory standard")
    jurisdiction: TariffJurisdiction = Field(..., description="Regulatory jurisdiction identifier")
    source_filename: str = Field(..., description="Basename of source PDF or Markdown file")
    page_number: int = Field(
        ..., ge=1, description="1-indexed document page where chunk content appears"
    )
    section_hierarchy: list[str] = Field(
        ...,
        min_length=1,
        description="Hierarchical breadcrumb list from top-level to current section",
    )
    section_title: str = Field(..., description="Immediate heading title enclosing this chunk")
    content: str = Field(
        ...,
        description=(
            "Searchable chunk text containing injected contextual hierarchy header and body text"
        ),
    )
    raw_text: str = Field(
        ..., description="Raw text of the section or paragraph without injected header"
    )
    char_count: int = Field(..., ge=0, description="Character count of content")
    word_count: int = Field(..., ge=0, description="Word count of content")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional attributes (clause ID, screen letter, etc.)",
    )

    @property
    def hierarchy_path(self) -> str:
        """Formatted string representation of the section hierarchy breadcrumb."""
        return " > ".join(self.section_hierarchy)


class IngestionSummary(BaseModel):
    """Execution telemetry from a regulatory tariff ingestion run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_documents: int = Field(..., ge=0, description="Total number of files processed")
    total_chunks: int = Field(..., ge=0, description="Total number of chunks produced")
    total_words: int = Field(..., ge=0, description="Total word count across all chunks")
    jurisdictions_indexed: list[TariffJurisdiction] = Field(
        ..., description="List of unique jurisdictions included in this run"
    )
    output_manifest_path: str | None = Field(
        default=None, description="Path where JSON chunk manifest was saved, if any"
    )
    execution_time_seconds: float = Field(..., ge=0, description="Total elapsed runtime (seconds)")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Run completion timestamp",
    )


class RetrievedChunk(BaseModel):
    """Result of hybrid retrieval combining dense semantic and BM25 sparse search."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: TariffChunk = Field(..., description="The underlying retrieved tariff chunk")
    fused_score: float = Field(
        ..., description="Reciprocal Rank Fusion (RRF) fused relevance score"
    )
    dense_rank: int | None = Field(
        default=None,
        ge=1,
        description="1-indexed rank from dense vector retrieval, if matched",
    )
    dense_score: float | None = Field(
        default=None,
        description="Cosine similarity score from dense vector search, if matched",
    )
    bm25_rank: int | None = Field(
        default=None,
        ge=1,
        description="1-indexed rank from BM25 sparse retrieval, if matched",
    )
    bm25_score: float | None = Field(
        default=None, description="Raw BM25 score from keyword retrieval, if matched"
    )


class TariffCitation(BaseModel):
    """Formal regulatory citation for screening reports, audit logs, and deficiency memos."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(..., description="Unique deterministic citation identifier")
    document_title: str = Field(..., description="Canonical standard title (e.g. Electric Rule 21)")
    jurisdiction: TariffJurisdiction = Field(
        ..., description="Regulatory body/jurisdiction identifier"
    )
    section_hierarchy: list[str] = Field(
        ..., min_length=1, description="Breadcrumb hierarchy leading to the cited section"
    )
    section_title: str = Field(..., description="Immediate section or screen title")
    page_number: int = Field(..., ge=1, description="1-indexed exact document page number")
    source_filename: str = Field(..., description="Source filename of standard PDF or Markdown")
    relevance_score: float = Field(
        ..., ge=0.0, le=1.0, description="Cross-encoder relevance score normalized to [0, 1]"
    )
    citation_label: str = Field(
        ..., description="Formatted label, e.g. [CA Rule 21 § Section D > Screen D, p. 14]"
    )
    exact_quote: str = Field(
        ..., description="Verbatim excerpt or key sentence from the cited clause"
    )
    chunk_id: str = Field(..., description="Identifier of the underlying source TariffChunk")


class RerankedResult(BaseModel):
    """Candidate chunk scored and ranked by the cross-encoder with citation metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: TariffChunk = Field(..., description="The underlying retrieved tariff chunk")
    score: float = Field(
        ..., ge=0.0, le=1.0, description="Cross-encoder relevance score normalized to [0, 1]"
    )
    rank: int = Field(..., ge=1, description="1-indexed final reranked position")
    original_fused_score: float | None = Field(
        default=None, description="Stage 1 RRF fused score before reranking, if available"
    )
    citation: TariffCitation = Field(
        ..., description="Structured citation metadata with exact page numbers"
    )
