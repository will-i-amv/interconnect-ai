"""Golden test dataset builder, schemas, and loader for InterconnectAI evaluation harness.

Constructs 25 synthetic interconnection applications (15 clean passes, 10 known deficiencies)
with ground-truth engineering labels, tariff citations, and electrical parameters for
automated benchmark evaluation per CPUC Rule 21 and IEEE 1547-2018.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
    OverallOutcome,
    ScreenId,
    ScreenStatus,
)
from src.tools.grid_screens import run_deterministic_screens

# -----------------------------------------------------------------------------
# Golden Dataset Schemas
# -----------------------------------------------------------------------------


class GoldenGroundTruth(BaseModel):
    """Ground truth expectations for an evaluation application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_overall_outcome: OverallOutcome = Field(
        ..., description="Expected screening determination"
    )
    failing_screens: list[ScreenId] = Field(
        default_factory=list,
        description="List of ScreenIds expected to fail (empty for passes)",
    )
    expected_deficiency_codes: list[str] = Field(
        default_factory=list,
        description="Formal deficiency error codes expected to be triggered",
    )
    required_citations: list[str] = Field(
        default_factory=list,
        description="Regulatory tariff citations required for grounding",
    )
    evaluation_notes: str = Field(
        default="",
        description="Engineering justification for the expected outcome",
    )


class GoldenApplication(BaseModel):
    """Single evaluated application package in the golden dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str = Field(..., description="Unique golden application identifier")
    application_name: str = Field(..., description="Descriptive project name")
    application_data: ApplicationSchema = Field(
        ..., description="Complete validated electrical application schema"
    )
    ground_truth: GoldenGroundTruth = Field(
        ..., description="Deterministic ground-truth expectations"
    )


class GoldenDataset(BaseModel):
    """Root container for the 25-application golden test benchmark."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(default="1.0.0", description="Dataset schema version")
    description: str = Field(..., description="Dataset overview and distribution description")
    total_count: int = Field(default=25, description="Total number of applications")
    pass_count: int = Field(default=15, description="Number of expected clean passes")
    fail_count: int = Field(default=10, description="Number of expected deficiency cases")
    applications: list[GoldenApplication] = Field(..., description="List of 25 golden applications")


# -----------------------------------------------------------------------------
# Golden Dataset Builder
# -----------------------------------------------------------------------------


def _create_standard_inverter(
    capacity_kw: float,
    manufacturer: str = "SMA Solar",
    model_name: str = "Sunny Tripower Core1",
    ul_certified: bool = True,
    count: int = 1,
) -> InverterSchema:
    """Helper to generate consistent InverterSchema specifications."""
    unit_kw = capacity_kw / count
    voltage_v = 480.0
    current_a = (unit_kw * 1000.0) / (voltage_v * 1.732)

    return InverterSchema(
        manufacturer=manufacturer,
        model_name=model_name,
        rated_ac_power_kw=unit_kw,
        nominal_voltage_v=voltage_v,
        max_continuous_current_a=round(current_a, 2),
        power_factor_min=-0.85,
        power_factor_max=0.85,
        ul_1741_sb_certified=ul_certified,
        ieee_1547_2018_compliant=ul_certified,
        anti_islanding_trip_time_s=2.0,
        cec_listed=ul_certified,
        count=count,
    )


def _create_standard_sld(
    has_switch: bool = True,
    visible: bool = True,
    lockable: bool = True,
    location: DisconnectSwitchLocation = DisconnectSwitchLocation.ADJACENT_TO_METER,
    breaker_rating_a: float = 800.0,
    breaker_kaic: float = 42.0,
) -> SLDComponentSchema:
    """Helper to generate Single-Line Diagram electrical component specifications."""
    return SLDComponentSchema(
        has_utility_disconnect_switch=has_switch,
        disconnect_switch_visible_break=visible,
        disconnect_switch_lockable=lockable,
        disconnect_switch_location=location,
        main_breaker_rating_a=breaker_rating_a,
        main_breaker_kaic=breaker_kaic,
        revenue_meter_depicted=True,
        grounding_electrode_system_depicted=True,
    )


