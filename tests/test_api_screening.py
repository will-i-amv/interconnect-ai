"""Automated test suite for FastAPI screening runner and streaming endpoints (T-111)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.schemas.application import (
    ApplicationSchema,
    DisconnectSwitchLocation,
    FeederTelemetrySchema,
    InterconnectionType,
    InverterSchema,
    SLDComponentSchema,
    TransformerSchema,
)
from src.schemas.screening import OverallOutcome, ScreenStatus


@pytest.fixture
def client() -> TestClient:
    """Provide a FastAPI TestClient instance."""
    return TestClient(app)


def test_health_check_endpoint(client: TestClient) -> None:
    """Verify GET /health returns service status and supported jurisdictions."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "InterconnectAI Screening API"
    assert "0.1.0" in data["version"]
    assert "CA_RULE_21" in data["supported_jurisdictions"]


def test_list_applications_catalog(client: TestClient) -> None:
    """Verify GET /api/applications returns catalog summary items."""
    response = client.get("/api/applications")
    assert response.status_code == 200
    apps = response.json()
    assert isinstance(apps, list)
    assert len(apps) >= 4

    app_ids = [item["application_id"] for item in apps]
    assert "APP-001-PASS-ROOFTOP-SOLAR" in app_ids
    assert "APP-002-FAIL-PENETRATION-15PCT" in app_ids

    first = apps[0]
    for key in (
        "application_id",
        "applicant_name",
        "project_type",
        "capacity_kw",
        "utility",
        "feeder_id",
        "expected_outcome",
    ):
        assert key in first


def test_get_application_details(client: TestClient) -> None:
    """Verify GET /api/applications/{app_id} returns detailed telemetry and schema."""
    response = client.get("/api/applications/APP-001-PASS-ROOFTOP-SOLAR")
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"] == "APP-001-PASS-ROOFTOP-SOLAR"
    assert "summary" in data
    assert "telemetry" in data
    assert "files" in data
    assert data["structured_schema"] is not None
    assert data["structured_schema"]["total_export_capacity_kw"] == 250.0


def test_get_application_details_not_found(client: TestClient) -> None:
    """Verify GET /api/applications/{app_id} returns 404 for unknown IDs."""
    response = client.get("/api/applications/APP-NON-EXISTENT-999")
    assert response.status_code == 404
    assert "not found in benchmark catalog" in response.json()["detail"]


