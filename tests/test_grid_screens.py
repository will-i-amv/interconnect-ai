"""Automated tests for deterministic distribution screening tools and grid calculators (T-108)."""

from __future__ import annotations

import pytest

from src.schemas.application import (
    ApplicationSchema,
    DisconnectSwitchLocation,
    FeederTelemetrySchema,
    InterconnectionType,
    InverterSchema,
    SLDComponentSchema,
    TransformerSchema,
)
from src.schemas.screening import (
    ScreenId,
    ScreenStatus,
)
from src.tools.grid_screens import (
    calculate_penetration_pct,
    calculate_rapid_voltage_change_pct,
    calculate_short_circuit_ratio,
    evaluate_screen_a_applicability,
    evaluate_screen_b_certified_equipment,
    evaluate_screen_c_voltage_drop,
    evaluate_screen_d_penetration_15pct,
    evaluate_screen_e_short_circuit_duty,
    evaluate_screen_f_short_circuit_ratio,
    evaluate_screen_h_disconnect_switch,
    evaluate_screen_i_anti_islanding,
    run_deterministic_screens,
)
from src.utils.dataset import load_application, load_dataset_catalog


def build_app(
    app_id: str = "TEST-APP-001",
    capacity_kw: float = 250.0,
    ul_certified: bool = True,
    ieee_compliant: bool = True,
    cec_listed: bool = True,
    trip_time_s: float = 2.0,
    peak_load_kw: float = 5000.0,
    existing_der_kw: float = 200.0,
    available_fault_duty_mva: float | None = 100.0,
    tx_rating_kva: float = 1000.0,
    tx_impedance_z: float = 2.5,
    has_disconnect: bool = True,
    disconnect_visible: bool = True,
    disconnect_lockable: bool = True,
    disconnect_location: DisconnectSwitchLocation = DisconnectSwitchLocation.ADJACENT_TO_METER,
    omit_sld: bool = False,
    omit_feeder: bool = False,
    omit_tx: bool = False,
) -> ApplicationSchema:
    """Helper factory for constructing custom ApplicationSchema instances."""
    inv = InverterSchema(
        manufacturer="SMA Solar",
        model_name="Sunny Tripower",
        rated_ac_power_kw=capacity_kw,
        nominal_voltage_v=480.0,
        max_continuous_current_a=(capacity_kw * 1000) / (480 * 1.732),
        ul_1741_sb_certified=ul_certified,
        ieee_1547_2018_compliant=ieee_compliant,
        anti_islanding_trip_time_s=trip_time_s,
        cec_listed=cec_listed,
        count=1,
    )

    sld = None
    if not omit_sld:
        sld = SLDComponentSchema(
            has_utility_disconnect_switch=has_disconnect,
            disconnect_switch_visible_break=disconnect_visible,
            disconnect_switch_lockable=disconnect_lockable,
            disconnect_switch_location=disconnect_location,
            main_breaker_rating_a=max(400.0, (capacity_kw * 1000 / (480 * 1.732)) * 1.25),
            main_breaker_kaic=65.0,
        )

    feeder = None
    if not omit_feeder:
        feeder = FeederTelemetrySchema(
            feeder_id="FEEDER-TEST-01",
            utility="Pacific Gas & Electric (PG&E)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=peak_load_kw,
            minimum_daytime_load_kw=peak_load_kw * 0.4,
            existing_connected_generation_kw=existing_der_kw,
            available_fault_duty_mva=available_fault_duty_mva,
        )

    tx = None
    if not omit_tx:
        tx = TransformerSchema(
            rating_kva=tx_rating_kva,
            primary_voltage_kv=12.47,
            secondary_voltage_v=480.0,
            impedance_pct_z=tx_impedance_z,
        )

    return ApplicationSchema(
        application_id=app_id,
        applicant_name="Clean Energy LLC",
        site_address="456 Solar Way",
        utility_provider="Pacific Gas & Electric (PG&E)",
        utility_account_number="ACCT-112233",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=capacity_kw,
        service_voltage="480V 3-Phase",
        inverters=[inv],
        transformer=tx,
        sld_components=sld,
        feeder_telemetry=feeder,
    )


