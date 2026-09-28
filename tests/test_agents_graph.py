"""Automated tests for LangGraph state machine, audit log, and error rollback (T-107)."""

from __future__ import annotations

import pytest

from src.agents.graph import create_interconnection_graph
from src.agents.state import (
    AuditAction,
    InterconnectionState,
    WorkflowStep,
)
from src.schemas.application import (
    ApplicationSchema,
    DisconnectSwitchLocation,
    FeederTelemetrySchema,
    InterconnectionType,
    InverterSchema,
    SLDComponentSchema,
    TransformerSchema,
)
from src.schemas.screening import OverallOutcome, ScreenId, ScreenStatus
from src.utils.dataset import load_application, load_dataset_catalog


def build_test_application(app_id: str) -> ApplicationSchema:
    """Construct a validated ApplicationSchema from benchmark catalog and telemetry."""
    catalog = load_dataset_catalog()
    entry = catalog["applications"][app_id]
    pkg = load_application(app_id)
    telemetry_raw = pkg["telemetry"]

    inv = InverterSchema(
        manufacturer="SMA Solar",
        model_name="Sunny Tripower",
        rated_ac_power_kw=entry["capacity_kw"],
        nominal_voltage_v=480.0,
        max_continuous_current_a=entry["capacity_kw"] * 1000 / (480 * 1.732),
        ul_1741_sb_certified="FAIL-NONCERTIFIED" not in app_id,
        ieee_1547_2018_compliant="FAIL-NONCERTIFIED" not in app_id,
        count=1,
    )

    telemetry = FeederTelemetrySchema(
        feeder_id=entry.get("feeder_id", "FEEDER-01"),
        utility=entry["utility"],
        nominal_voltage_kv=telemetry_raw.get("distribution_voltage_kv", 12.47),
        annual_peak_load_kw=telemetry_raw.get("feeder_peak_load_kw", 5000.0),
        minimum_daytime_load_kw=telemetry_raw.get("daytime_min_load_kw", 2000.0),
        existing_connected_generation_kw=telemetry_raw.get("existing_der_kw", 200.0),
    )

    sld = SLDComponentSchema(
        has_utility_disconnect_switch="MISSING-DISCONNECT" not in app_id,
        disconnect_switch_visible_break="MISSING-DISCONNECT" not in app_id,
        disconnect_switch_lockable="MISSING-DISCONNECT" not in app_id,
        disconnect_switch_location=(
            DisconnectSwitchLocation.NOT_DEPICTED
            if "MISSING-DISCONNECT" in app_id
            else DisconnectSwitchLocation.ADJACENT_TO_METER
        ),
        main_breaker_rating_a=max(400.0, (entry["capacity_kw"] * 1000 / (480 * 1.732)) * 1.25),
        main_breaker_kaic=65.0,
    )

    tx_rating = max(1000.0, entry["capacity_kw"] * 1.25)
    transformer = TransformerSchema(
        rating_kva=tx_rating,
        primary_voltage_kv=12.47,
        secondary_voltage_v=480.0,
        impedance_pct_z=2.5,
    )

    return ApplicationSchema(
        application_id=app_id,
        applicant_name=entry["applicant_name"],
        site_address="123 Solar Way",
        utility_provider=entry["utility"],
        utility_account_number="ACCT-98765",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=entry["capacity_kw"],
        service_voltage="480V 3-Phase",
        inverters=[inv],
        transformer=transformer,
        sld_components=sld,
        feeder_telemetry=telemetry,
    )


@pytest.fixture
def pass_application() -> ApplicationSchema:
    """Fixture returning validated APP-001-PASS-ROOFTOP-SOLAR schema."""
    return build_test_application("APP-001-PASS-ROOFTOP-SOLAR")


@pytest.fixture
def fail_penetration_application() -> ApplicationSchema:
    """Fixture returning validated APP-002-FAIL-PENETRATION-15PCT schema."""
    return build_test_application("APP-002-FAIL-PENETRATION-15PCT")


def test_graph_compilation_and_topology() -> None:
    """Verify that StateGraph compiles and all expected nodes are present."""
    graph = create_interconnection_graph()
    nodes = set(graph.nodes.keys())
    expected_nodes = {
        "__start__",
        "intake",
        "extraction",
        "retrieval",
        "screening",
        "synthesis",
        "human_review",
        "error_rollback",
    }
    assert expected_nodes.issubset(nodes)


