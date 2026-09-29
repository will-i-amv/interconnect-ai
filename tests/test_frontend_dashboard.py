"""Automated unit tests for Streamlit frontend API client and dashboard utilities (T-112)."""

from __future__ import annotations

from frontend.api_client import InterconnectApiClient
from frontend.styles import CUSTOM_CSS
from src.schemas.screening import OverallOutcome


def test_custom_css_tokens() -> None:
    """Verify frontend CSS contains required styling classes and design tokens."""
    assert ".metric-container" in CUSTOM_CSS
    assert ".badge-pass" in CUSTOM_CSS
    assert ".badge-fail" in CUSTOM_CSS
    assert ".app-card" in CUSTOM_CSS
    assert "Inter" in CUSTOM_CSS
    assert "JetBrains Mono" in CUSTOM_CSS


def test_api_client_catalog_retrieval() -> None:
    """Verify API client retrieves the complete benchmark catalog."""
    client = InterconnectApiClient(base_url="http://127.0.0.1:9999")  # Force fallback
    apps = client.get_applications_catalog()

    assert isinstance(apps, list)
    assert len(apps) >= 4

    app_ids = [a["application_id"] for a in apps]
    assert "APP-001-PASS-ROOFTOP-SOLAR" in app_ids
    assert "APP-002-FAIL-PENETRATION-15PCT" in app_ids
    assert "APP-003-FAIL-NONCERTIFIED-INV" in app_ids
    assert "APP-004-FAIL-MISSING-DISCONNECT" in app_ids

    # Validate essential fields
    sample = apps[0]
    for field in ("application_id", "applicant_name", "capacity_kw", "utility", "expected_outcome"):
        assert field in sample


def test_api_client_application_details() -> None:
    """Verify API client loads detailed telemetry, documents, and schema."""
    client = InterconnectApiClient(base_url="http://127.0.0.1:9999")  # Force fallback
    details = client.get_application_details("APP-001-PASS-ROOFTOP-SOLAR")

    assert details["application_id"] == "APP-001-PASS-ROOFTOP-SOLAR"
    assert "telemetry" in details
    has_voltage = (
        "nominal_voltage_kv" in details["telemetry"]
        or "distribution_voltage_kv" in details["telemetry"]
    )
    assert has_voltage
    assert "files" in details
    assert "single_line_diagram" in details["files"]
    assert details["structured_schema"] is not None
    assert details["structured_schema"]["total_export_capacity_kw"] == 250.0


def test_api_client_screening_pass_execution() -> None:
    """Verify API client executes screening on a clean pass application."""
    client = InterconnectApiClient(base_url="http://127.0.0.1:9999")  # Force fallback
    result = client.run_screening("APP-001-PASS-ROOFTOP-SOLAR")

    assert result["application_id"] == "APP-001-PASS-ROOFTOP-SOLAR"
    assert result["overall_outcome"] == OverallOutcome.FAST_TRACK_APPROVED.value
    assert len(result["screen_results"]) == 8
    assert len(result["deficiencies"]) == 0
    assert result["formal_letter_markdown"] is not None
    assert "APPROVAL NOTICE" in result["formal_letter_markdown"]


def test_api_client_screening_deficiency_execution() -> None:
    """Verify API client executes screening and catches deficiencies on APP-002."""
    client = InterconnectApiClient(base_url="http://127.0.0.1:9999")  # Force fallback
    result = client.run_screening("APP-002-FAIL-PENETRATION-15PCT")

    assert result["application_id"] == "APP-002-FAIL-PENETRATION-15PCT"
    assert result["overall_outcome"] == OverallOutcome.DEFICIENCY_ISSUED.value
    assert len(result["deficiencies"]) >= 1
    assert result["requires_human_override"] is True