# -----------------------------------------------------------------------------
# 1. Mathematical Formulas Tests
# -----------------------------------------------------------------------------


def test_calculate_penetration_pct() -> None:
    """Verify aggregate penetration percentage math and guardrails."""
    # (200 + 250) / 5000 * 100 = 9.0%
    assert calculate_penetration_pct(250.0, 200.0, 5000.0) == 9.0
    # (100 + 1200) / 4000 * 100 = 32.5%
    assert calculate_penetration_pct(1200.0, 100.0, 4000.0) == 32.5
    # Zero existing DER
    assert calculate_penetration_pct(150.0, 0.0, 1000.0) == 15.0

    # Non-positive peak load raises ValueError
    with pytest.raises(ValueError, match="strictly positive"):
        calculate_penetration_pct(100.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="strictly positive"):
        calculate_penetration_pct(100.0, 0.0, -100.0)


def test_calculate_rapid_voltage_change_pct() -> None:
    """Verify rapid voltage change calculation and error validation."""
    # (250 / 1000) * 5.75 = 1.4375 -> 1.44%
    assert calculate_rapid_voltage_change_pct(250.0, 1000.0, 5.75) == 1.44
    # (1200 / 1500) * 2.5 = 2.0%
    assert calculate_rapid_voltage_change_pct(1200.0, 1500.0, 2.5) == 2.0

    with pytest.raises(ValueError, match="Transformer rating"):
        calculate_rapid_voltage_change_pct(100.0, 0.0, 5.0)
    with pytest.raises(ValueError, match="Transformer impedance"):
        calculate_rapid_voltage_change_pct(100.0, 500.0, 0.0)


def test_calculate_short_circuit_ratio() -> None:
    """Verify short-circuit ratio calculation."""
    # 100 MVA / 0.25 MVA = 400.0
    assert calculate_short_circuit_ratio(100.0, 0.25) == 400.0
    # 15 MVA / 1.0 MVA = 15.0
    assert calculate_short_circuit_ratio(15.0, 1.0) == 15.0

    with pytest.raises(ValueError, match="DER capacity"):
        calculate_short_circuit_ratio(100.0, 0.0)
    with pytest.raises(ValueError, match="Available fault duty"):
        calculate_short_circuit_ratio(0.0, 1.0)


# -----------------------------------------------------------------------------
# 2. Individual Screen Unit Tests
# -----------------------------------------------------------------------------


def test_screen_a_applicability() -> None:
    """Verify Screen A capacity threshold evaluation."""
    app_pass = build_app(capacity_kw=2500.0)
    res_pass, def_pass = evaluate_screen_a_applicability(app_pass)
    assert res_pass.status == ScreenStatus.PASS
    assert def_pass is None

    app_fail = build_app(capacity_kw=3500.0)
    res_fail, def_fail = evaluate_screen_a_applicability(app_fail)
    assert res_fail.status == ScreenStatus.FAIL
    assert def_fail is not None
    assert def_fail.code == "DEF_FAST_TRACK_CAPACITY_EXCEEDED"
    assert def_fail.violating_screen == ScreenId.SCREEN_A_APPLICABILITY
    assert def_fail.cure_deadline_business_days == 10


def test_screen_b_certified_equipment() -> None:
    """Verify Screen B smart inverter certification checks."""
    app_pass = build_app(ul_certified=True, ieee_compliant=True, cec_listed=True)
    res_pass, def_pass = evaluate_screen_b_certified_equipment(app_pass)
    assert res_pass.status == ScreenStatus.PASS
    assert def_pass is None

    app_fail = build_app(ul_certified=False, ieee_compliant=False)
    res_fail, def_fail = evaluate_screen_b_certified_equipment(app_fail)
    assert res_fail.status == ScreenStatus.FAIL
    assert def_fail is not None
    assert def_fail.code == "DEF_NON_CERTIFIED_EQUIPMENT"
    assert def_fail.violating_screen == ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT


