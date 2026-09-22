"""Unit tests for Pydantic technical application and screening schemas."""

import pytest
from pydantic import ValidationError

from src.schemas import (
    ApplicationSchema,
    DeficiencyItem,
    DisconnectSwitchLocation,
    FeederTelemetrySchema,
    InterconnectionType,
    InverterSchema,
    OverallOutcome,
    ScreenId,
    ScreeningReport,
    ScreenResult,
    ScreenStatus,
    SLDComponentSchema,
    TransformerSchema,
)
from src.utils.dataset import load_dataset_catalog


def test_inverter_schema_valid() -> None:
    """Verify valid inverter specification instantiation."""
    inv = InverterSchema(
        manufacturer="SMA",
        model_name="Sunny Tripower CORE1 50-US",
        rated_ac_power_kw=50.0,
        nominal_voltage_v=480.0,
        max_continuous_current_a=60.2,
        power_factor_min=-0.80,
        power_factor_max=0.80,
        ul_1741_sb_certified=True,
        ieee_1547_2018_compliant=True,
        count=5,
    )
    assert inv.total_capacity_kw == 250.0
    assert inv.ul_1741_sb_certified is True


def test_inverter_schema_validation_rules() -> None:
    """Verify bounds and validation errors on invalid inverter inputs."""
    # Negative capacity
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        InverterSchema(
            manufacturer="SMA",
            model_name="CORE1",
            rated_ac_power_kw=-10.0,
            nominal_voltage_v=480.0,
            max_continuous_current_a=50.0,
            ul_1741_sb_certified=True,
            ieee_1547_2018_compliant=True,
        )

    # Power factor out of [-1.0, 1.0] range
    with pytest.raises(ValidationError, match="Input should be less than or equal to 1"):
        InverterSchema(
            manufacturer="SMA",
            model_name="CORE1",
            rated_ac_power_kw=50.0,
            nominal_voltage_v=480.0,
            max_continuous_current_a=50.0,
            power_factor_max=1.5,
            ul_1741_sb_certified=True,
            ieee_1547_2018_compliant=True,
        )


