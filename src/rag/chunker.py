"""Hierarchical section-preserving chunker with contextual header prepending."""

from __future__ import annotations

import re
from pathlib import Path

from src.rag.pdf_parser import ParsedDocument, ParsedSection
from src.schemas.tariff import TariffChunk


def slugify(text: str) -> str:
    """Generate a clean alphanumeric identifier slug from text."""
    clean = re.sub(r"[^\w\s-]", "", text).strip().upper()
    return re.sub(r"[-\s]+", "_", clean)


class HierarchicalTariffChunker:
    """Chunks structured regulatory sections while preserving hierarchy and context."""

    def __init__(
        self,
        max_chunk_chars: int = 1200,
        min_chunk_chars: int = 80,
    ) -> None:
        self.max_chunk_chars = max_chunk_chars
        self.min_chunk_chars = min_chunk_chars

    def chunk_document(self, parsed_doc: ParsedDocument) -> list[TariffChunk]:
        """Convert a ParsedDocument into a list of contextualized TariffChunk objects.

        Args:
            parsed_doc: The output from LayoutAwarePDFParser or MarkdownTariffParser.

        Returns:
            List of validated, grounded TariffChunk instances.
        """
        chunks: list[TariffChunk] = []

        for sec_idx, section in enumerate(parsed_doc.sections):
            section_chunks = self._chunk_section(parsed_doc, section, sec_idx)
            chunks.extend(section_chunks)

        return chunks

    def _chunk_section(
        self,
        doc: ParsedDocument,
        section: ParsedSection,
        section_index: int,
    ) -> list[TariffChunk]:
        """Process a single parsed section into one or more TariffChunks with injected headers."""
        raw_body = section.body.strip()
        if not raw_body:
            return []

        # Build Context-Prepending Header
        breadcrumb = " > ".join(section.hierarchy)
        header = (
            f"[Document: {doc.document_title} | "
            f"Jurisdiction: {doc.jurisdiction.value} | "
            f"Path: {breadcrumb} | "
            f"Page: {section.page_number}]"
        )

        source_slug = slugify(Path(doc.source_filename).stem)
        sec_slug = slugify(section.heading)[:30]

        # Case 1: Section fits comfortably in one chunk
        if len(raw_body) <= self.max_chunk_chars:
            content = f"{header}\n{raw_body}"
            chunk_id = (
                f"{doc.jurisdiction.value}_{source_slug}_"
                f"p{section.page_number}_{sec_slug}_{section_index}_0"
            )
            return [
                TariffChunk(
                    chunk_id=chunk_id,
                    document_title=doc.document_title,
                    jurisdiction=doc.jurisdiction,
                    source_filename=doc.source_filename,
                    page_number=section.page_number,
                    section_hierarchy=section.hierarchy,
                    section_title=section.heading,
                    content=content,
                    raw_text=raw_body,
                    char_count=len(content),
                    word_count=len(content.split()),
                    metadata={
                        "section_index": section_index,
                        "sub_chunk_index": 0,
                        "bbox": section.bbox,
                    },
                )
            ]

        # Case 2: Multi-paragraph section exceeding max_chunk_chars -> split on paragraphs
        paragraphs = [p.strip() for p in raw_body.split("\n\n") if p.strip()]
        if len(paragraphs) <= 1:
            # Fallback: split on single newlines
            paragraphs = [p.strip() for p in raw_body.split("\n") if p.strip()]

        result_chunks: list[TariffChunk] = []
        current_sub_text: list[str] = []
        current_len = 0
        sub_idx = 0

        for p in paragraphs:
            if current_len + len(p) > self.max_chunk_chars and current_sub_text:
                combined_body = "\n\n".join(current_sub_text)
                content = f"{header}\n{combined_body}"
                chunk_id = (
                    f"{doc.jurisdiction.value}_{source_slug}_"
                    f"p{section.page_number}_{sec_slug}_{section_index}_{sub_idx}"
                )

                result_chunks.append(
                    TariffChunk(
                        chunk_id=chunk_id,
                        document_title=doc.document_title,
                        jurisdiction=doc.jurisdiction,
                        source_filename=doc.source_filename,
                        page_number=section.page_number,
                        section_hierarchy=section.hierarchy,
                        section_title=section.heading,
                        content=content,
                        raw_text=combined_body,
                        char_count=len(content),
                        word_count=len(content.split()),
                        metadata={
                            "section_index": section_index,
                            "sub_chunk_index": sub_idx,
                            "bbox": section.bbox,
                        },
                    )
                )
                current_sub_text = [p]
                current_len = len(p)
                sub_idx += 1
            else:
                current_sub_text.append(p)
                current_len += len(p)

        if current_sub_text:
            combined_body = "\n\n".join(current_sub_text)
            content = f"{header}\n{combined_body}"
            chunk_id = (
                f"{doc.jurisdiction.value}_{source_slug}_"
                f"p{section.page_number}_{sec_slug}_{section_index}_{sub_idx}"
            )

            result_chunks.append(
                TariffChunk(
                    chunk_id=chunk_id,
                    document_title=doc.document_title,
                    jurisdiction=doc.jurisdiction,
                    source_filename=doc.source_filename,
                    page_number=section.page_number,
                    section_hierarchy=section.hierarchy,
                    section_title=section.heading,
                    content=content,
                    raw_text=combined_body,
                    char_count=len(content),
                    word_count=len(content.split()),
                    metadata={
                        "section_index": section_index,
                        "sub_chunk_index": sub_idx,
                        "bbox": section.bbox,
                    },
                )
            )

        return result_chunks