def test_screen_c_voltage_drop() -> None:
    """Verify Screen C rapid voltage change evaluation."""
    app_pass = build_app(capacity_kw=250.0, tx_rating_kva=1000.0, tx_impedance_z=5.75)
    res_pass, def_pass = evaluate_screen_c_voltage_drop(app_pass)
    assert res_pass.status == ScreenStatus.PASS
    assert def_pass is None

    # Voltage drop > 3.0%: 800 kW on 1000 kVA tx with 5.75% Z -> 4.6%
    app_fail = build_app(capacity_kw=800.0, tx_rating_kva=1000.0, tx_impedance_z=5.75)
    res_fail, def_fail = evaluate_screen_c_voltage_drop(app_fail)
    assert res_fail.status == ScreenStatus.FAIL
    assert def_fail is not None
    assert def_fail.code == "DEF_VOLTAGE_DROP_EXCEEDED"

    # Transformer omitted: evaluates service nominal fallback
    app_no_tx = build_app(omit_tx=True)
    res_no_tx, def_no_tx = evaluate_screen_c_voltage_drop(app_no_tx)
    assert res_no_tx.status == ScreenStatus.PASS
    assert def_no_tx is None


def test_screen_d_penetration_15pct() -> None:
    """Verify Screen D 15% feeder penetration check."""
    # (200 + 250) / 5000 = 9% <= 15%
    app_pass = build_app(capacity_kw=250.0, existing_der_kw=200.0, peak_load_kw=5000.0)
    res_pass, def_pass = evaluate_screen_d_penetration_15pct(app_pass)
    assert res_pass.status == ScreenStatus.PASS
    assert def_pass is None

    # (100 + 1200) / 4000 = 32.5% > 15%
    app_fail = build_app(capacity_kw=1200.0, existing_der_kw=100.0, peak_load_kw=4000.0)
    res_fail, def_fail = evaluate_screen_d_penetration_15pct(app_fail)
    assert res_fail.status == ScreenStatus.FAIL
    assert def_fail is not None
    assert def_fail.code == "DEF_PENETRATION_EXCEEDED"

    # Missing feeder telemetry
    app_no_feeder = build_app(omit_feeder=True)
    res_missing, def_missing = evaluate_screen_d_penetration_15pct(app_no_feeder)
    assert res_missing.status == ScreenStatus.REQUIRES_SUPPLEMENTAL_REVIEW
    assert def_missing is not None
    assert def_missing.code == "DEF_MISSING_FEEDER_TELEMETRY"


def test_screen_e_short_circuit_duty() -> None:
    """Verify Screen E short-circuit current duty."""
    app_pass = build_app(capacity_kw=250.0)
    res_pass, def_pass = evaluate_screen_e_short_circuit_duty(app_pass)
    assert res_pass.status == ScreenStatus.PASS
    assert def_pass is None


def test_screen_f_short_circuit_ratio() -> None:
    """Verify Screen F short-circuit ratio check."""
    # Fault duty 100 MVA, Gen 0.25 MVA -> SCR = 400 >= 20.0
    app_pass = build_app(capacity_kw=250.0, available_fault_duty_mva=100.0)
    res_pass, def_pass = evaluate_screen_f_short_circuit_ratio(app_pass)
    assert res_pass.status == ScreenStatus.PASS
    assert def_pass is None

    # Weak grid: Fault duty 15 MVA, Gen 1.0 MVA -> SCR = 15 < 20.0
    app_fail = build_app(capacity_kw=1000.0, available_fault_duty_mva=15.0)
    res_fail, def_fail = evaluate_screen_f_short_circuit_ratio(app_fail)
    assert res_fail.status == ScreenStatus.FAIL
    assert def_fail is not None
    assert def_fail.code == "DEF_SHORT_CIRCUIT_RATIO_LOW"

    # Missing fault duty telemetry defaults to stiff-bus pass
    app_no_scr = build_app(available_fault_duty_mva=None)
    res_no_scr, def_no_scr = evaluate_screen_f_short_circuit_ratio(app_no_scr)
    assert res_no_scr.status == ScreenStatus.PASS
    assert def_no_scr is None


