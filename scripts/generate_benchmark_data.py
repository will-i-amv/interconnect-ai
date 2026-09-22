#!/usr/bin/env python3
"""Build compiler script for InterconnectAI benchmark dataset.

Parses canonical Markdown regulatory documents (in dataset/tariffs/) and application
templates to generate derived vector PDFs and SLD diagrams.

Note: Generated PDF files are transient/build artifacts and ignored in git.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

ROOT_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT_DIR / "dataset"
TARIFFS_DIR = DATASET_DIR / "tariffs"
APPS_DIR = DATASET_DIR / "applications"


# -----------------------------------------------------------------------------
# Markdown Parser for Tariff Compilation
# -----------------------------------------------------------------------------


def parse_markdown_to_sections(md_path: Path) -> tuple[str, str, list[tuple[str, str]]]:
    """Parse a Markdown document into title, subtitle, and structured sections.

    Extracts:
    - `# <Title>` -> document title
    - `## <Subtitle>` -> document subtitle
    - `###` or `####` headings -> section header and associated body text
    """
    content = md_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    title = "Technical Standard Document"
    subtitle = "Regulatory Interconnection Specification"
    sections: list[tuple[str, str]] = []

    current_sec_title = ""
    current_sec_body: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Document Title (# )
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            continue

        # Document Subtitle (## )
        if stripped.startswith("## ") and not stripped.startswith("### "):
            subtitle = stripped[3:].strip()
            continue

        # Section Headings (### or ####)
        if re.match(r"^#{3,4}\s+", stripped):
            if current_sec_title and current_sec_body:
                body_text = "\n".join(current_sec_body).strip()
                if body_text:
                    sections.append((current_sec_title, body_text))
                current_sec_body = []

            # Clean markdown formatting like bolding from header
            header_text = re.sub(r"^#{3,4}\s+", "", stripped)
            current_sec_title = header_text.replace("**", "").strip()
            continue

        # Skip horizontal dividers
        if stripped in {"---", "***", "___"}:
            continue

        if current_sec_title:
            current_sec_body.append(line)

    # Append trailing section
    if current_sec_title and current_sec_body:
        body_text = "\n".join(current_sec_body).strip()
        if body_text:
            sections.append((current_sec_title, body_text))

    return title, subtitle, sections


# -----------------------------------------------------------------------------
# Vector PDF Generation Utilities
# -----------------------------------------------------------------------------


def create_styled_pdf(
    output_path: Path,
    title: str,
    subtitle: str,
    sections: list[tuple[str, str]],
    header_color: tuple[float, float, float] = (0.1, 0.25, 0.45),
) -> None:
    """Create a clean, multi-page vector PDF document with structured typography."""
    doc = pymupdf.open()
    page_width, page_height = 612, 792  # Standard Letter
    margin = 54  # 0.75 inch margins
    content_width = page_width - (2 * margin)

    page = doc.new_page(width=page_width, height=page_height)
    y_pos = margin

    # Draw Header Banner
    header_rect = pymupdf.Rect(margin, y_pos, page_width - margin, y_pos + 46)
    page.draw_rect(header_rect, color=None, fill=header_color)
    page.insert_text(
        pymupdf.Point(margin + 14, y_pos + 26),
        title[:58],
        fontsize=13,
        fontname="helv",
        color=(1, 1, 1),
    )
    page.insert_text(
        pymupdf.Point(margin + 14, y_pos + 40),
        subtitle[:80],
        fontsize=8.5,
        fontname="helv",
        color=(0.85, 0.9, 0.95),
    )
    y_pos += 65

    for sec_title, sec_text in sections:
        clean_body = sec_text.replace("**", "").replace("*", "").strip()
        estimated_height = 24 + (len(clean_body.splitlines()) * 13) + 16

        if y_pos + min(estimated_height, 200) > page_height - margin:
            page = doc.new_page(width=page_width, height=page_height)
            y_pos = margin

        # Section Header
        page.draw_line(
            pymupdf.Point(margin, y_pos),
            pymupdf.Point(page_width - margin, y_pos),
            color=header_color,
            width=1,
        )
        page.insert_text(
            pymupdf.Point(margin, y_pos + 14),
            sec_title[:75],
            fontsize=10.5,
            fontname="helv",
            color=header_color,
        )
        y_pos += 22

        # Section Body Text
        text_rect = pymupdf.Rect(margin, y_pos, margin + content_width, page_height - margin)
        rc = page.insert_textbox(
            text_rect,
            clean_body,
            fontsize=9.0,
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
                clean_body,
                fontsize=9.0,
                fontname="times-roman",
                color=(0.15, 0.15, 0.15),
            )
            y_pos += (len(clean_body.splitlines()) * 12) + 20
        else:
            y_pos += (len(clean_body.splitlines()) * 12) + 20

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    doc.close()


def draw_single_line_diagram(
    output_path: Path,
    project_name: str,
    inverter_specs: str,
    include_disconnect_switch: bool = True,
) -> None:
    """Generate a vector electrical Single-Line Diagram (SLD) PDF."""
    doc = pymupdf.open()
    width, height = 792, 612  # Landscape Letter
    page = doc.new_page(width=width, height=height)

    # Title Block (Bottom Right)
    tb_x, tb_y = 520, 480
    page.draw_rect(pymupdf.Rect(tb_x, tb_y, 750, 570), color=(0, 0, 0), width=1.5)
    page.insert_text(
        pymupdf.Point(tb_x + 8, tb_y + 20),
        "ELECTRICAL SINGLE-LINE DIAGRAM",
        fontsize=10,
        fontname="helv",
    )
    page.insert_text(
        pymupdf.Point(tb_x + 8, tb_y + 38), f"Project: {project_name}", fontsize=9, fontname="helv"
    )
    page.insert_text(
        pymupdf.Point(tb_x + 8, tb_y + 54),
        f"Inverters: {inverter_specs}",
        fontsize=8,
        fontname="helv",
    )
    page.insert_text(
        pymupdf.Point(tb_x + 8, tb_y + 70),
        "Status: FOR REGULATORY REVIEW",
        fontsize=8,
        fontname="helv",
    )

    # Outer Border
    page.draw_rect(pymupdf.Rect(30, 30, 762, 582), color=(0.1, 0.1, 0.1), width=1.5)

    # 1. Utility Bus
    page.draw_line(pymupdf.Point(100, 80), pymupdf.Point(700, 80), color=(0.7, 0.1, 0.1), width=2.5)
    page.insert_text(
        pymupdf.Point(110, 72),
        "UTILITY 12.47 kV 3-PHASE DISTRIBUTION FEEDER",
        fontsize=9,
        fontname="helv",
    )

    # 2. Point of Common Coupling (PCC) Tap Line
    page.draw_line(pymupdf.Point(220, 80), pymupdf.Point(220, 140), color=(0, 0, 0), width=1.8)
    page.draw_circle(pymupdf.Point(220, 140), 4, fill=(0, 0, 0))
    page.insert_text(
        pymupdf.Point(232, 142), "PCC (Point of Common Coupling)", fontsize=8.5, fontname="helv"
    )

    # 3. Step-down transformer (Delta-Wye)
    page.draw_circle(pymupdf.Point(220, 175), 18, color=(0, 0, 0), width=1.5)
    page.draw_circle(pymupdf.Point(220, 195), 18, color=(0, 0, 0), width=1.5)
    page.insert_text(
        pymupdf.Point(250, 190),
        "Service Transformer: 12.47 kV Delta / 480V Wye",
        fontsize=8.5,
        fontname="helv",
    )

    # 4. Connection line to Revenue Meter
    page.draw_line(pymupdf.Point(220, 213), pymupdf.Point(220, 260), color=(0, 0, 0), width=1.8)

    # 5. Revenue Meter Symbol (Circle with 'M')
    page.draw_circle(
        pymupdf.Point(220, 280), 16, color=(0, 0, 0), fill=(0.95, 0.95, 0.95), width=1.5
    )
    page.insert_text(pymupdf.Point(214, 285), "M", fontsize=14, fontname="helv")
    page.insert_text(
        pymupdf.Point(245, 284),
        "Utility Bi-Directional Revenue Meter (480V)",
        fontsize=8.5,
        fontname="helv",
    )

    cur_y = 296
    if include_disconnect_switch:
        # 6a. Compliant Visible-Break Lockable AC Disconnect Switch
        page.draw_line(
            pymupdf.Point(220, cur_y), pymupdf.Point(220, 340), color=(0, 0, 0), width=1.8
        )
        page.draw_rect(
            pymupdf.Rect(195, 340, 245, 380), color=(0, 0.5, 0), fill=(0.92, 1.0, 0.92), width=1.5
        )
        page.draw_circle(pymupdf.Point(210, 365), 3, fill=(0, 0, 0))
        page.draw_circle(pymupdf.Point(230, 355), 3, fill=(0, 0, 0))
        page.draw_line(pymupdf.Point(210, 365), pymupdf.Point(226, 348), color=(0, 0, 0), width=1.5)
        page.insert_text(
            pymupdf.Point(255, 356), "UTILITY AC DISCONNECT SWITCH", fontsize=9, fontname="helv"
        )
        page.insert_text(
            pymupdf.Point(255, 370),
            "[COMPLIANT: Visible-break, lockable, exterior mounted]",
            fontsize=8,
            fontname="helv",
            color=(0, 0.5, 0),
        )
        cur_y = 380
    else:
        # 6b. DEFICIENCY: Direct wire skipping external disconnect switch!
        page.draw_line(
            pymupdf.Point(220, cur_y), pymupdf.Point(220, 380), color=(0, 0, 0), width=1.8
        )
        page.draw_rect(
            pymupdf.Rect(170, 335, 270, 365), color=(0.8, 0, 0), fill=(1.0, 0.92, 0.92), width=1
        )
        page.insert_text(
            pymupdf.Point(176, 352),
            "DIRECT BUS TAP - NO AC DISCONNECT",
            fontsize=7.5,
            fontname="helv",
            color=(0.8, 0, 0),
        )
        cur_y = 380

        # 7. Main Switchboard / Service Panel
        page.draw_line(
            pymupdf.Point(220, cur_y), pymupdf.Point(220, 420), color=(0, 0, 0), width=1.8
        )
        page.draw_rect(
            pymupdf.Rect(140, 420, 500, 445), color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=1.5
        )
        page.insert_text(
            pymupdf.Point(150, 436),
            "MAIN SWITCHBOARD (MSB) 480V / 3-PHASE / 4-WIRE / 65 kAIC RATED",
            fontsize=8.5,
            fontname="helv",
        )

        # 8. Main Circuit Breaker
        page.draw_rect(pymupdf.Rect(205, 400, 235, 420), color=(0, 0, 0), fill=(1, 1, 1), width=1)
        page.insert_text(pymupdf.Point(210, 413), "CB", fontsize=8, fontname="helv")

        # 9. Feeders to Inverters
        for i, x_offset in enumerate([180, 280, 380, 460]):
            page.draw_line(
                pymupdf.Point(x_offset, 445),
                pymupdf.Point(x_offset, 490),
                color=(0, 0, 0),
                width=1.5,
            )
            # Dedicated Breaker
            page.draw_rect(
                pymupdf.Rect(x_offset - 12, 460, x_offset + 12, 478),
                color=(0, 0, 0),
                fill=(1, 1, 1),
                width=1,
            )
            page.insert_text(pymupdf.Point(x_offset - 8, 472), "CB", fontsize=7, fontname="helv")
            page.draw_rect(
                pymupdf.Rect(x_offset - 30, 490, x_offset + 30, 530),
                color=(0.1, 0.3, 0.6),
                fill=(0.9, 0.94, 1.0),
                width=1.5,
            )
            page.insert_text(
                pymupdf.Point(x_offset - 24, 506), f"INV #{i + 1}", fontsize=8, fontname="helv"
            )
            page.insert_text(
                pymupdf.Point(x_offset - 26, 520), "Smart Inv", fontsize=7.5, fontname="helv"
            )

        # Grounding Electrode System
        page.draw_line(pymupdf.Point(140, 432), pymupdf.Point(110, 432), color=(0, 0, 0), width=1.5)
        page.draw_line(pymupdf.Point(110, 432), pymupdf.Point(110, 460), color=(0, 0, 0), width=1.5)
        page.draw_line(pymupdf.Point(100, 460), pymupdf.Point(120, 460), color=(0, 0, 0), width=1.5)
        page.draw_line(pymupdf.Point(103, 464), pymupdf.Point(117, 464), color=(0, 0, 0), width=1.2)
        page.draw_line(pymupdf.Point(106, 468), pymupdf.Point(114, 468), color=(0, 0, 0), width=1)
        page.insert_text(
            pymupdf.Point(60, 475), "Grounding Electrode System", fontsize=7, fontname="helv"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    doc.close()


# -----------------------------------------------------------------------------
# Tariff Compilation from Canonical Markdown
# -----------------------------------------------------------------------------


def compile_tariffs_from_markdown() -> None:
    """Compile PDF versions directly from canonical Markdown files in dataset/tariffs/."""
    # 1. California Rule 21
    rule21_md = TARIFFS_DIR / "ca_rule_21_extract.md"
    if rule21_md.is_file():
        title, subtitle, sections = parse_markdown_to_sections(rule21_md)
        create_styled_pdf(
            TARIFFS_DIR / "ca_rule_21_extract.pdf",
            title=title,
            subtitle=subtitle,
            sections=sections,
            header_color=(0.12, 0.28, 0.48),
        )

    # 2. IEEE 1547-2018
    ieee_md = TARIFFS_DIR / "ieee_1547_2018_extract.md"
    if ieee_md.is_file():
        title, subtitle, sections = parse_markdown_to_sections(ieee_md)
        create_styled_pdf(
            TARIFFS_DIR / "ieee_1547_2018_extract.pdf",
            title=title,
            subtitle=subtitle,
            sections=sections,
            header_color=(0.18, 0.38, 0.22),
        )


# -----------------------------------------------------------------------------
# Application Benchmark Packages Generation
# -----------------------------------------------------------------------------


def generate_application_package(
    app_id: str,
    applicant_name: str,
    site_address: str,
    utility_name: str,
    account_number: str,
    project_type: str,
    capacity_kw: float,
    service_voltage: str,
    feeder_id: str,
    feeder_peak_kw: float,
    feeder_mdl_kw: float,
    existing_gen_kw: float,
    inverter_model: str,
    inverter_cert: str,
    inverter_pf: str,
    has_compliant_switch: bool,
    expected_outcome: str,
    failing_screens: list[str],
    citations: list[str],
) -> dict:
    """Generate all application package files and return catalog metadata."""
    app_dir = APPS_DIR / app_id
    app_dir.mkdir(parents=True, exist_ok=True)

    # 1. Application Form PDF
    form_pdf = app_dir / "application_form.pdf"
    sec1_text = (
        f"Legal Entity: {applicant_name}\n"
        f"Project Site: {site_address}\n"
        f"Utility Provider: {utility_name}\n"
        f"Account Number: {account_number}\n"
        "Submission Date: 2026-09-15"
    )
    sec2_text = (
        f"Interconnection Type: {project_type}\n"
        f"Gross Nameplate AC Capacity: {capacity_kw:,.1f} kW-AC\n"
        f"Service Voltage: {service_voltage}\n"
        f"Point of Common Coupling (PCC): Substation Feeder {feeder_id}\n"
        "Proposed In-Service Date: 2026-12-01"
    )
    inv_count = int(capacity_kw / 50) if capacity_kw >= 50 else 1
    sec3_text = (
        f"Inverter Model: {inverter_model}\n"
        f"Total Inverter Count: {inv_count}\n"
        f"Declared Power Factor Capability: {inverter_pf}\n"
        f"Declared Safety Certifications: {inverter_cert}"
    )
    sec4_text = (
        "The undersigned certified professional engineer verifies that all electrical exhibits, "
        "cut-sheets, and Single-Line Diagrams submitted herewith represent actual site conditions."
    )
    sections = [
        ("Section 1: Applicant Information", sec1_text),
        ("Section 2: Technical Project Profile", sec2_text),
        ("Section 3: Inverter & Generating Units", sec3_text),
        ("Section 4: Applicant Verification", sec4_text),
    ]
    create_styled_pdf(
        form_pdf,
        title=f"Interconnection Application - {app_id}",
        subtitle=f"{utility_name} Distribution Interconnection Intake Form",
        sections=sections,
        header_color=(0.15, 0.25, 0.35),
    )

    # 2. Inverter Cut-Sheet PDF
    cutsheet_pdf = app_dir / "inverter_cutsheet.pdf"
    max_amps = capacity_kw * 1000 / (480 * 1.732)
    cs1_text = (
        "Manufacturer: Industrial Power Systems\n"
        f"Model: {inverter_model}\n"
        f"Nominal AC Power Output: {capacity_kw:,.1f} kW\n"
        f"Nominal Grid Voltage: {service_voltage}\n"
        f"Maximum Continuous Output Current: {max_amps:.1f} A"
    )
    cs2_text = (
        f"Operating Power Factor Range: {inverter_pf}\n"
        "Volt-Var Functionality: Enabled / Factory Pre-configured\n"
        "Frequency Ride-Through: Compliant with IEEE 1547 requirements"
    )
    cs3_text = (
        f"Safety Standard Listing: {inverter_cert}\n"
        "Anti-Islanding Protection: Active frequency drift algorithm (trip <= 2.0 s)\n"
        "Enclosure Rating: NEMA 4X / IP66 Outdoor Rated"
    )
    cutsheet_sections = [
        ("Product Overview & General Specifications", cs1_text),
        ("Grid Support & Reactive Capabilities", cs2_text),
        ("Regulatory Certifications & Safety Listings", cs3_text),
    ]
    create_styled_pdf(
        cutsheet_pdf,
        title=f"Datasheet: {inverter_model}",
        subtitle="Commercial & Utility Inverter Engineering Datasheet",
        sections=cutsheet_sections,
        header_color=(0.2, 0.3, 0.4),
    )

    # 3. Single-Line Diagram PDF
    sld_pdf = app_dir / "single_line_diagram.pdf"
    draw_single_line_diagram(
        sld_pdf,
        project_name=f"{applicant_name} ({capacity_kw:.0f} kW)",
        inverter_specs=f"{inverter_model} ({capacity_kw:.0f} kW total)",
        include_disconnect_switch=has_compliant_switch,
    )

    # 4. Grid Telemetry JSON
    telemetry_data = {
        "feeder_id": feeder_id,
        "utility": utility_name,
        "nominal_voltage_kv": 12.47,
        "annual_peak_load_kw": feeder_peak_kw,
        "minimum_daytime_load_kw": feeder_mdl_kw,
        "existing_connected_generation_kw": existing_gen_kw,
        "proposed_project_capacity_kw": capacity_kw,
        "substation_transformer_rating_kva": 10000.0,
        "available_fault_duty_mva": 180.0,
    }
    telemetry_file = app_dir / "grid_telemetry.json"
    telemetry_file.write_text(json.dumps(telemetry_data, indent=2), encoding="utf-8")

    total_gen_kw = existing_gen_kw + capacity_kw
    penetration_pct = round((total_gen_kw / feeder_peak_kw) * 100.0, 2)

    return {
        "application_id": app_id,
        "applicant_name": applicant_name,
        "project_type": project_type,
        "capacity_kw": capacity_kw,
        "utility": utility_name,
        "feeder_id": feeder_id,
        "calculated_penetration_pct": penetration_pct,
        "expected_outcome": expected_outcome,
        "failing_screens": failing_screens,
        "required_citations": citations,
        "files": {
            "application_form": "application_form.pdf",
            "inverter_cutsheet": "inverter_cutsheet.pdf",
            "single_line_diagram": "single_line_diagram.pdf",
            "grid_telemetry": "grid_telemetry.json",
        },
    }


def generate_all_applications() -> None:
    """Generate the four standardized benchmark applications."""
    catalog: dict[str, dict] = {"applications": {}}

    app1 = generate_application_package(
        app_id="APP-001-PASS-ROOFTOP-SOLAR",
        applicant_name="SunTech Logistics LLC",
        site_address="1420 Mission Blvd, Fremont, CA 94539",
        utility_name="Pacific Gas & Electric (PG&E)",
        account_number="98234-7712",
        project_type="Commercial Rooftop Solar PV",
        capacity_kw=250.0,
        service_voltage="480V 3-Phase",
        feeder_id="Fremont-12-04",
        feeder_peak_kw=4500.0,
        feeder_mdl_kw=1800.0,
        existing_gen_kw=200.0,
        inverter_model="SMA Sunny Tripower CORE1 50-US",
        inverter_cert="UL 1741 Supplement SB, IEEE 1547-2018, CPUC Rule 21 Compliant",
        inverter_pf="0.80 leading to 0.80 lagging",
        has_compliant_switch=True,
        expected_outcome="FAST_TRACK_APPROVED",
        failing_screens=[],
        citations=[
            "Rule 21 Section C.1",
            "Rule 21 Section D Screen D",
            "IEEE 1547-2018 Clause 5.1",
        ],
    )
    catalog["applications"][app1["application_id"]] = app1

    app2 = generate_application_package(
        app_id="APP-002-FAIL-PENETRATION-15PCT",
        applicant_name="Golden State Agripower Inc.",
        site_address="8800 Central Valley Highway, Bakersfield, CA 93308",
        utility_name="Southern California Edison (SCE)",
        account_number="44109-8821",
        project_type="Ground-Mount Solar Farm",
        capacity_kw=1200.0,
        service_voltage="480V 3-Phase",
        feeder_id="Kern-08-02",
        feeder_peak_kw=5000.0,
        feeder_mdl_kw=2100.0,
        existing_gen_kw=400.0,
        inverter_model="Sungrow SG250HX",
        inverter_cert="UL 1741-SB, IEEE 1547-2018, Rule 21 Compliant",
        inverter_pf="0.80 leading to 0.80 lagging",
        has_compliant_switch=True,
        expected_outcome="DEFICIENCY_ISSUED",
        failing_screens=["Screen D: Aggregate Feeder Penetration (15% Peak Load Screen)"],
        citations=["Rule 21 Section D Screen D", "Rule 21 Section C.2"],
    )
    catalog["applications"][app2["application_id"]] = app2

    app3 = generate_application_package(
        app_id="APP-003-FAIL-NONCERTIFIED-INV",
        applicant_name="Horizon Manufacturing Corp.",
        site_address="510 Industrial Way, Oakland, CA 94601",
        utility_name="Pacific Gas & Electric (PG&E)",
        account_number="11204-6632",
        project_type="Industrial Solar PV",
        capacity_kw=500.0,
        service_voltage="480V 3-Phase",
        feeder_id="Coliseum-04-11",
        feeder_peak_kw=6200.0,
        feeder_mdl_kw=2800.0,
        existing_gen_kw=150.0,
        inverter_model="SunMaster Pro 100K (Legacy)",
        inverter_cert="UL 1741 (2010 Basic Edition only - Lacks UL 1741-SB and IEEE 1547-2018)",
        inverter_pf="Fixed 1.0 (Unity) Power Factor only",
        has_compliant_switch=True,
        expected_outcome="DEFICIENCY_ISSUED",
        failing_screens=["Screen B: Certified Equipment (Inverter Compliance)"],
        citations=[
            "Rule 21 Section D Screen B",
            "IEEE 1547-2018 Clause 5.1",
            "Rule 21 Section C.2",
        ],
    )
    catalog["applications"][app3["application_id"]] = app3

    app4 = generate_application_package(
        app_id="APP-004-FAIL-MISSING-DISCONNECT",
        applicant_name="Pacific Coast Storage Partners",
        site_address="700 Harbor Dr, San Diego, CA 92101",
        utility_name="San Diego Gas & Electric (SDG&E)",
        account_number="55219-3384",
        project_type="Battery Energy Storage System (BESS)",
        capacity_kw=750.0,
        service_voltage="480V 3-Phase",
        feeder_id="Coronado-21-06",
        feeder_peak_kw=8000.0,
        feeder_mdl_kw=3500.0,
        existing_gen_kw=300.0,
        inverter_model="Tesla Megapack 2XL Inverter Block",
        inverter_cert="UL 1741-SB, IEEE 1547-2018, CPUC Rule 21 Compliant",
        inverter_pf="0.80 leading to 0.80 lagging",
        has_compliant_switch=False,
        expected_outcome="DEFICIENCY_ISSUED",
        failing_screens=["Screen H: Manual Disconnect Switch and Safety Requirements"],
        citations=["Rule 21 Section D Screen H", "Rule 21 Section C.2"],
    )
    catalog["applications"][app4["application_id"]] = app4

    index_file = DATASET_DIR / "dataset_index.json"
    index_file.write_text(json.dumps(catalog, indent=2), encoding="utf-8")


def main() -> None:
    print("Compiling regulatory tariffs from Markdown...")
    compile_tariffs_from_markdown()
    print("Generating benchmark applications...")
    generate_all_applications()
    print("Benchmark compilation complete!")


if __name__ == "__main__":
    main()
