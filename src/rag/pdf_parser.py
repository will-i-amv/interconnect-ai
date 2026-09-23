"""Layout-aware PDF and Markdown document parser for regulatory utility tariffs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from src.schemas.tariff import TariffJurisdiction


@dataclass(frozen=True)
class ParsedSection:
    """A distinct structural section extracted from a regulatory document."""

    heading: str
    page_number: int
    hierarchy: list[str]
    body: str
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class ParsedDocument:
    """A fully parsed regulatory document ready for hierarchical chunking."""

    document_title: str
    subtitle: str
    jurisdiction: TariffJurisdiction
    source_filename: str
    sections: list[ParsedSection] = field(default_factory=list)


def detect_jurisdiction(text: str, filename: str) -> TariffJurisdiction:
    """Determine regulatory jurisdiction from filename and document text."""
    combined = f"{filename} {text}".lower()
    if "rule 21" in combined or "rule_21" in combined:
        return TariffJurisdiction.CA_RULE_21
    if "1547" in combined:
        return TariffJurisdiction.IEEE_1547
    if "order 2023" in combined or "order_2023" in combined or "ferc" in combined:
        return TariffJurisdiction.FERC_ORDER_2023
    return TariffJurisdiction.OTHER


class LayoutAwarePDFParser:
    """Extracts hierarchical sections from vector and scanned PDFs using font metadata."""

    def __init__(self, heading_min_font_size: float = 10.0) -> None:
        self.heading_min_font_size = heading_min_font_size

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a PDF document into a structured ParsedDocument with hierarchy.

        Args:
            file_path: Path to the target PDF file.

        Returns:
            ParsedDocument containing extracted sections, page numbers, and breadcrumbs.
        """
        doc = pymupdf.open(file_path)
        filename = file_path.name

        doc_title = "Regulatory Interconnection Tariff"
        doc_subtitle = ""
        sections: list[ParsedSection] = []

        # Hierarchy tracking state
        current_major_section = ""
        current_sub_section = ""
        current_body_lines: list[str] = []
        current_page = 1
        current_bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            page_dict = page.get_text("dict")
            blocks: list[dict[str, Any]] = page_dict.get("blocks", [])

            for block in blocks:
                if block.get("type") != 0:  # Skip image/drawing blocks
                    continue

                lines = block.get("lines", [])
                for line in lines:
                    spans = line.get("spans", [])
                    if not spans:
                        continue

                    # Analyze dominant font size in the line
                    max_size = max(span.get("size", 0.0) for span in spans)
                    line_text = "".join(span.get("text", "") for span in spans).strip()
                    if not line_text:
                        continue

                    # Document banner title (typically largest font size on page 1)
                    if (
                        page_num == 1
                        and max_size >= 12.5
                        and doc_title == "Regulatory Interconnection Tariff"
                    ):
                        doc_title = line_text
                        continue

                    # Document subtitle on page 1
                    if (
                        page_num == 1
                        and not doc_subtitle
                        and line_text != doc_title
                        and (
                            "Standard" in line_text
                            or "Technical" in line_text
                            or "Interconnection" in line_text
                        )
                    ):
                        doc_subtitle = line_text
                        continue

                    # Check for section or screen heading:
                    # 1. Font size matches heading size (>= 10.0) OR
                    # 2. Text matches known regulatory heading patterns
                    is_heading = max_size >= self.heading_min_font_size or bool(
                        re.match(
                            r"^(Section|Screen|Clause|Article|Appendix)\s+[A-Z0-9]",
                            line_text,
                            re.IGNORECASE,
                        )
                    )

                    if is_heading and len(line_text) < 120 and not line_text.endswith("."):
                        # Flush previous section
                        if (current_major_section or current_sub_section) and current_body_lines:
                            heading_name = current_sub_section or current_major_section
                            hierarchy = [doc_title]
                            if current_major_section and current_major_section != heading_name:
                                hierarchy.append(current_major_section)
                            hierarchy.append(heading_name)

                            sections.append(
                                ParsedSection(
                                    heading=heading_name,
                                    page_number=current_page,
                                    hierarchy=hierarchy,
                                    body="\n".join(current_body_lines).strip(),
                                    bbox=current_bbox,
                                )
                            )
                            current_body_lines = []

                        # Update current heading and page
                        current_page = page_num
                        bbox_list = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
                        current_bbox = (
                            float(bbox_list[0]),
                            float(bbox_list[1]),
                            float(bbox_list[2]),
                            float(bbox_list[3]),
                        )

                        if re.match(r"^(Section|Clause)\s+[A-Z0-9]", line_text, re.IGNORECASE):
                            current_major_section = line_text
                            current_sub_section = ""
                        elif re.match(r"^Screen\s+[A-Z0-9]", line_text, re.IGNORECASE):
                            current_sub_section = line_text
                        else:
                            current_sub_section = line_text
                    else:
                        current_body_lines.append(line_text)

        # Flush final section
        if (current_major_section or current_sub_section) and current_body_lines:
            heading_name = current_sub_section or current_major_section
            hierarchy = [doc_title]
            if current_major_section and current_major_section != heading_name:
                hierarchy.append(current_major_section)
            hierarchy.append(heading_name)

            sections.append(
                ParsedSection(
                    heading=heading_name,
                    page_number=current_page,
                    hierarchy=hierarchy,
                    body="\n".join(current_body_lines).strip(),
                    bbox=current_bbox,
                )
            )

        doc.close()

        jurisdiction = detect_jurisdiction(doc_title, filename)

        return ParsedDocument(
            document_title=doc_title,
            subtitle=doc_subtitle,
            jurisdiction=jurisdiction,
            source_filename=filename,
            sections=sections,
        )