def test_screen_h_disconnect_switch() -> None:
    """Verify Screen H AC disconnect switch requirements."""
    app_pass = build_app(
        has_disconnect=True,
        disconnect_visible=True,
        disconnect_lockable=True,
        disconnect_location=DisconnectSwitchLocation.ADJACENT_TO_METER,
    )
    res_pass, def_pass = evaluate_screen_h_disconnect_switch(app_pass)
    assert res_pass.status == ScreenStatus.PASS
    assert def_pass is None

    # Missing lockable feature
    app_fail_lock = build_app(
        has_disconnect=True,
        disconnect_visible=True,
        disconnect_lockable=False,
    )
    res_fail_lock, def_fail_lock = evaluate_screen_h_disconnect_switch(app_fail_lock)
    assert res_fail_lock.status == ScreenStatus.FAIL
    assert def_fail_lock is not None
    assert def_fail_lock.code == "DEF_MISSING_DISCONNECT_SWITCH"

    # Missing SLD entirely
    app_no_sld = build_app(omit_sld=True)
    res_no_sld, def_no_sld = evaluate_screen_h_disconnect_switch(app_no_sld)
    assert res_no_sld.status == ScreenStatus.FAIL
    assert def_no_sld is not None
    assert def_no_sld.code == "DEF_MISSING_SLD_EXHIBIT"


def test_screen_i_anti_islanding() -> None:
    """Verify Screen I anti-islanding trip time."""
    app_pass = build_app(trip_time_s=1.8, ul_certified=True)
    res_pass, def_pass = evaluate_screen_i_anti_islanding(app_pass)
    assert res_pass.status == ScreenStatus.PASS
    assert def_pass is None

    # Exceeds 2.0s
    app_fail = build_app(trip_time_s=2.5)
    res_fail, def_fail = evaluate_screen_i_anti_islanding(app_fail)
    assert res_fail.status == ScreenStatus.FAIL
    assert def_fail is not None
    assert def_fail.code == "DEF_ANTI_ISLANDING_TIME_EXCEEDED"


# -----------------------------------------------------------------------------
# 3. Ground-Truth Benchmark Application Package Integration Tests
# -----------------------------------------------------------------------------


def build_benchmark_app(app_id: str) -> ApplicationSchema:
    """Build validated ApplicationSchema matching catalog benchmark package."""
    catalog = load_dataset_catalog()
    entry = catalog["applications"][app_id]
    pkg = load_application(app_id)
    telemetry_raw = pkg["telemetry"]
    cap_kw = entry["capacity_kw"]

    inv = InverterSchema(
        manufacturer="SMA Solar" if "FAIL-NONCERTIFIED" not in app_id else "SunMaster",
        model_name="Sunny Tripower" if "FAIL-NONCERTIFIED" not in app_id else "Legacy-500",
        rated_ac_power_kw=cap_kw,
        nominal_voltage_v=480.0,
        max_continuous_current_a=(cap_kw * 1000) / (480 * 1.732),
        ul_1741_sb_certified="FAIL-NONCERTIFIED" not in app_id,
        ieee_1547_2018_compliant="FAIL-NONCERTIFIED" not in app_id,
        anti_islanding_trip_time_s=2.0,
        cec_listed="FAIL-NONCERTIFIED" not in app_id,
        count=1,
    )

    feeder = FeederTelemetrySchema(
        feeder_id=entry.get("feeder_id", "FEEDER-01"),
        utility=entry["utility"],
        nominal_voltage_kv=telemetry_raw.get(
            "nominal_voltage_kv", telemetry_raw.get("distribution_voltage_kv", 12.47)
        ),
        annual_peak_load_kw=telemetry_raw.get(
            "annual_peak_load_kw", telemetry_raw.get("feeder_peak_load_kw", 5000.0)
        ),
        minimum_daytime_load_kw=telemetry_raw.get(
            "minimum_daytime_load_kw", telemetry_raw.get("daytime_min_load_kw", 2000.0)
        ),
        existing_connected_generation_kw=telemetry_raw.get(
            "existing_connected_generation_kw", telemetry_raw.get("existing_der_kw", 200.0)
        ),
        available_fault_duty_mva=telemetry_raw.get("available_fault_duty_mva", 100.0),
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
        main_breaker_rating_a=max(400.0, (cap_kw * 1000 / (480 * 1.732)) * 1.25),
        main_breaker_kaic=65.0,
    )

    transformer = TransformerSchema(
        rating_kva=max(1000.0, cap_kw * 1.25),
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
        total_export_capacity_kw=cap_kw,
        service_voltage="480V 3-Phase",
        inverters=[inv],
        transformer=transformer,
        sld_components=sld,
        feeder_telemetry=feeder,
    )