def _create_standard_transformer(
    der_kw: float,
    primary_kv: float = 12.47,
    secondary_v: float = 480.0,
    z_pct: float = 2.5,
    oversize_ratio: float = 1.25,
) -> TransformerSchema:
    """Helper to generate step-up or service transformer specifications."""
    kva = round(der_kw * oversize_ratio, 1)
    return TransformerSchema(
        rating_kva=kva,
        primary_voltage_kv=primary_kv,
        secondary_voltage_v=secondary_v,
        impedance_pct_z=z_pct,
        winding_configuration="DELTA_WYE_GROUNDED",
    )


def create_golden_dataset() -> GoldenDataset:
    """Construct the complete 25-application golden test set."""
    apps: list[GoldenApplication] = []

    # =========================================================================
    # 15 CLEAN PASSES (GOLD-001 through GOLD-015)
    # =========================================================================

    pass_configs = [
        (
            "GOLD-001-PASS-RES-SOLAR",
            "Sunset Cluster Community Solar",
            "Residential Solar Co-Op LLC",
            InterconnectionType.SOLAR_PV,
            75.0,
            "Pacific Gas & Electric (PG&E)",
            "FEEDER-PGNE-01",
            3000.0,
            1200.0,
            100.0,
            50.0,
        ),
        (
            "GOLD-002-PASS-COMM-ROOFTOP",
            "Valley Logistics Commercial Rooftop",
            "SunTech Logistics LLC",
            InterconnectionType.SOLAR_PV,
            250.0,
            "Pacific Gas & Electric (PG&E)",
            "FEEDER-PGNE-02",
            4000.0,
            1800.0,
            200.0,
            60.0,
        ),
        (
            "GOLD-003-PASS-RETAIL-CANOPY",
            "South Coast Retail Center Solar Canopy",
            "Coastal Retail Ventures",
            InterconnectionType.SOLAR_PV,
            450.0,
            "Southern California Edison (SCE)",
            "FEEDER-SCE-03",
            6000.0,
            2500.0,
            400.0,
            75.0,
        ),
        (
            "GOLD-004-PASS-UNIV-CAMPUS",
            "Foothill College Green Campus Array",
            "Foothill Education Trust",
            InterconnectionType.SOLAR_PV,
            600.0,
            "Southern California Edison (SCE)",
            "FEEDER-SCE-04",
            8000.0,
            3200.0,
            500.0,
            80.0,
        ),
        (
            "GOLD-005-PASS-HOSPITAL-HYBRID",
            "Mercy General Emergency Microgrid",
            "Mercy Health Network",
            InterconnectionType.HYBRID_SOLAR_STORAGE,
            500.0,
            "San Diego Gas & Electric (SDG&E)",
            "FEEDER-SDGE-05",
            7000.0,
            2800.0,
            300.0,
            70.0,
        ),
        (
            "GOLD-006-PASS-COLD-STORAGE",
            "Sierra Frozen Foods Distribution Solar",
            "Sierra Ag Enterprises",
            InterconnectionType.SOLAR_PV,
            350.0,
            "Pacific Gas & Electric (PG&E)",
            "FEEDER-PGNE-06",
            5000.0,
            2100.0,
            250.0,
            65.0,
        ),
        (
            "GOLD-007-PASS-WATER-TREATMENT",
            "Bay Municipal Water Recovery Solar",
            "City Public Utilities District",
            InterconnectionType.SOLAR_PV,
            800.0,
            "Pacific Gas & Electric (PG&E)",
            "FEEDER-PGNE-07",
            9000.0,
            3600.0,
            450.0,
            90.0,
        ),
        (
            "GOLD-008-PASS-AGRI-WINERY",
            "Napa Valley Estate Winery Solar",
            "Napa Terroir Holdings",
            InterconnectionType.SOLAR_PV,
            180.0,
            "Southern California Edison (SCE)",
            "FEEDER-SCE-08",
            3500.0,
            1400.0,
            150.0,
            55.0,
        ),
        (
            "GOLD-009-PASS-OFFICE-PARK",
            "Mission Valley Corporate Center Array",
            "Mission Real Estate Group",
            InterconnectionType.SOLAR_PV,
            400.0,
            "San Diego Gas & Electric (SDG&E)",
            "FEEDER-SDGE-09",
            5500.0,
            2200.0,
            300.0,
            70.0,
        ),
        (
            "GOLD-010-PASS-INDUSTRIAL-MICROGRID",
            "Pacific Precision Steel Microgrid",
            "Pacific Metals Corp",
            InterconnectionType.HYBRID_SOLAR_STORAGE,
            1000.0,
            "Southern California Edison (SCE)",
            "FEEDER-SCE-10",
            12000.0,
            5000.0,
            700.0,
            120.0,
        ),
        (
            "GOLD-011-PASS-BESS-COMMERCIAL",
            "Silverado Standalone Storage BESS",
            "GridFlex Energy Storage",
            InterconnectionType.BATTERY_STORAGE,
            500.0,
            "Pacific Gas & Electric (PG&E)",
            "FEEDER-PGNE-11",
            6500.0,
            2600.0,
            350.0,
            80.0,
        ),
        (
            "GOLD-012-PASS-TRANSIT-DEPOT",
            "Metro Transit Clean Bus Fleet Depot",
            "Metropolitan Transit Authority",
            InterconnectionType.EV_CHARGING,
            750.0,
            "San Diego Gas & Electric (SDG&E)",
            "FEEDER-SDGE-12",
            9500.0,
            3800.0,
            500.0,
            95.0,
        ),
        (
            "GOLD-013-PASS-SCHOOL-DISTRICT",
            "San Joaquin Unified STEM Campus Solar",
            "County Unified School District",
            InterconnectionType.SOLAR_PV,
            300.0,
            "Pacific Gas & Electric (PG&E)",
            "FEEDER-PGNE-13",
            4500.0,
            1800.0,
            200.0,
            60.0,
        ),
        (
            "GOLD-014-PASS-LOGISTICS-AIRPORT",
            "Inland Empire Cargo Hub Solar",
            "TransPacific Air Freight Logistics",
            InterconnectionType.SOLAR_PV,
            1500.0,
            "Southern California Edison (SCE)",
            "FEEDER-SCE-14",
            16000.0,
            6500.0,
            800.0,
            150.0,
        ),
        (
            "GOLD-015-PASS-RURAL-COMMUNITY",
            "Highland Valley Rural Microgrid",
            "Highland Community Mutual",
            InterconnectionType.SOLAR_PV,
            120.0,
            "Southern California Edison (SCE)",
            "FEEDER-SCE-15",
            3000.0,
            1200.0,
            100.0,
            50.0,
        ),
    ]

    for (
        app_id,
        name,
        applicant,
        p_type,
        cap_kw,
        utility,
        feeder_id,
        peak_kw,
        min_kw,
        existing_der,
        fault_mva,
    ) in pass_configs:
        inverter = _create_standard_inverter(capacity_kw=cap_kw)
        transformer = _create_standard_transformer(der_kw=cap_kw)
        sld = _create_standard_sld()
        telemetry = FeederTelemetrySchema(
            feeder_id=feeder_id,
            utility=utility,
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=peak_kw,
            minimum_daytime_load_kw=min_kw,
            existing_connected_generation_kw=existing_der,
            available_fault_duty_mva=fault_mva,
        )

        app_data = ApplicationSchema(
            application_id=app_id,
            applicant_name=applicant,
            site_address="100 Clean Energy Way, Industrial District, CA 94105",
            utility_provider=utility,
            utility_account_number=f"ACCT-{app_id[-6:]}",
            project_type=p_type,
            total_export_capacity_kw=cap_kw,
            service_voltage="480V_3PHASE",
            inverters=[inverter],
            transformer=transformer,
            sld_components=sld,
            feeder_telemetry=telemetry,
        )

        ground_truth = GoldenGroundTruth(
            expected_overall_outcome=OverallOutcome.FAST_TRACK_APPROVED,
            failing_screens=[],
            expected_deficiency_codes=[],
            required_citations=[
                "CPUC Rule 21 Section C.1 & Section D Screen A",
                "CPUC Rule 21 Section D.1 & IEEE 1547-2018",
                "CPUC Rule 21 Section D Screen C & IEEE 1453",
                "CPUC Rule 21 Section D.2",
                "CPUC Rule 21 Section D Screen E",
                "CPUC Rule 21 Section D Screen F",
                "CPUC Rule 21 Section D.4",
                "CPUC Rule 21 Section D Screen I & IEEE 1547-2018 Clause 8.1",
            ],
            evaluation_notes=(
                f"Full clean pass across all 8 technical screens. Feeder penetration is "
                f"{((cap_kw + existing_der) / peak_kw) * 100:.1f}% (<= 15.0%). Inverters are "
                "UL 1741-SB certified, disconnect switch is compliant, and SCR is adequate."
            ),
        )

        apps.append(
            GoldenApplication(
                application_id=app_id,
                application_name=name,
                application_data=app_data,
                ground_truth=ground_truth,
            )
        )

    # =========================================================================
    # 10 KNOWN DEFICIENCIES (GOLD-016 through GOLD-025)
    # =========================================================================

    # 16. Moderate Penetration Exceeded (Screen D)
    app16_cap = 1200.0
    app16_data = ApplicationSchema(
        application_id="GOLD-016-FAIL-PENETRATION-MODERATE",
        applicant_name="Kern Agripower Solar LLC",
        site_address="4500 Orchard Highway, Bakersfield, CA 93301",
        utility_provider="Southern California Edison (SCE)",
        utility_account_number="ACCT-SCE-9812",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=app16_cap,
        service_voltage="12.47KV_3PHASE",
        inverters=[_create_standard_inverter(capacity_kw=app16_cap)],
        transformer=_create_standard_transformer(der_kw=app16_cap),
        sld_components=_create_standard_sld(),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-KERN-02",
            utility="Southern California Edison (SCE)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=4500.0,
            minimum_daytime_load_kw=1800.0,
            existing_connected_generation_kw=500.0,
            available_fault_duty_mva=100.0,
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-016-FAIL-PENETRATION-MODERATE",
            application_name="Kern Valley Agricultural Solar Farm",
            application_data=app16_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[ScreenId.SCREEN_D_PENETRATION_15PCT],
                expected_deficiency_codes=["DEF_PENETRATION_EXCEEDED"],
                required_citations=["CPUC Rule 21 Section D.2 & Section F"],
                evaluation_notes=(
                    "Penetration is (1200 + 500) / 4500 = 37.78% > 15.0%. "
                    "Requires Supplemental Review."
                ),
            ),
        )
    )

    # 17. Non-Certified Legacy Inverter (Screen B)
    app17_cap = 500.0
    app17_data = ApplicationSchema(
        application_id="GOLD-017-FAIL-NONCERTIFIED-INVERTER",
        applicant_name="Redwood Timber Works Inc",
        site_address="888 Mill Creek Road, Eureka, CA 95501",
        utility_provider="Pacific Gas & Electric (PG&E)",
        utility_account_number="ACCT-PGNE-4321",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=app17_cap,
        service_voltage="480V_3PHASE",
        inverters=[
            _create_standard_inverter(
                capacity_kw=app17_cap,
                manufacturer="Vintage Power",
                model_name="VP-500-Legacy",
                ul_certified=False,
            )
        ],
        transformer=_create_standard_transformer(der_kw=app17_cap),
        sld_components=_create_standard_sld(),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-EUREKA-04",
            utility="Pacific Gas & Electric (PG&E)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=6000.0,
            minimum_daytime_load_kw=2400.0,
            existing_connected_generation_kw=200.0,
            available_fault_duty_mva=80.0,
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-017-FAIL-NONCERTIFIED-INVERTER",
            application_name="Redwood Timber Mill Solar Project",
            application_data=app17_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT],
                expected_deficiency_codes=["DEF_NON_CERTIFIED_EQUIPMENT"],
                required_citations=["CPUC Rule 21 Section D.1 & Section E.2", "IEEE 1547-2018"],
                evaluation_notes=(
                    "Proposed inverter lacks UL 1741-SB and IEEE 1547-2018 "
                    "smart inverter certifications."
                ),
            ),
        )
    )

    # 18. Missing Utility AC Disconnect Switch (Screen H)
    app18_cap = 750.0
    app18_data = ApplicationSchema(
        application_id="GOLD-018-FAIL-MISSING-DISCONNECT",
        applicant_name="Pacific Coast Storage Partners",
        site_address="1200 Bayside Parkway, Coronado, CA 92118",
        utility_provider="San Diego Gas & Electric (SDG&E)",
        utility_account_number="ACCT-SDGE-7788",
        project_type=InterconnectionType.BATTERY_STORAGE,
        total_export_capacity_kw=app18_cap,
        service_voltage="480V_3PHASE",
        inverters=[_create_standard_inverter(capacity_kw=app18_cap)],
        transformer=_create_standard_transformer(der_kw=app18_cap),
        sld_components=_create_standard_sld(
            has_switch=False,
            visible=False,
            lockable=False,
            location=DisconnectSwitchLocation.NOT_DEPICTED,
        ),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-CORONADO-21",
            utility="San Diego Gas & Electric (SDG&E)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=8000.0,
            minimum_daytime_load_kw=3500.0,
            existing_connected_generation_kw=400.0,
            available_fault_duty_mva=90.0,
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-018-FAIL-MISSING-DISCONNECT",
            application_name="Coronado Coastal BESS Facility",
            application_data=app18_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[ScreenId.SCREEN_H_DISCONNECT_SWITCH],
                expected_deficiency_codes=["DEF_MISSING_DISCONNECT_SWITCH"],
                required_citations=["CPUC Rule 21 Section D.4 / Safety Standards"],
                evaluation_notes=(
                    "Single-Line Diagram omits mandatory utility-accessible visible "
                    "AC disconnect switch."
                ),
            ),
        )
    )

    # 19. Excessive Voltage Drop / High Impedance (Screen C)
    app19_cap = 400.0
    app19_data = ApplicationSchema(
        application_id="GOLD-019-FAIL-VOLTAGE-DROP",
        applicant_name="Desert Sun Agrivoltaics LLC",
        site_address="7700 Coachella Canal Road, Indio, CA 92201",
        utility_provider="Southern California Edison (SCE)",
        utility_account_number="ACCT-SCE-5511",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=app19_cap,
        service_voltage="480V_3PHASE",
        inverters=[_create_standard_inverter(capacity_kw=app19_cap)],
        transformer=TransformerSchema(
            rating_kva=300.0,  # Undersized relative to 400 kW export
            primary_voltage_kv=12.47,
            secondary_voltage_v=480.0,
            impedance_pct_z=3.5,  # Delta V = (400/300)*3.5 = 4.67% > 3.0%
            winding_configuration="DELTA_WYE_GROUNDED",
        ),
        sld_components=_create_standard_sld(),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-INDIO-08",
            utility="Southern California Edison (SCE)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=6500.0,
            minimum_daytime_load_kw=2800.0,
            existing_connected_generation_kw=300.0,
            available_fault_duty_mva=85.0,
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-019-FAIL-VOLTAGE-DROP",
            application_name="Coachella Desert Agrivoltaic Array",
            application_data=app19_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[ScreenId.SCREEN_C_VOLTAGE_DROP],
                expected_deficiency_codes=["DEF_VOLTAGE_DROP_EXCEEDED"],
                required_citations=["CPUC Rule 21 Section D Screen C & IEEE 1453"],
                evaluation_notes=(
                    "Calculated rapid voltage change of 4.67% exceeds the 3.0% "
                    "threshold at the PCC."
                ),
            ),
        )
    )

    # 20. Weak Grid / Low Short Circuit Ratio (Screen F)
    app20_cap = 1000.0
    app20_data = ApplicationSchema(
        application_id="GOLD-020-FAIL-SHORT-CIRCUIT-RATIO",
        applicant_name="Sierra Foothills Solar Co",
        site_address="1234 Ridge Highway, Sonora, CA 95370",
        utility_provider="Pacific Gas & Electric (PG&E)",
        utility_account_number="ACCT-PGNE-1122",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=app20_cap,
        service_voltage="12.47KV_3PHASE",
        inverters=[_create_standard_inverter(capacity_kw=app20_cap)],
        transformer=_create_standard_transformer(der_kw=app20_cap),
        sld_components=_create_standard_sld(),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-SONORA-03",
            utility="Pacific Gas & Electric (PG&E)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=9000.0,
            minimum_daytime_load_kw=3500.0,
            existing_connected_generation_kw=250.0,
            available_fault_duty_mva=14.0,  # SCR = 14.0 / 1.0 = 14.0 < 20.0
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-020-FAIL-SHORT-CIRCUIT-RATIO",
            application_name="Sonora Mountain Solar Park",
            application_data=app20_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO],
                expected_deficiency_codes=["DEF_SHORT_CIRCUIT_RATIO_LOW"],
                required_citations=["CPUC Rule 21 Section D Screen F"],
                evaluation_notes=(
                    "Short-circuit ratio of 14.0 is below the 20.0 stiff-grid threshold, "
                    "indicating a weak PCC."
                ),
            ),
        )
    )

    # 21. Extreme Feeder Penetration (Screen D)
    app21_cap = 2500.0
    app21_data = ApplicationSchema(
        application_id="GOLD-021-FAIL-PENETRATION-EXTREME",
        applicant_name="Imperial Solar Power LLC",
        site_address="9900 Salton Highway, Brawley, CA 92227",
        utility_provider="San Diego Gas & Electric (SDG&E)",
        utility_account_number="ACCT-SDGE-3344",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=app21_cap,
        service_voltage="12.47KV_3PHASE",
        inverters=[_create_standard_inverter(capacity_kw=app21_cap, count=2)],
        transformer=_create_standard_transformer(der_kw=app21_cap),
        sld_components=_create_standard_sld(),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-BRAWLEY-12",
            utility="San Diego Gas & Electric (SDG&E)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=7000.0,
            minimum_daytime_load_kw=2500.0,
            existing_connected_generation_kw=1800.0,  # Pen = (2500 + 1800) / 7000 = 61.43%
            available_fault_duty_mva=150.0,
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-021-FAIL-PENETRATION-EXTREME",
            application_name="Salton Basin Utility Scale Solar",
            application_data=app21_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[ScreenId.SCREEN_D_PENETRATION_15PCT],
                expected_deficiency_codes=["DEF_PENETRATION_EXCEEDED"],
                required_citations=["CPUC Rule 21 Section D.2 & Section F"],
                evaluation_notes=(
                    "Extreme penetration of 61.43% severely violates the 15.0% "
                    "threshold and exceeds daytime min load."
                ),
            ),
        )
    )

    # 22. Inaccessible / Non-Lockable Disconnect Switch (Screen H)
    app22_cap = 300.0
    app22_data = ApplicationSchema(
        application_id="GOLD-022-FAIL-NONLOCKABLE-DISCONNECT",
        applicant_name="Bayview Biotech Research",
        site_address="500 Mission Bay Blvd, San Francisco, CA 94158",
        utility_provider="Pacific Gas & Electric (PG&E)",
        utility_account_number="ACCT-PGNE-6677",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=app22_cap,
        service_voltage="480V_3PHASE",
        inverters=[_create_standard_inverter(capacity_kw=app22_cap)],
        transformer=_create_standard_transformer(der_kw=app22_cap),
        sld_components=_create_standard_sld(
            has_switch=True,
            visible=True,
            lockable=False,  # Not lockable
            location=DisconnectSwitchLocation.EXTERIOR_NOT_ADJACENT,  # Not adjacent
        ),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-SF-09",
            utility="Pacific Gas & Electric (PG&E)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=5000.0,
            minimum_daytime_load_kw=2000.0,
            existing_connected_generation_kw=200.0,
            available_fault_duty_mva=75.0,
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-022-FAIL-NONLOCKABLE-DISCONNECT",
            application_name="Mission Bay Life Sciences Solar",
            application_data=app22_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[ScreenId.SCREEN_H_DISCONNECT_SWITCH],
                expected_deficiency_codes=["DEF_MISSING_DISCONNECT_SWITCH"],
                required_citations=["CPUC Rule 21 Section D.4 / Safety Standards"],
                evaluation_notes=(
                    "Disconnect switch lacks required padlock provision and is not "
                    "installed adjacent to meter."
                ),
            ),
        )
    )

    # 23. Gross Over-Capacity Beyond Fast Track Scope (Screen A)
    app23_cap = 4000.0  # Exceeds 3,000 kW Fast Track eligibility
    app23_data = ApplicationSchema(
        application_id="GOLD-023-FAIL-CAPACITY-EXCEEDED",
        applicant_name="Mojave Desert Solar One",
        site_address="15000 Mojave Freeway, Barstow, CA 92311",
        utility_provider="Southern California Edison (SCE)",
        utility_account_number="ACCT-SCE-8899",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=app23_cap,
        service_voltage="12.47KV_3PHASE",
        inverters=[_create_standard_inverter(capacity_kw=app23_cap, count=4)],
        transformer=_create_standard_transformer(der_kw=app23_cap),
        sld_components=_create_standard_sld(),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-BARSTOW-01",
            utility="Southern California Edison (SCE)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=35000.0,
            minimum_daytime_load_kw=15000.0,
            existing_connected_generation_kw=1000.0,
            available_fault_duty_mva=200.0,
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-023-FAIL-CAPACITY-EXCEEDED",
            application_name="Barstow Commercial Utility PV Farm",
            application_data=app23_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[ScreenId.SCREEN_A_APPLICABILITY],
                expected_deficiency_codes=["DEF_FAST_TRACK_CAPACITY_EXCEEDED"],
                required_citations=["CPUC Rule 21 Section C.1 & Section D Screen A"],
                evaluation_notes=(
                    "Proposed export of 4,000 kW exceeds the 3,000 kW maximum "
                    "eligibility limit for Fast Track."
                ),
            ),
        )
    )

    # 24. Compound Failure: Penetration Exceeded + Missing Disconnect Switch (Screen D + Screen H)
    app24_cap = 900.0
    app24_data = ApplicationSchema(
        application_id="GOLD-024-FAIL-COMPOUND-PEN-AND-DISCONNECT",
        applicant_name="Chino Dairy Renewable Energy",
        site_address="3200 Dairy Road, Chino, CA 91710",
        utility_provider="Southern California Edison (SCE)",
        utility_account_number="ACCT-SCE-9900",
        project_type=InterconnectionType.SOLAR_PV,
        total_export_capacity_kw=app24_cap,
        service_voltage="480V_3PHASE",
        inverters=[_create_standard_inverter(capacity_kw=app24_cap)],
        transformer=_create_standard_transformer(der_kw=app24_cap),
        sld_components=_create_standard_sld(
            has_switch=False,
            visible=False,
            lockable=False,
            location=DisconnectSwitchLocation.NOT_DEPICTED,
        ),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-CHINO-05",
            utility="Southern California Edison (SCE)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=4000.0,
            minimum_daytime_load_kw=1600.0,
            existing_connected_generation_kw=400.0,  # Pen = (900 + 400) / 4000 = 32.5%
            available_fault_duty_mva=60.0,
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-024-FAIL-COMPOUND-PEN-AND-DISCONNECT",
            application_name="Chino Valley Agricultural DER Array",
            application_data=app24_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[
                    ScreenId.SCREEN_D_PENETRATION_15PCT,
                    ScreenId.SCREEN_H_DISCONNECT_SWITCH,
                ],
                expected_deficiency_codes=[
                    "DEF_PENETRATION_EXCEEDED",
                    "DEF_MISSING_DISCONNECT_SWITCH",
                ],
                required_citations=[
                    "CPUC Rule 21 Section D.2 & Section F",
                    "CPUC Rule 21 Section D.4 / Safety Standards",
                ],
                evaluation_notes=(
                    "Compound failure: feeder penetration is 32.5% (> 15.0%) and "
                    "SLD omits mandatory AC disconnect switch."
                ),
            ),
        )
    )

    # 25. Compound Failure: Non-Certified Inverter + Low Short Circuit Ratio (Screen B + Screen F)
    app25_cap = 1500.0
    app25_data = ApplicationSchema(
        application_id="GOLD-025-FAIL-COMPOUND-INVERTER-AND-SCR",
        applicant_name="Salinas Cold Storage Microgrid",
        site_address="600 Industrial Way, Salinas, CA 93901",
        utility_provider="Pacific Gas & Electric (PG&E)",
        utility_account_number="ACCT-PGNE-7711",
        project_type=InterconnectionType.HYBRID_SOLAR_STORAGE,
        total_export_capacity_kw=app25_cap,
        service_voltage="12.47KV_3PHASE",
        inverters=[
            _create_standard_inverter(
                capacity_kw=app25_cap,
                manufacturer="NonCompliant Corp",
                model_name="NC-1500-Old",
                ul_certified=False,
            )
        ],
        transformer=_create_standard_transformer(der_kw=app25_cap),
        sld_components=_create_standard_sld(),
        feeder_telemetry=FeederTelemetrySchema(
            feeder_id="FEEDER-SALINAS-02",
            utility="Pacific Gas & Electric (PG&E)",
            nominal_voltage_kv=12.47,
            annual_peak_load_kw=15000.0,
            minimum_daytime_load_kw=6000.0,
            existing_connected_generation_kw=300.0,
            available_fault_duty_mva=15.0,  # SCR = 15.0 / 1.5 = 10.0 < 20.0
        ),
    )
    apps.append(
        GoldenApplication(
            application_id="GOLD-025-FAIL-COMPOUND-INVERTER-AND-SCR",
            application_name="Salinas Produce Distribution Microgrid",
            application_data=app25_data,
            ground_truth=GoldenGroundTruth(
                expected_overall_outcome=OverallOutcome.DEFICIENCY_ISSUED,
                failing_screens=[
                    ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
                    ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO,
                ],
                expected_deficiency_codes=[
                    "DEF_NON_CERTIFIED_EQUIPMENT",
                    "DEF_SHORT_CIRCUIT_RATIO_LOW",
                ],
                required_citations=[
                    "CPUC Rule 21 Section D.1 & Section E.2",
                    "CPUC Rule 21 Section D Screen F",
                ],
                evaluation_notes=(
                    "Compound failure: inverters lack UL 1741-SB certification and "
                    "PCC short-circuit ratio is 10.0 (< 20.0)."
                ),
            ),
        )
    )

    return GoldenDataset(
        version="1.0.0",
        description=(
            "Golden evaluation benchmark of 25 synthetic interconnection applications "
            "(15 clean Fast Track passes, 10 known regulatory deficiencies) for "
            "Rule 21 and IEEE 1547-2018."
        ),
        total_count=len(apps),
        pass_count=sum(
            1
            for app in apps
            if app.ground_truth.expected_overall_outcome == OverallOutcome.FAST_TRACK_APPROVED
        ),
        fail_count=sum(
            1
            for app in apps
            if app.ground_truth.expected_overall_outcome == OverallOutcome.DEFICIENCY_ISSUED
        ),
        applications=apps,
    )