def test_extra_forbid_configuration() -> None:
    """Verify extra='forbid' rejects unexpected fields to prevent LLM hallucinations."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InverterSchema(
            manufacturer="SMA",
            model_name="CORE1",
            rated_ac_power_kw=50.0,
            nominal_voltage_v=480.0,
            max_continuous_current_a=50.0,
            ul_1741_sb_certified=True,
            ieee_1547_2018_compliant=True,
            hallucinated_field="forbidden_value",  # type: ignore[call-arg]
        )


def test_frozen_immutability() -> None:
    """Verify frozen=True prevents accidental in-place attribute mutations."""
    inv = InverterSchema(
        manufacturer="SMA",
        model_name="CORE1",
        rated_ac_power_kw=50.0,
        nominal_voltage_v=480.0,
        max_continuous_current_a=50.0,
        ul_1741_sb_certified=True,
        ieee_1547_2018_compliant=True,
    )
    with pytest.raises(ValidationError, match="Instance is frozen"):
        inv.rated_ac_power_kw = 100.0  # type: ignore[misc]

    # Functional copy works
    updated_inv = inv.model_copy(update={"rated_ac_power_kw": 100.0})
    assert updated_inv.rated_ac_power_kw == 100.0
    assert inv.rated_ac_power_kw == 50.0


def test_application_schema_capacity_validator() -> None:
    """Verify model validator checks total inverter capacity vs declared export capacity."""
    inv = InverterSchema(
        manufacturer="SMA",
        model_name="CORE1",
        rated_ac_power_kw=50.0,
        nominal_voltage_v=480.0,
        max_continuous_current_a=50.0,
        ul_1741_sb_certified=True,
        ieee_1547_2018_compliant=True,
        count=2,  # 100 kW total
    )

    # Inverters provide 100 kW, but application claims 250 kW export -> should fail
    with pytest.raises(ValidationError, match="cannot be less than declared export capacity"):
        ApplicationSchema(
            application_id="APP-TEST-001",
            applicant_name="Acme Solar",
            site_address="123 Sunny St",
            utility_provider="PG&E",
            utility_account_number="12345",
            project_type=InterconnectionType.SOLAR_PV,
            total_export_capacity_kw=250.0,
            service_voltage="480V 3-Phase",
            inverters=[inv],
        )


def test_screening_report_and_deficiency_lifecycle() -> None:
    """Verify complete screening report composition, calculations, and serialization."""
    screen_d = ScreenResult(
        screen_id=ScreenId.SCREEN_D_PENETRATION_15PCT,
        screen_name="Aggregate Feeder Penetration (15% Peak Load Screen)",
        status=ScreenStatus.FAIL,
        calculated_value=32.0,
        threshold_value=15.0,
        citation="Rule 21 Section D Screen D",
        reasoning=(
            "Aggregate generation of 1,600 kW exceeds 15% of 5,000 kW feeder peak load (32%)."
        ),
    )
    screen_b = ScreenResult(
        screen_id=ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
        screen_name="Certified Inverter Equipment",
        status=ScreenStatus.PASS,
        calculated_value="UL 1741-SB",
        threshold_value="UL 1741-SB / IEEE 1547-2018",
        citation="Rule 21 Section D Screen B",
        reasoning="Inverters verified on CEC listing.",
    )

    deficiency = DeficiencyItem(
        code="DEF_SCREEN_D_PENETRATION_EXCEEDED",
        title="Feeder Penetration Limit Exceeded (15% Screen)",
        description="The proposed generation exceeds 15% of the annual line peak load.",
        violating_screen=ScreenId.SCREEN_D_PENETRATION_15PCT,
        required_cure_action=(
            "Submit for Supplemental Review (Screens N, O, P) or reduce export limit."
        ),
        cure_deadline_business_days=10,
        tariff_citation="Rule 21 Section D Screen D and Section C.2",
    )

    report = ScreeningReport(
        application_id="APP-002-FAIL-PENETRATION-15PCT",
        overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
        screens=[screen_d, screen_b],
        deficiencies=[deficiency],
        aggregate_generation_kw=1600.0,
        feeder_penetration_pct=32.0,
    )

    assert report.has_deficiencies is True
    assert report.passed_screens_count == 1
    assert report.failed_screens_count == 1

    # Round-trip JSON serialization
    json_str = report.model_dump_json()
    loaded_report = ScreeningReport.model_validate_json(json_str)
    assert loaded_report.application_id == report.application_id
    assert loaded_report.overall_outcome == OverallOutcome.DEFICIENCY_ISSUED
    assert loaded_report.screens[0].status == ScreenStatus.FAIL


def test_benchmark_catalog_validation() -> None:
    """Verify that all 4 benchmark catalog cases can be parsed into ApplicationSchema."""
    catalog = load_dataset_catalog()
    apps = catalog["applications"]

    for app_id, entry in apps.items():
        inv = InverterSchema(
            manufacturer="Industrial Power Systems",
            model_name="Benchmark Inverter",
            rated_ac_power_kw=entry["capacity_kw"],
            nominal_voltage_v=480.0,
            max_continuous_current_a=entry["capacity_kw"] * 1000 / (480 * 1.732),
            ul_1741_sb_certified="FAIL-NONCERTIFIED" not in app_id,
            ieee_1547_2018_compliant="FAIL-NONCERTIFIED" not in app_id,
            count=1,
        )

        telemetry = FeederTelemetrySchema(
            feeder_id=entry["feeder_id"],
            utility=entry["utility"],
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=5000.0,
            minimum_daytime_load_kw=2000.0,
            existing_connected_generation_kw=200.0,
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
            main_breaker_rating_a=400.0,
            main_breaker_kaic=65.0,
        )

        transformer = TransformerSchema(
            rating_kva=1000.0,
            primary_voltage_kv=12.47,
            secondary_voltage_v=480.0,
            impedance_pct_z=5.75,
        )

        app = ApplicationSchema(
            application_id=app_id,
            applicant_name=entry["applicant_name"],
            site_address="Benchmark Location",
            utility_provider=entry["utility"],
            utility_account_number="ACCT-12345",
            project_type=InterconnectionType.SOLAR_PV,
            total_export_capacity_kw=entry["capacity_kw"],
            service_voltage="480V 3-Phase",
            inverters=[inv],
            transformer=transformer,
            sld_components=sld,
            feeder_telemetry=telemetry,
        )

        assert app.application_id == app_id
        assert app.total_export_capacity_kw == entry["capacity_kw"]