def test_benchmark_app_001_pass() -> None:
    """Verify APP-001 passes all 8 deterministic screens with zero deficiencies."""
    app = build_benchmark_app("APP-001-PASS-ROOFTOP-SOLAR")
    results, deficiencies = run_deterministic_screens(app)

    assert len(results) == 8
    assert len(deficiencies) == 0
    assert all(r.status == ScreenStatus.PASS for r in results)


def test_benchmark_app_002_fail_penetration() -> None:
    """Verify APP-002 triggers Screen D deficiency exclusively."""
    app = build_benchmark_app("APP-002-FAIL-PENETRATION-15PCT")
    results, deficiencies = run_deterministic_screens(app)

    assert len(results) == 8
    assert len(deficiencies) == 1
    assert deficiencies[0].violating_screen == ScreenId.SCREEN_D_PENETRATION_15PCT
    assert deficiencies[0].code == "DEF_PENETRATION_EXCEEDED"

    screen_d = next(r for r in results if r.screen_id == ScreenId.SCREEN_D_PENETRATION_15PCT)
    assert screen_d.status == ScreenStatus.FAIL


def test_benchmark_app_003_fail_noncertified_inverter() -> None:
    """Verify APP-003 triggers Screen B deficiency exclusively."""
    app = build_benchmark_app("APP-003-FAIL-NONCERTIFIED-INV")
    results, deficiencies = run_deterministic_screens(app)

    assert len(results) == 8
    assert len(deficiencies) == 1
    assert deficiencies[0].violating_screen == ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT
    assert deficiencies[0].code == "DEF_NON_CERTIFIED_EQUIPMENT"

    screen_b = next(r for r in results if r.screen_id == ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT)
    assert screen_b.status == ScreenStatus.FAIL


def test_benchmark_app_004_fail_missing_disconnect() -> None:
    """Verify APP-004 triggers Screen H deficiency exclusively."""
    app = build_benchmark_app("APP-004-FAIL-MISSING-DISCONNECT")
    results, deficiencies = run_deterministic_screens(app)

    assert len(results) == 8
    assert len(deficiencies) == 1
    assert deficiencies[0].violating_screen == ScreenId.SCREEN_H_DISCONNECT_SWITCH
    assert deficiencies[0].code == "DEF_MISSING_DISCONNECT_SWITCH"

    screen_h = next(r for r in results if r.screen_id == ScreenId.SCREEN_H_DISCONNECT_SWITCH)
    assert screen_h.status == ScreenStatus.FAIL


def test_run_deterministic_screens_subset() -> None:
    """Verify evaluating a targeted subset of screens."""
    app = build_benchmark_app("APP-001-PASS-ROOFTOP-SOLAR")
    subset = [ScreenId.SCREEN_D_PENETRATION_15PCT, ScreenId.SCREEN_H_DISCONNECT_SWITCH]
    results, deficiencies = run_deterministic_screens(app, screens=subset)

    assert len(results) == 2
    assert [r.screen_id for r in results] == subset
    assert len(deficiencies) == 0
