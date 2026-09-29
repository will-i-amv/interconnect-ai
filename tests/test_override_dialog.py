"""Automated unit tests for human-in-the-loop override records and audit logging (T-114)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from frontend.api_client import InterconnectApiClient
from frontend.components.override_dialog import EngineerSignoffRecord
from src.agents.state import AuditAction, AuditEntry, WorkflowStep
from src.schemas.screening import OverallOutcome
from src.utils.dataset import load_application_schema


def test_engineer_signoff_record_schema() -> None:
    """Verify EngineerSignoffRecord model validations and immutable configuration."""
    rec = EngineerSignoffRecord(
        application_id="APP-001-PASS-ROOFTOP-SOLAR",
        engineer_name="Elena Rostova, PE",
        pe_license_number="PE-CA-104928",
        decision="APPROVE_FAST_TRACK",
        rationale="All 8 California Rule 21 fast-track screens verified without deficiencies.",
        modified_parameters={"capacity_kw": 250.0},
    )

    assert rec.application_id == "APP-001-PASS-ROOFTOP-SOLAR"
    assert rec.engineer_name == "Elena Rostova, PE"
    assert rec.pe_license_number == "PE-CA-104928"
    assert rec.decision == "APPROVE_FAST_TRACK"
    assert len(rec.timestamp_utc) > 10

    # Model is frozen (immutable)
    with pytest.raises(ValidationError):
        rec.engineer_name = "New Name"  # type: ignore[misc]

    # Forbids extra fields
    with pytest.raises(ValidationError):
        EngineerSignoffRecord(
            application_id="APP-001",
            engineer_name="Test",
            pe_license_number="123",
            decision="APPROVE",
            rationale="Test",
            unrecognized_field=123,  # type: ignore[call-arg]
        )


def test_human_override_parameter_correction_recalculation() -> None:
    """Verify that applying parameter overrides alters deterministic calculation outcomes.

    Specifically, take APP-002-FAIL-PENETRATION-15PCT (1200 kW on a 5000 kW feeder = 28%),
    which normally fails Screen D.
    Override export capacity down to 200 kW, which reduces aggregate penetration to 8% (< 15%).
    Verify the recalculated outcome shifts from DEFICIENCY_ISSUED to FAST_TRACK_APPROVED!
    """
    client = InterconnectApiClient(base_url="http://127.0.0.1:9999")  # Local engine

    # Baseline run fails Screen D
    baseline_result = client.run_screening("APP-002-FAIL-PENETRATION-15PCT")
    assert baseline_result["overall_outcome"] == OverallOutcome.DEFICIENCY_ISSUED.value
    assert len(baseline_result["deficiencies"]) >= 1

    # Engineer overrides capacity from 1200 kW to 200 kW
    base_schema = load_application_schema("APP-002-FAIL-PENETRATION-15PCT")
    overridden_schema = base_schema.model_copy(
        update={
            "total_export_capacity_kw": 200.0,
            "inverters": [base_schema.inverters[0].model_copy(update={"rated_ac_power_kw": 200.0})],
        }
    )

    # Re-run screening with overridden schema
    overridden_result = client.run_screening(
        "APP-002-FAIL-PENETRATION-15PCT",
        custom_schema=overridden_schema.model_dump(mode="json"),
    )

    # Screen D now passes, yielding FAST_TRACK_APPROVED!
    assert overridden_result["overall_outcome"] == OverallOutcome.FAST_TRACK_APPROVED.value
    assert len(overridden_result["deficiencies"]) == 0
    assert overridden_result["requires_human_override"] is False


def test_audit_entry_recording_for_human_override() -> None:
    """Verify AuditEntry captures OVERRIDE_APPLIED actions under WorkflowStep.HUMAN_REVIEW."""
    entry = AuditEntry(
        step=WorkflowStep.HUMAN_REVIEW,
        action=AuditAction.OVERRIDE_APPLIED,
        message="Manual override applied by Marcus Brody, PE: verified secondary breaker kAIC",
        details={"pe_license": "PE-CA-554433", "breaker_kaic": 65.0},
    )

    data = entry.model_dump(mode="json")
    assert data["step"] == "HUMAN_REVIEW"
    assert data["action"] == "OVERRIDE_APPLIED"
    assert "Marcus Brody" in data["message"]
    assert data["details"]["pe_license"] == "PE-CA-554433"