class MarkdownTariffParser:
    """Parses native Markdown tariff source documents preserving heading hierarchies."""

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a Markdown tariff document into structured sections."""
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        filename = file_path.name

        doc_title = "Regulatory Interconnection Standard"
        doc_subtitle = ""
        sections: list[ParsedSection] = []

        current_h2 = ""
        current_h3_or_h4 = ""
        current_body: list[str] = []

        for line in lines:
            stripped = line.strip()

            # Level 1 Heading (# Title)
            if stripped.startswith("# ") and not stripped.startswith("## "):
                doc_title = stripped[2:].strip()
                continue

            # Level 2 Heading (## Subtitle / Major Division)
            if stripped.startswith("## ") and not stripped.startswith("### "):
                current_h2 = stripped[3:].strip()
                continue

            # Level 3 or 4 Heading (### or ####)
            if re.match(r"^#{3,4}\s+", stripped):
                if (current_h2 or current_h3_or_h4) and current_body:
                    heading_name = current_h3_or_h4 or current_h2
                    hierarchy = [doc_title]
                    if current_h2 and current_h2 != heading_name:
                        hierarchy.append(current_h2)
                    hierarchy.append(heading_name)

                    sections.append(
                        ParsedSection(
                            heading=heading_name,
                            page_number=1,  # Markdown is single continuous document
                            hierarchy=hierarchy,
                            body="\n".join(current_body).strip(),
                        )
                    )
                    current_body = []

                header_text = re.sub(r"^#{3,4}\s+", "", stripped)
                current_h3_or_h4 = header_text.replace("**", "").strip()
                continue

            if stripped in {"---", "***", "___"}:
                continue

            if current_h2 or current_h3_or_h4:
                current_body.append(line)

        # Flush final section
        if (current_h2 or current_h3_or_h4) and current_body:
            heading_name = current_h3_or_h4 or current_h2
            hierarchy = [doc_title]
            if current_h2 and current_h2 != heading_name:
                hierarchy.append(current_h2)
            hierarchy.append(heading_name)

            sections.append(
                ParsedSection(
                    heading=heading_name,
                    page_number=1,
                    hierarchy=hierarchy,
                    body="\n".join(current_body).strip(),
                )
            )

        jurisdiction = detect_jurisdiction(doc_title, filename)

        return ParsedDocument(
            document_title=doc_title,
            subtitle=doc_subtitle,
            jurisdiction=jurisdiction,
            source_filename=filename,
            sections=sections,
        )