def test_screen_run_pass_application(client: TestClient) -> None:
    """Verify POST /api/screen/run evaluates a clean pass application correctly."""
    payload = {"application_id": "APP-001-PASS-ROOFTOP-SOLAR"}
    response = client.post("/api/screen/run", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["application_id"] == "APP-001-PASS-ROOFTOP-SOLAR"
    assert data["overall_outcome"] == OverallOutcome.FAST_TRACK_APPROVED.value
    assert len(data["screen_results"]) == 8
    assert all(s["status"] == ScreenStatus.PASS.value for s in data["screen_results"])
    assert len(data["deficiencies"]) == 0
    assert data["formal_letter_markdown"] is not None
    assert "APPROVAL NOTICE" in data["formal_letter_markdown"]
    assert data["execution_time_ms"] > 0
    assert len(data["audit_log"]) > 0
    assert data["requires_human_override"] is False


def test_screen_run_fail_application(client: TestClient) -> None:
    """Verify POST /api/screen/run identifies penetration failure and deficiencies."""
    payload = {"application_id": "APP-002-FAIL-PENETRATION-15PCT"}
    response = client.post("/api/screen/run", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["application_id"] == "APP-002-FAIL-PENETRATION-15PCT"
    assert data["overall_outcome"] == OverallOutcome.DEFICIENCY_ISSUED.value
    assert len(data["deficiencies"]) >= 1
    assert data["requires_human_override"] is True
    assert data["formal_letter_markdown"] is not None
    assert "DEFICIENCY NOTICE" in data["formal_letter_markdown"]


def test_screen_run_unrecognized_app_without_schema(client: TestClient) -> None:
    """Verify POST /api/screen/run returns 404 when app is unknown and no schema provided."""
    payload = {"application_id": "APP-UNKNOWN-X"}
    response = client.post("/api/screen/run", json=payload)
    assert response.status_code == 404
    assert "not recognized in the benchmark catalog" in response.json()["detail"]


def test_screen_run_with_custom_schema(client: TestClient) -> None:
    """Verify POST /api/screen/run accepts an explicit custom application_data schema."""
    custom_app = ApplicationSchema(
        application_id="CUSTOM-UNIT-TEST-APP",
        applicant_name="Clean Power Corp",
        site_address="456 Grid Blvd",
        utility_provider="Pacific Gas & Electric (PG&E)",
        utility_account_number="ACCT-112233",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=100.0,
        service_voltage="480V 3-Phase",
        inverters=[
            InverterSchema(
                manufacturer="Enphase",
                model_name="IQ8+",
                rated_ac_power_kw=100.0,
                nominal_voltage_v=480.0,
                max_continuous_current_a=120.0,
                ul_1741_sb_certified=True,
                ieee_1547_2018_compliant=True,
                count=1,
            )
        ],
        transformer=TransformerSchema(
            rating_kva=500.0,
            primary_voltage_kv=12.47,
            secondary_voltage_v=480.0,
            impedance_pct_z=2.5,
        ),
        sld_components=SLDComponentSchema(
            has_utility_disconnect_switch=True,
            disconnect_switch_visible_break=True,
            disconnect_switch_lockable=True,
            disconnect_switch_location=DisconnectSwitchLocation.ADJACENT_TO_METER,
            main_breaker_rating_a=400.0,
            main_breaker_kaic=65.0,
        ),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-99",
            utility="Pacific Gas & Electric (PG&E)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=4000.0,
            minimum_daytime_load_kw=1500.0,
            existing_connected_generation_kw=50.0,
        ),
    )

    payload = {
        "application_id": "CUSTOM-UNIT-TEST-APP",
        "application_data": custom_app.model_dump(mode="json"),
    }
    response = client.post("/api/screen/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"] == "CUSTOM-UNIT-TEST-APP"
    assert data["overall_outcome"] == OverallOutcome.FAST_TRACK_APPROVED.value


def test_screen_stream_post_sse(client: TestClient) -> None:
    """Verify POST /api/screen/stream returns a streaming SSE sequence through completion."""
    payload = {"application_id": "APP-001-PASS-ROOFTOP-SOLAR"}
    with client.stream("POST", "/api/screen/stream", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events: list[dict[str, str]] = []
        current_event: str | None = None

        for line in response.iter_lines():
            line_str = line.strip() if isinstance(line, str) else line.decode("utf-8").strip()
            if not line_str:
                continue
            if line_str.startswith("event:"):
                current_event = line_str.replace("event:", "").strip()
            elif line_str.startswith("data:") and current_event:
                data_json = line_str.replace("data:", "").strip()
                events.append({"event": current_event, "data": data_json})
                current_event = None

        assert len(events) >= 3
        event_names = [e["event"] for e in events]
        assert "start" in event_names
        assert "node_complete" in event_names
        assert "done" in event_names

        # Parse node complete steps
        node_events = [e for e in events if e["event"] == "node_complete"]
        nodes_seen = [json.loads(e["data"])["node"] for e in node_events]
        assert "intake" in nodes_seen
        assert "screening" in nodes_seen
        assert "synthesis" in nodes_seen


def test_screen_stream_get_sse(client: TestClient) -> None:
    """Verify GET /api/screen/stream/{application_id} streams SSE for catalog items."""
    with client.stream("GET", "/api/screen/stream/APP-001-PASS-ROOFTOP-SOLAR") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        first_few_lines = []
        for line in response.iter_lines():
            line_str = line.strip() if isinstance(line, str) else line.decode("utf-8").strip()
            if line_str:
                first_few_lines.append(line_str)
            if len(first_few_lines) >= 4:
                break

        assert any("event: start" in line for line in first_few_lines)
