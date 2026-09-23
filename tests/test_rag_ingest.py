"""Tests for layout-aware PDF/Markdown parsing and hierarchical tariff chunking."""

import json
from pathlib import Path

import pytest

from src.rag.chunker import HierarchicalTariffChunker
from src.rag.ingest import ingest_tariffs, main
from src.rag.pdf_parser import LayoutAwarePDFParser, MarkdownTariffParser, detect_jurisdiction
from src.schemas.tariff import TariffChunk, TariffJurisdiction
from src.utils.dataset import get_dataset_root, get_tariff_path


@pytest.fixture(scope="session", autouse=True)
def ensure_dataset_ready() -> None:
    """Ensure benchmark dataset and tariff PDFs are compiled before tests run."""
    import scripts.generate_benchmark_data as generator

    rule21_pdf = get_dataset_root() / "tariffs" / "ca_rule_21_extract.pdf"
    if not rule21_pdf.is_file():
        generator.compile_tariffs_from_markdown()
        generator.generate_all_applications()


def test_detect_jurisdiction_heuristics() -> None:
    """Verify regulatory jurisdiction classification based on titles and filenames."""
    assert (
        detect_jurisdiction("Rule 21 Standard", "ca_rule_21.pdf") == TariffJurisdiction.CA_RULE_21
    )
    assert (
        detect_jurisdiction("IEEE Std 1547-2018", "ieee_1547.pdf") == TariffJurisdiction.IEEE_1547
    )
    assert (
        detect_jurisdiction("FERC Order 2023 SGIP", "ferc_order.md")
        == TariffJurisdiction.FERC_ORDER_2023
    )
    assert detect_jurisdiction("Generic Manual", "custom.pdf") == TariffJurisdiction.OTHER


def test_layout_aware_pdf_parser_rule21() -> None:
    """Verify layout-aware PDF parser extracts sections and page numbers from Rule 21 PDF."""
    pdf_path = get_tariff_path("ca_rule_21_extract.pdf")
    parser = LayoutAwarePDFParser()
    doc = parser.parse(pdf_path)

    assert doc.jurisdiction == TariffJurisdiction.CA_RULE_21
    assert "Rule 21" in doc.document_title or "California" in doc.document_title
    assert len(doc.sections) >= 6

    # Verify key engineering screens were parsed as sections
    headings = [s.heading for s in doc.sections]
    assert any("Screen B" in h for h in headings), "Screen B heading missing"
    assert any("Screen D" in h for h in headings), "Screen D heading missing"
    assert any("Screen H" in h for h in headings), "Screen H heading missing"

    # Verify multi-page tracking
    pages = {s.page_number for s in doc.sections}
    assert len(pages) >= 2, "Expected sections distributed across at least 2 pages"


def test_layout_aware_pdf_parser_ieee1547() -> None:
    """Verify parsing of IEEE 1547-2018 PDF extracts clauses and power factor rules."""
    pdf_path = get_tariff_path("ieee_1547_2018_extract.pdf")
    parser = LayoutAwarePDFParser()
    doc = parser.parse(pdf_path)

    assert doc.jurisdiction == TariffJurisdiction.IEEE_1547
    headings = [s.heading for s in doc.sections]
    assert any("Clause 5.1" in h for h in headings), "Clause 5.1 heading missing"
    assert any("Clause 8.1" in h or "Anti-Islanding" in h for h in headings)


def test_markdown_tariff_parser_ferc() -> None:
    """Verify MarkdownTariffParser parses native markdown tariff files."""
    md_path = get_tariff_path("ferc_order_2023_sgip.md")
    parser = MarkdownTariffParser()
    doc = parser.parse(md_path)

    assert doc.jurisdiction == TariffJurisdiction.FERC_ORDER_2023
    assert len(doc.sections) >= 2
    assert any("Fast Track" in s.heading for s in doc.sections)


def test_hierarchical_chunker_context_prepending() -> None:
    """Verify HierarchicalTariffChunker injects breadcrumb context header into chunks."""
    pdf_path = get_tariff_path("ca_rule_21_extract.pdf")
    parser = LayoutAwarePDFParser()
    parsed_doc = parser.parse(pdf_path)

    chunker = HierarchicalTariffChunker(max_chunk_chars=1000)
    chunks = chunker.chunk_document(parsed_doc)

    assert len(chunks) >= len(parsed_doc.sections)

    chunk_ids = set()
    for chunk in chunks:
        assert isinstance(chunk, TariffChunk)
        assert chunk.chunk_id not in chunk_ids, f"Duplicate chunk ID found: {chunk.chunk_id}"
        chunk_ids.add(chunk.chunk_id)

        # Context-Prepending Verification
        first_line = chunk.content.splitlines()[0]
        assert first_line.startswith("[Document:"), f"Header missing: {first_line}"
        assert "Jurisdiction: CA_RULE_21" in first_line
        assert f"Page: {chunk.page_number}" in first_line
        assert "Path:" in first_line

        # Word count and character count integrity
        assert chunk.char_count == len(chunk.content)
        assert chunk.word_count == len(chunk.content.split())
        assert len(chunk.raw_text) > 0


def test_ingest_tariffs_pipeline_and_json_manifest(tmp_path: Path) -> None:
    """Verify end-to-end ingest_tariffs pipeline and serialized JSON output."""
    tariff_dir = get_dataset_root() / "tariffs"
    out_file = tmp_path / "processed_chunks.json"

    chunks, summary = ingest_tariffs(
        tariff_dir=tariff_dir,
        output_file=out_file,
        dry_run=False,
    )

    assert summary.total_documents == 3
    assert summary.total_chunks == len(chunks)
    assert summary.total_chunks >= 15
    assert summary.total_words > 1000
    assert summary.output_manifest_path == str(out_file)

    # Verify serialized JSON manifest
    assert out_file.is_file()
    with out_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == len(chunks)

    # Validate deserialization back into TariffChunk models
    first_chunk = TariffChunk.model_validate(data[0])
    assert first_chunk.chunk_id == chunks[0].chunk_id
    assert first_chunk.jurisdiction in {
        TariffJurisdiction.CA_RULE_21,
        TariffJurisdiction.IEEE_1547,
        TariffJurisdiction.FERC_ORDER_2023,
    }


def test_ingest_cli_dry_run() -> None:
    """Verify that CLI execution in dry-run mode succeeds with exit code 0."""
    tariff_dir_str = str(get_dataset_root() / "tariffs")
    exit_code = main(["--tariff-dir", tariff_dir_str, "--dry-run"])
    assert exit_code == 0