build_golden_dataset = create_golden_dataset


# -----------------------------------------------------------------------------
# Golden Dataset Persistence & Validation Utilities
# -----------------------------------------------------------------------------


def get_golden_dataset_path() -> Path:
    """Return the default path to evals/golden_dataset.json."""
    return Path(__file__).resolve().parent / "golden_dataset.json"


def save_golden_dataset(path: Path | None = None) -> Path:
    """Build and write the golden test set to disk in JSON format."""
    target_path = path or get_golden_dataset_path()
    dataset = create_golden_dataset()
    data_dict = dataset.model_dump(mode="json")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as f:
        json.dump(data_dict, f, indent=2)

    return target_path


def load_golden_dataset(path: Path | None = None) -> GoldenDataset:
    """Load and parse the golden dataset from disk."""
    source_path = path or get_golden_dataset_path()
    if not source_path.is_file():
        # Auto-generate if missing
        save_golden_dataset(source_path)

    with source_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    return GoldenDataset.model_validate(raw)


def verify_golden_application(app: GoldenApplication) -> dict[str, Any]:
    """Execute deterministic screens against a golden application and compare with ground truth.

    Returns:
        Validation report dictionary with match booleans and diagnostics.
    """
    screen_results, deficiencies = run_deterministic_screens(app.application_data)
    actual_failing_screens = [
        scr.screen_id for scr in screen_results if scr.status == ScreenStatus.FAIL
    ]
    actual_deficiency_codes = [def_item.code for def_item in deficiencies]

    has_failures = bool(actual_failing_screens)
    actual_outcome = (
        OverallOutcome.DEFICIENCY_ISSUED if has_failures else OverallOutcome.FAST_TRACK_APPROVED
    )

    outcome_match = actual_outcome == app.ground_truth.expected_overall_outcome
    screens_match = sorted(actual_failing_screens) == sorted(app.ground_truth.failing_screens)
    codes_match = sorted(actual_deficiency_codes) == sorted(
        app.ground_truth.expected_deficiency_codes
    )

    return {
        "application_id": app.application_id,
        "is_valid": outcome_match and screens_match and codes_match,
        "outcome_match": outcome_match,
        "screens_match": screens_match,
        "codes_match": codes_match,
        "actual_outcome": actual_outcome,
        "expected_outcome": app.ground_truth.expected_overall_outcome,
        "actual_failing_screens": actual_failing_screens,
        "expected_failing_screens": app.ground_truth.failing_screens,
        "actual_deficiency_codes": actual_deficiency_codes,
        "expected_deficiency_codes": app.ground_truth.expected_deficiency_codes,
    }


def verify_all_golden_applications(dataset: GoldenDataset | None = None) -> list[dict[str, Any]]:
    """Run verification against all applications in the golden dataset."""
    active_dataset = dataset or load_golden_dataset()
    return [verify_golden_application(app) for app in active_dataset.applications]
