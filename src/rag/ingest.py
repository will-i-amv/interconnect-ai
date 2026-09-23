"""Tariff ingestion and layout-aware chunking pipeline CLI."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from pathlib import Path

from src.rag.chunker import HierarchicalTariffChunker
from src.rag.pdf_parser import LayoutAwarePDFParser, MarkdownTariffParser
from src.schemas.tariff import IngestionSummary, TariffChunk, TariffJurisdiction


def ingest_tariffs(
    tariff_dir: Path,
    output_file: Path | None = None,
    dry_run: bool = False,
    prefer_pdf: bool = True,
) -> tuple[list[TariffChunk], IngestionSummary]:
    """Ingest, parse, and chunk all regulatory tariffs in a target directory.

    Args:
        tariff_dir: Directory containing tariff PDFs and Markdown files.
        output_file: Optional path to save the serialized chunk manifest JSON.
        dry_run: If True, skips writing output files to disk.
        prefer_pdf: If True, uses compiled PDFs when available, falling back to Markdown.

    Returns:
        Tuple of (list of validated TariffChunk objects, IngestionSummary telemetry).
    """
    start_time = time.perf_counter()
    if not tariff_dir.is_dir():
        raise FileNotFoundError(f"Tariff directory not found: {tariff_dir}")

    pdf_parser = LayoutAwarePDFParser()
    md_parser = MarkdownTariffParser()
    chunker = HierarchicalTariffChunker()

    all_chunks: list[TariffChunk] = []
    processed_docs = 0
    jurisdictions_seen: set[TariffJurisdiction] = set()

    # Discover documents
    pdf_files = sorted(tariff_dir.glob("*.pdf"))
    md_files = sorted(tariff_dir.glob("*.md"))

    files_to_process: list[Path] = []
    if prefer_pdf and pdf_files:
        files_to_process.extend(pdf_files)
        # Also include any markdown files that do NOT have a matching PDF stem
        pdf_stems = {p.stem for p in pdf_files}
        for md in md_files:
            if md.stem not in pdf_stems:
                files_to_process.append(md)
    else:
        files_to_process.extend(md_files or pdf_files)

    for doc_path in files_to_process:
        if doc_path.suffix.lower() == ".pdf":
            parsed_doc = pdf_parser.parse(doc_path)
        elif doc_path.suffix.lower() == ".md":
            parsed_doc = md_parser.parse(doc_path)
        else:
            continue

        doc_chunks = chunker.chunk_document(parsed_doc)
        all_chunks.extend(doc_chunks)
        processed_docs += 1
        jurisdictions_seen.add(parsed_doc.jurisdiction)

    total_words = sum(c.word_count for c in all_chunks)
    elapsed = round(time.perf_counter() - start_time, 3)

    summary = IngestionSummary(
        total_documents=processed_docs,
        total_chunks=len(all_chunks),
        total_words=total_words,
        jurisdictions_indexed=sorted(jurisdictions_seen, key=lambda j: j.value),
        output_manifest_path=(str(output_file) if (output_file and not dry_run) else None),
        execution_time_seconds=elapsed,
    )

    if output_file and not dry_run:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        dump_data = [chunk.model_dump() for chunk in all_chunks]
        output_file.write_text(json.dumps(dump_data, indent=2, default=str), encoding="utf-8")

    return all_chunks, summary


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for tariff ingestion."""
    parser = argparse.ArgumentParser(
        description="Ingest regulatory utility tariff documents with layout-aware chunking."
    )
    parser.add_argument(
        "--tariff-dir",
        type=Path,
        default=Path("dataset/tariffs"),
        help="Path to directory containing tariff PDFs and Markdown files.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("dataset/tariffs/processed_chunks.json"),
        help="Path to write the processed JSON chunks manifest.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk documents without writing manifest to disk.",
    )

    args = parser.parse_args(argv)

    print("=== InterconnectAI Tariff Ingestion Pipeline ===")
    print(f"Reading from: {args.tariff_dir}")
    print(f"Dry run mode: {args.dry_run}")

    chunks, summary = ingest_tariffs(
        tariff_dir=args.tariff_dir,
        output_file=args.output_file,
        dry_run=args.dry_run,
    )

    print(f"\nIngestion Complete in {summary.execution_time_seconds}s:")
    print(f"  - Documents processed: {summary.total_documents}")
    print(f"  - Chunks generated:    {summary.total_chunks}")
    print(f"  - Total words:         {summary.total_words}")
    print(f"  - Jurisdictions:       {[j.value for j in summary.jurisdictions_indexed]}")
    if summary.output_manifest_path:
        print(f"  - Saved manifest:      {summary.output_manifest_path}")

    # Display preview of top 3 chunks
    print("\n--- Sample Chunks Preview ---")
    for i, chunk in enumerate(chunks[:3]):
        print(f"[{i + 1}] ID: {chunk.chunk_id}")
        print(f"    Title: {chunk.section_title} (Page {chunk.page_number})")
        print(f"    Path:  {chunk.hierarchy_path}")
        first_line = chunk.content.splitlines()[1] if len(chunk.content.splitlines()) > 1 else ""
        print(f"    Snippet: {first_line[:80]}...\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
