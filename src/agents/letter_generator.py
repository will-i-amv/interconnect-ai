"""Deficiency & Approval synthesis engine and formal letter generator.

Generates structured, publication-ready utility interconnection decision memos
(Markdown & styled multi-page PDF) with exact regulatory citations per CPUC Rule 21,
IEEE 1547-2018, and FERC Order 2023 standards.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pymupdf

from src.agents.state import InterconnectionState
from src.schemas.screening import OverallOutcome, ScreenStatus
from src.schemas.tariff import TariffCitation

logger = logging.getLogger(__name__)


def generate_letter_markdown(state: InterconnectionState) -> str:
    """Generate a formal, publication-ready interconnection decision memo in Markdown.

    Args:
        state: Active InterconnectionState containing application_data, screen_results,
            deficiencies, and retrieved_citations.

    Returns:
        Structured Markdown text suitable for formal utility transmission to the applicant.
    """
    app_id = state.get("application_id", "UNKNOWN")
    app_data = state.get("application_data")
    screen_results = state.get("screen_results", [])
    deficiencies = state.get("deficiencies", [])
    citations: list[TariffCitation] = state.get("retrieved_citations", [])
    outcome = state.get("overall_outcome", OverallOutcome.FAST_TRACK_APPROVED)

    # Determine date and utility metadata
    review_date = datetime.now(UTC).strftime("%B %d, %Y")
    utility_name = app_data.utility_provider if app_data else "Electric Distribution Utility"
    applicant_name = app_data.applicant_name if app_data else "Interconnection Customer"
    site_address = app_data.site_address if app_data else "Project Location On File"
    service_voltage = app_data.service_voltage if app_data else "480V 3-Phase"
    export_capacity_kw = f"{app_data.total_export_capacity_kw:,.1f}" if app_data else "0.0"
    project_type = app_data.project_type.value if app_data else "SOLAR_PV"

    is_approval = outcome == OverallOutcome.FAST_TRACK_APPROVED
    determination_title = (
        "FAST TRACK INITIAL REVIEW APPROVAL NOTICE"
        if is_approval
        else "FAST TRACK INITIAL REVIEW DEFICIENCY NOTICE & INTENT TO DENY"
    )

    lines: list[str] = []

    # 1. Document Title
    lines.append(f"# {utility_name} — Distribution Interconnection Bureau")
    lines.append(f"## {determination_title}")
    lines.append("")

    # 2. Executive Summary Box
    lines.append("| Application Reference | Project Details |")
    lines.append("|---|---|")
    lines.append(f"| **Application ID**: `{app_id}` | **Applicant**: {applicant_name} |")
    lines.append(f"| **Review Date**: {review_date} | **Installation Site**: {site_address} |")
    lines.append(
        f"| **Governing Standard**: CPUC Electric Rule 21 | "
        f"**Export Capacity**: {export_capacity_kw} kW |"
    )
    lines.append(
        f"| **Jurisdiction**: California Public Utilities Commission | "
        f"**Service Voltage**: {service_voltage} |"
    )
    lines.append(
        f"| **Interconnection Technology**: {project_type} | "
        f"**Formal Determination**: **{outcome.value}** |"
    )
    lines.append("")

    # 3. Executive Determination Statement
    lines.append("### Executive Determination")
    if is_approval:
        lines.append(
            f"The {utility_name} Distribution Planning & Engineering Bureau has completed the "
            f"technical screening evaluation for interconnection application **{app_id}** pursuant "
            "to California Public Utilities Commission (CPUC) Electric Rule 21 Section D and IEEE "
            f"Standard 1547-2018. The proposed **{export_capacity_kw} kW** generating facility "
            "has passed all applicable Fast Track engineering screens without identifying any "
            "adverse safety, thermal, voltage fluctuation, or grid reliability deficiencies on "
            "the local distribution feeder. "
            "**Fast Track Initial Review clearance is hereby granted.**"
        )
    else:
        deficiency_count = len(deficiencies)
        lines.append(
            f"The {utility_name} Distribution Planning & Engineering Bureau has completed the "
            f"technical screening evaluation for interconnection application **{app_id}** pursuant "
            f"to California Public Utilities Commission (CPUC) Electric Rule 21 Section D. "
            f"The technical review has identified **{deficiency_count} formal engineering "
            "deficiency(ies)** that prevent Fast Track Initial Review approval in its current "
            "configuration. The applicant is hereby provided statutory notice of these findings "
            "and must elect one of the formal response options detailed below within the "
            "mandatory cure deadline."
        )
    lines.append("")

    # 4. Technical Screening Evaluation Matrix
    lines.append("### Technical Screen Evaluation Matrix")
    lines.append(
        "Each screen reflects deterministic distribution engineering criteria verified against "
        "project single-line diagrams, equipment cut-sheets, and 12-month substation feeder "
        "telemetry."
    )
    lines.append("")
    lines.append(
        "| Screen ID | Screen Name | Governing Tariff Section | "
        "Evaluated Value | Threshold Limit | Status |"
    )
    lines.append("|---|---|---|---|---|:---:|")

    for scr in screen_results:
        status_badge = "**PASS**" if scr.status == ScreenStatus.PASS else "**FAIL**"
        if isinstance(scr.calculated_value, float):
            val_str = f"{scr.calculated_value:.2f}"
        elif scr.calculated_value is not None:
            val_str = str(scr.calculated_value)
        else:
            val_str = "Verified"

        if isinstance(scr.threshold_value, float):
            thresh_str = f"{scr.threshold_value:.2f}"
        elif scr.threshold_value is not None:
            thresh_str = str(scr.threshold_value)
        else:
            thresh_str = "Standard Spec"

        lines.append(
            f"| `{scr.screen_id}` | {scr.screen_name} | {scr.citation} | "
            f"{val_str} | {thresh_str} | {status_badge} |"
        )
    lines.append("")

    # 5. Deficiency Breakdown (if any)
    if deficiencies:
        lines.append("### Identified Engineering Deficiencies & Required Cure Actions")
        lines.append(
            "Pursuant to CPUC Rule 21 Section D and FERC Order 2023, the applicant must resolve "
            "all identified deficiencies prior to the expiration of the statutory cure window."
        )
        lines.append("")

        for idx, def_item in enumerate(deficiencies, 1):
            lines.append(f"#### Deficiency {idx}: {def_item.code} — {def_item.title}")
            lines.append(f"- **Violating Screen**: `{def_item.violating_screen}`")
            lines.append(f"- **Description**: {def_item.description}")
            lines.append(
                f"- **Cure Deadline**: **{def_item.cure_deadline_business_days} Business Days** "
                "from receipt of this notice"
            )
            lines.append(f"- **Required Corrective Action**: {def_item.required_cure_action}")
            if def_item.tariff_citation:
                lines.append(f"- **Governing Regulatory Citation**: {def_item.tariff_citation}")
            lines.append("")

    # 6. Regulatory Grounding & Verbatim Tariff Citations
    if citations:
        lines.append("### Governing Regulatory Grounding & Tariff Citations")
        lines.append(
            "The technical determinations in this notice are grounded in the following governing "
            "tariff clauses and standards:"
        )
        lines.append("")
        for cit in citations:
            lines.append(f"- **{cit.citation_label}** (`{cit.citation_id}`):")
            lines.append(f"  - *Standard*: {cit.document_title} ({cit.jurisdiction.value})")
            lines.append(f"  - *Section*: {' > '.join(cit.section_hierarchy)}: {cit.section_title}")
            lines.append(f"  - *Source Reference*: `{cit.source_filename}`, Page {cit.page_number}")
            lines.append(f'  - *Regulatory Clause*: "{cit.exact_quote}"')
        lines.append("")

    # 7. Next Steps & Applicant Action Plan
    lines.append("### Next Steps & Action Plan")
    if is_approval:
        lines.append("To proceed toward commercial operation, please complete the following steps:")
        lines.append(
            "1. **Execute Interconnection Agreement**: Sign and return the CPUC Rule 21 Standard "
            "Distribution Interconnection Agreement within 30 calendar days."
        )
        lines.append(
            "2. **Schedule Pre-Parallel Inspection**: Upon facility construction completion, "
            "submit the Final Building Permit and request utility field inspection."
        )
        lines.append(
            "3. **Revenue Meter Upgrades**: The utility will inspect the service entrance, "
            "configure bi-directional interval metering, and issue formal "
            "**Permission to Operate (PTO)**."
        )
    else:
        lines.append(
            "The applicant must select and submit written notice of one of the following "
            "formal options within the statutory cure deadline:"
        )
        lines.append(
            "1. **Option 1 (Cure Deficiencies)**: Submit revised engineering documentation "
            "(e.g. updated Single-Line Diagram, certified inverter cut-sheets) addressing "
            "all items above within the required business days."
        )
        lines.append(
            "2. **Option 2 (Supplemental Review)**: Elect to proceed to CPUC Rule 21 "
            "Supplemental Review (15-day technical evaluation) or Detailed Interconnection Study."
        )
        lines.append(
            "3. **Option 3 (Application Withdrawal)**: Formally withdraw the application "
            "with an accounting and refund of any unexpended technical review deposits."
        )
    lines.append("")

    # 8. Signature Block
    lines.append("---")
    lines.append("### Verification & Professional Engineering Sign-Off")
    lines.append("")
    lines.append(
        f"**Authorized Bureau**: {utility_name} — Distribution Planning & Engineering Bureau  "
    )
    lines.append(
        f"**Reviewing System**: InterconnectAI Technical Screening Engine (Audit: `REV-{app_id}`)  "
    )
    lines.append(f"**Date Issued**: {review_date}  ")
    if is_approval:
        lines.append("**Status**: Approved for Interconnection Agreement Execution  ")
    else:
        lines.append("**Status**: Fast Track Blocked — Pending Applicant Response / Human Review  ")

    return "\n".join(lines)


def export_letter_pdf(
    letter_markdown: str,
    output_path: str | Path,
    title: str | None = None,
    subtitle: str | None = None,
    is_approval: bool = True,
) -> Path:
    """Export the formal letter markdown to an executive, publication-styled PDF document.

    Args:
        letter_markdown: Full Markdown text of the interconnection letter.
        output_path: File system path where the PDF will be saved.
        title: Optional custom header title.
        subtitle: Optional custom header subtitle.
        is_approval: Boolean indicating whether outcome is approval or deficiency.

    Returns:
        Path to the successfully generated PDF file.
    """
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    header_color = (0.10, 0.22, 0.42) if is_approval else (0.50, 0.12, 0.12)
    default_title = (
        "INTERCONNECTION FAST TRACK APPROVAL NOTICE"
        if is_approval
        else "INTERCONNECTION FAST TRACK DEFICIENCY NOTICE"
    )
    default_sub = "Electric Distribution Technical Screening & Regulatory Compliance Memo"

    doc = pymupdf.open()
    page_width, page_height = 612, 792  # Standard Letter
    margin = 48
    content_width = page_width - (2 * margin)

    page = doc.new_page(width=page_width, height=page_height)
    y_pos = margin

    # Draw Header Banner
    header_rect = pymupdf.Rect(margin, y_pos, page_width - margin, y_pos + 46)
    page.draw_rect(header_rect, color=None, fill=header_color)
    page.insert_text(
        pymupdf.Point(margin + 12, y_pos + 24),
        (title or default_title)[:60],
        fontsize=12,
        fontname="helv",
        color=(1, 1, 1),
    )
    page.insert_text(
        pymupdf.Point(margin + 12, y_pos + 38),
        (subtitle or default_sub)[:80],
        fontsize=8.0,
        fontname="helv",
        color=(0.9, 0.93, 0.98),
    )
    y_pos += 62

    # Parse markdown into major sections
    sections = _parse_markdown_into_pdf_sections(letter_markdown)

    for sec_title, sec_body in sections:
        clean_text = sec_body.replace("**", "").replace("*", "").replace("`", "").strip()
        lines_count = len(clean_text.splitlines())
        estimated_h = 24 + (lines_count * 12) + 12

        # Check for page break
        if y_pos + min(estimated_h, 160) > page_height - margin:
            page = doc.new_page(width=page_width, height=page_height)
            y_pos = margin

        # Section Header
        page.draw_line(
            pymupdf.Point(margin, y_pos),
            pymupdf.Point(page_width - margin, y_pos),
            color=header_color,
            width=1.2,
        )
        page.insert_text(
            pymupdf.Point(margin, y_pos + 14),
            sec_title[:80],
            fontsize=10.0,
            fontname="helv",
            color=header_color,
        )
        y_pos += 22

        # Section Body Textbox
        tb_rect = pymupdf.Rect(margin, y_pos, margin + content_width, page_height - margin)
        rc = page.insert_textbox(
            tb_rect,
            clean_text,
            fontsize=8.5,
            fontname="times-roman",
            color=(0.15, 0.15, 0.15),
            align=pymupdf.TEXT_ALIGN_LEFT,
        )

        if rc < 0:
            # Multi-page overflow
            page = doc.new_page(width=page_width, height=page_height)
            y_pos = margin
            page.insert_textbox(
                pymupdf.Rect(margin, y_pos, margin + content_width, page_height - margin),
                clean_text,
                fontsize=8.5,
                fontname="times-roman",
                color=(0.15, 0.15, 0.15),
            )
            y_pos += (lines_count * 11) + 18
        else:
            y_pos += (lines_count * 11) + 18

    doc.save(dest)
    doc.close()
    logger.info(f"Exported formal interconnection letter PDF to: {dest}")
    return dest


def _parse_markdown_into_pdf_sections(md_text: str) -> list[tuple[str, str]]:
    """Parse Markdown headings into tuples of (section_title, section_body)."""
    sections: list[tuple[str, str]] = []
    current_title = "Overview"
    current_lines: list[str] = []

    for line in md_text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("### "):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
                current_lines = []
            current_title = trimmed[4:].replace("**", "").replace("*", "").strip()
        elif trimmed.startswith("## ") and not trimmed.startswith("### "):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
                current_lines = []
            current_title = trimmed[3:].replace("**", "").replace("*", "").strip()
        elif (trimmed.startswith("# ") and not trimmed.startswith("## ")) or trimmed in {
            "---",
            "***",
            "___",
        }:
            continue
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))

    return [(sec_title, sec_body) for sec_title, sec_body in sections if sec_body.strip()]


class LetterGenerator:
    """Master generator for formal utility interconnection review letters."""

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self.output_dir = Path(output_dir) if output_dir else None

    def generate_markdown(self, state: InterconnectionState) -> str:
        """Synthesize Markdown letter from state."""
        return generate_letter_markdown(state)

    def export_pdf(
        self,
        state: InterconnectionState,
        output_path: str | Path,
    ) -> Path:
        """Generate and export formal PDF letter."""
        md = self.generate_markdown(state)
        outcome = state.get("overall_outcome", OverallOutcome.FAST_TRACK_APPROVED)
        is_approval = outcome == OverallOutcome.FAST_TRACK_APPROVED
        return export_letter_pdf(md, output_path, is_approval=is_approval)

    def generate(
        self,
        state: InterconnectionState,
        output_path: str | Path | None = None,
    ) -> tuple[str, Path | None]:
        """Generate Markdown memo and optional PDF export."""
        md = self.generate_markdown(state)
        pdf_path: Path | None = None

        target = output_path or (
            self.output_dir / f"{state.get('application_id', 'LETTER')}_interconnection_memo.pdf"
            if self.output_dir
            else None
        )
        if target:
            outcome = state.get("overall_outcome", OverallOutcome.FAST_TRACK_APPROVED)
            pdf_path = export_letter_pdf(
                md, target, is_approval=(outcome == OverallOutcome.FAST_TRACK_APPROVED)
            )

        return md, pdf_path
