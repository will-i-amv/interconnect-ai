"""Tests for benchmark dataset integrity, schemas, and PDF extraction."""

import pymupdf
import pytest

from src.utils.dataset import (
    get_dataset_root,
    get_tariff_path,
    list_applications,
    load_application,
    load_dataset_catalog,
)


@pytest.fixture(scope="session", autouse=True)
def ensure_benchmark_data_compiled() -> None:
    """Ensure benchmark dataset is compiled from Markdown before tests run."""
    import scripts.generate_benchmark_data as generator

    rule21_pdf = get_dataset_root() / "tariffs" / "ca_rule_21_extract.pdf"
    catalog_json = get_dataset_root() / "dataset_index.json"
    if not rule21_pdf.is_file() or not catalog_json.is_file():
        generator.compile_tariffs_from_markdown()
        generator.generate_all_applications()


def test_dataset_catalog_structure() -> None:
    """Verify master catalog index format and required keys."""
    catalog = load_dataset_catalog()
    assert "applications" in catalog, "Catalog missing 'applications' root key"
    apps = catalog["applications"]
    assert len(apps) == 4, f"Expected 4 benchmark applications, found {len(apps)}"

    expected_ids = {
        "APP-001-PASS-ROOFTOP-SOLAR",
        "APP-002-FAIL-PENETRATION-15PCT",
        "APP-003-FAIL-NONCERTIFIED-INV",
        "APP-004-FAIL-MISSING-DISCONNECT",
    }
    assert set(apps.keys()) == expected_ids

    for app_id, entry in apps.items():
        assert entry["application_id"] == app_id
        assert entry["capacity_kw"] > 0
        assert entry["expected_outcome"] in {"FAST_TRACK_APPROVED", "DEFICIENCY_ISSUED"}
        assert "calculated_penetration_pct" in entry
        assert "required_citations" in entry
        assert len(entry["required_citations"]) > 0


def test_list_applications_utility() -> None:
    """Verify list_applications returns sorted list matching catalog."""
    apps = list_applications()
    assert len(apps) == 4
    assert apps[0] == "APP-001-PASS-ROOFTOP-SOLAR"


def test_application_packages_integrity() -> None:
    """Verify each application folder contains all 4 required files."""
    for app_id in list_applications():
        pkg = load_application(app_id)

        assert pkg["application_form_path"].is_file(), f"Missing form in {app_id}"
        assert pkg["inverter_cutsheet_path"].is_file(), f"Missing cutsheet in {app_id}"
        assert pkg["single_line_diagram_path"].is_file(), f"Missing SLD in {app_id}"
        assert pkg["telemetry_path"].is_file(), f"Missing telemetry in {app_id}"

        # Verify grid telemetry contents
        telemetry = pkg["telemetry"]
        assert telemetry["annual_peak_load_kw"] > 0
        assert telemetry["minimum_daytime_load_kw"] > 0
        assert telemetry["nominal_voltage_kv"] == 12.47
        assert telemetry["proposed_project_capacity_kw"] == pkg["metadata"]["capacity_kw"]


def test_pdf_readability_and_text_extraction() -> None:
    """Verify that all generated PDFs can be opened and contain extractable text."""
    for app_id in list_applications():
        pkg = load_application(app_id)

        # Form PDF
        doc_form = pymupdf.open(pkg["application_form_path"])
        assert len(doc_form) >= 1
        form_text = "".join(page.get_text() for page in doc_form)
        assert pkg["metadata"]["applicant_name"] in form_text
        doc_form.close()

        # Inverter Cutsheet PDF
        doc_cut = pymupdf.open(pkg["inverter_cutsheet_path"])
        assert len(doc_cut) >= 1
        cut_text = "".join(page.get_text() for page in doc_cut)
        assert "Power Factor" in cut_text or "Manufacturer" in cut_text
        doc_cut.close()

        # Single Line Diagram PDF
        doc_sld = pymupdf.open(pkg["single_line_diagram_path"])
        assert len(doc_sld) >= 1
        sld_text = "".join(page.get_text() for page in doc_sld)
        assert "SINGLE-LINE DIAGRAM" in sld_text
        doc_sld.close()


def test_tariff_documents_exist_and_readable() -> None:
    """Verify tariff handbooks exist and contain critical screen definitions."""
    dataset_root = get_dataset_root()
    tariffs_dir = dataset_root / "tariffs"

    expected_files = [
        "ca_rule_21_extract.md",
        "ca_rule_21_extract.pdf",
        "ieee_1547_2018_extract.md",
        "ieee_1547_2018_extract.pdf",
        "ferc_order_2023_sgip.md",
    ]
    for filename in expected_files:
        path = tariffs_dir / filename
        assert path.is_file(), f"Missing tariff file {path}"

    # Verify Rule 21 PDF
    rule21_pdf = get_tariff_path("ca_rule_21_extract.pdf")
    doc_r21 = pymupdf.open(rule21_pdf)
    r21_text = "".join(page.get_text() for page in doc_r21)
    doc_r21.close()

    assert "Screen B" in r21_text
    assert "Screen D" in r21_text
    assert "15%" in r21_text
    assert "Screen H" in r21_text

    # Verify IEEE 1547 PDF
    ieee_pdf = get_tariff_path("ieee_1547_2018_extract.pdf")
    doc_ieee = pymupdf.open(ieee_pdf)
    ieee_text = "".join(page.get_text() for page in doc_ieee)
    doc_ieee.close()

    assert "Clause 5.1" in ieee_text
    assert "Anti-Islanding" in ieee_text or "Clause 8.1" in ieee_text


def test_invalid_application_lookup() -> None:
    """Verify that nonexistent application lookup raises KeyError."""
    with pytest.raises(KeyError, match="Application 'APP-NONEXISTENT' not found"):
        load_application("APP-NONEXISTENT")