def test_pass_application_full_workflow(pass_application: ApplicationSchema) -> None:
    """Verify clean approval workflow for compliant rooftop solar application."""
    graph = create_interconnection_graph()
    initial_state: InterconnectionState = {
        "application_id": pass_application.application_id,
        "raw_documents": ["application_form.json", "sld_diagram.pdf"],
        "application_data": pass_application,
        "retrieved_citations": [],
        "screen_results": [],
        "deficiencies": [],
        "errors": [],
        "audit_log": [],
    }

    config = {"configurable": {"thread_id": "thread-pass-test-1"}}
    final_state = graph.invoke(initial_state, config=config)

    # Outcome assertions
    assert final_state["overall_outcome"] == OverallOutcome.FAST_TRACK_APPROVED
    assert final_state["screening_report"] is not None
    assert final_state["screening_report"].overall_outcome == OverallOutcome.FAST_TRACK_APPROVED
    assert not final_state["deficiencies"]
    assert not final_state["requires_human_override"]

    # Screen evaluations
    screen_results = final_state["screen_results"]
    assert len(screen_results) == 8
    for screen in screen_results:
        assert screen.status == ScreenStatus.PASS

    # Citation grounding
    citations = final_state["retrieved_citations"]
    assert len(citations) >= 2
    citation_ids = [c.citation_id for c in citations]
    assert any("RULE21_SCREEN_D" in cid for cid in citation_ids)

    # Audit trail verification
    audit_log = final_state["audit_log"]
    assert len(audit_log) >= 5
    actions = [entry.action for entry in audit_log]
    assert AuditAction.STATE_TRANSITION in actions
    assert AuditAction.CITATION_RETRIEVED in actions
    assert AuditAction.SCREEN_EVALUATED in actions


def test_fail_application_deficiency_workflow(
    fail_penetration_application: ApplicationSchema,
) -> None:
    """Verify deficiency issuance and human review routing for failing application."""
    graph = create_interconnection_graph()
    initial_state: InterconnectionState = {
        "application_id": fail_penetration_application.application_id,
        "raw_documents": ["application_form.json"],
        "application_data": fail_penetration_application,
        "retrieved_citations": [],
        "screen_results": [],
        "deficiencies": [],
        "errors": [],
        "audit_log": [],
    }

    config = {"configurable": {"thread_id": "thread-fail-test-1"}}
    final_state = graph.invoke(initial_state, config=config)

    # Outcome assertions
    assert final_state["overall_outcome"] == OverallOutcome.DEFICIENCY_ISSUED
    assert final_state["screening_report"] is not None
    assert final_state["requires_human_override"] is True
    assert final_state["current_step"] == WorkflowStep.HUMAN_REVIEW

    # Verify Screen D deficiency
    assert len(final_state["deficiencies"]) >= 1
    deficiency = final_state["deficiencies"][0]
    assert deficiency.violating_screen == ScreenId.SCREEN_D_PENETRATION_15PCT
    assert deficiency.cure_deadline_business_days == 10
    assert "Supplemental Review" in deficiency.required_cure_action


def test_error_rollback_on_missing_intake_id() -> None:
    """Verify error rollback node catches missing application_id and prevents crash."""
    graph = create_interconnection_graph()
    initial_state: InterconnectionState = {
        "raw_documents": ["orphaned_doc.pdf"],
        "retrieved_citations": [],
        "screen_results": [],
        "deficiencies": [],
        "errors": [],
        "audit_log": [],
    }

    config = {"configurable": {"thread_id": "thread-error-test-1"}}
    final_state = graph.invoke(initial_state, config=config)

    assert final_state["current_step"] == WorkflowStep.ERROR
    assert final_state["requires_human_override"] is True
    assert len(final_state["errors"]) >= 1
    assert "application_id" in final_state["errors"][0]

    # Verify audit log recorded rollback
    actions = [entry.action for entry in final_state["audit_log"]]
    assert AuditAction.ROLLBACK_TRIGGERED in actions


def test_checkpointer_thread_isolation(pass_application: ApplicationSchema) -> None:
    """Verify LangGraph checkpointer isolates state by thread_id and allows state querying."""
    graph = create_interconnection_graph()

    # Thread 1
    config_1 = {"configurable": {"thread_id": "isolation-thread-1"}}
    graph.invoke(
        {
            "application_id": "APP-ISOLATION-001",
            "application_data": pass_application,
            "retrieved_citations": [],
            "screen_results": [],
            "deficiencies": [],
            "errors": [],
            "audit_log": [],
        },
        config=config_1,
    )

    # Thread 2
    config_2 = {"configurable": {"thread_id": "isolation-thread-2"}}
    graph.invoke(
        {
            "application_id": "APP-ISOLATION-002",
            "application_data": pass_application,
            "retrieved_citations": [],
            "screen_results": [],
            "deficiencies": [],
            "errors": [],
            "audit_log": [],
        },
        config=config_2,
    )

    state_1 = graph.get_state(config_1)
    state_2 = graph.get_state(config_2)

    assert state_1.values["application_id"] == "APP-ISOLATION-001"
    assert state_2.values["application_id"] == "APP-ISOLATION-002"
