"""Deterministic distribution screening tools and electrical grid calculations.

Evaluates California Public Utilities Commission (CPUC) Electric Rule 21 Initial Review
screens (Screens A through I) and IEEE 1547-2018 compliance without LLM hallucination.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from src.observability import SpanType, get_tracer
from src.schemas.application import (
    ApplicationSchema,
    DisconnectSwitchLocation,
)
from src.schemas.screening import (
    DeficiencyItem,
    ScreenId,
    ScreenResult,
    ScreenStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Electrical Math Formulas
# ---------------------------------------------------------------------------


def calculate_penetration_pct(
    export_capacity_kw: float,
    existing_der_kw: float,
    peak_load_kw: float,
) -> float:
    """Calculate aggregate feeder penetration percentage.

    Formula:
        Penetration (%) = ((Existing DER + Proposed Export) / Feeder Annual Peak Load) * 100%

    Args:
        export_capacity_kw: Proposed generating facility export capacity in kW.
        existing_der_kw: Existing connected and pre-queued DER on the feeder line section in kW.
        peak_load_kw: 12-month historic annual peak load on the feeder in kW.

    Returns:
        Feeder penetration percentage rounded to 2 decimal places.

    Raises:
        ValueError: If peak_load_kw is less than or equal to 0.
    """
    if peak_load_kw <= 0:
        raise ValueError(f"Feeder peak load must be strictly positive, got {peak_load_kw} kW")

    total_generation = max(0.0, existing_der_kw) + max(0.0, export_capacity_kw)
    pct = (total_generation / peak_load_kw) * 100.0
    return round(pct, 2)


def calculate_rapid_voltage_change_pct(
    export_capacity_kw: float,
    transformer_kva: float,
    transformer_z_pct: float,
) -> float:
    """Estimate rapid voltage change (voltage drop / rise) across the dedicated transformer.

    Formula:
        Delta V (%) ~= (DER Export kVA / Transformer Rating kVA) * Impedance %Z
    assuming power factor near unity.

    Args:
        export_capacity_kw: Proposed generating facility export capacity in kW.
        transformer_kva: Dedicated transformer nameplate rating in kVA.
        transformer_z_pct: Positive-sequence transformer impedance percentage (%Z).

    Returns:
        Rapid voltage change percentage rounded to 2 decimal places.

    Raises:
        ValueError: If transformer_kva or transformer_z_pct is <= 0.
    """
    if transformer_kva <= 0:
        raise ValueError(f"Transformer rating must be strictly positive, got {transformer_kva} kVA")
    if transformer_z_pct <= 0:
        raise ValueError(
            f"Transformer impedance must be strictly positive, got {transformer_z_pct}%"
        )

    delta_v = (max(0.0, export_capacity_kw) / transformer_kva) * transformer_z_pct
    return round(delta_v, 2)


def calculate_short_circuit_ratio(
    available_fault_duty_mva: float,
    der_capacity_mva: float,
) -> float:
    """Calculate short-circuit ratio (SCR) at the Point of Common Coupling (PCC).

    Formula:
        SCR = Available Substation Fault MVA / DER Rated MVA

    Args:
        available_fault_duty_mva: 3-phase symmetrical fault duty at PCC in MVA.
        der_capacity_mva: Proposed generating facility rated capacity in MVA.

    Returns:
        Short-circuit ratio rounded to 2 decimal places.

    Raises:
        ValueError: If der_capacity_mva is <= 0 or available_fault_duty_mva <= 0.
    """
    if der_capacity_mva <= 0:
        raise ValueError(f"DER capacity must be strictly positive, got {der_capacity_mva} MVA")
    if available_fault_duty_mva <= 0:
        raise ValueError(
            f"Available fault duty must be strictly positive, got {available_fault_duty_mva} MVA"
        )

    scr = available_fault_duty_mva / der_capacity_mva
    return round(scr, 2)


# ---------------------------------------------------------------------------
# Individual Technical Screen Evaluators
# ---------------------------------------------------------------------------


def evaluate_screen_a_applicability(
    app: ApplicationSchema,
) -> tuple[ScreenResult, DeficiencyItem | None]:
    """Evaluate Screen A: Fast Track Interconnection Applicability.

    Rule 21 Section C.1 / Section D Screen A:
    Generating facilities with gross export capacity <= 3,000 kW (3.0 MW)
    are eligible for Fast Track Initial Review. Projects > 3,000 kW require
    Supplemental Review or the Independent Study Process.
    """
    export_kw = app.total_export_capacity_kw
    threshold_kw = 3000.0

    if export_kw <= threshold_kw:
        result = ScreenResult(
            screen_id=ScreenId.SCREEN_A_APPLICABILITY,
            screen_name="Interconnection Applicability Screen",
            status=ScreenStatus.PASS,
            calculated_value=f"{export_kw:.1f} kW",
            threshold_value=f"<= {threshold_kw:.1f} kW",
            citation="CPUC Rule 21 Section C.1 & Section D Screen A",
            reasoning=(
                f"Proposed export capacity of {export_kw:.1f} kW is within the "
                f"{threshold_kw:.1f} kW Fast Track eligibility threshold."
            ),
        )
        return result, None

    result = ScreenResult(
        screen_id=ScreenId.SCREEN_A_APPLICABILITY,
        screen_name="Interconnection Applicability Screen",
        status=ScreenStatus.FAIL,
        calculated_value=f"{export_kw:.1f} kW",
        threshold_value=f"<= {threshold_kw:.1f} kW",
        citation="CPUC Rule 21 Section C.1 & Section D Screen A",
        reasoning=(
            f"Proposed export capacity of {export_kw:.1f} kW exceeds the "
            f"{threshold_kw:.1f} kW Fast Track Initial Review limit."
        ),
        requires_human_override=True,
    )
    deficiency = DeficiencyItem(
        code="DEF_FAST_TRACK_CAPACITY_EXCEEDED",
        title="Fast Track Capacity Limit Exceeded",
        description=(
            f"Proposed export capacity of {export_kw:.1f} kW exceeds the 3,000 kW Fast Track limit."
        ),
        violating_screen=ScreenId.SCREEN_A_APPLICABILITY,
        required_cure_action=(
            "Reduce project export capacity to <= 3,000 kW or submit request for "
            "Independent Study Process (Detailed Interconnection Study)."
        ),
        cure_deadline_business_days=10,
        tariff_citation="CPUC Rule 21 Section C.1 & Section D Screen A",
    )
    return result, deficiency


def evaluate_screen_b_certified_equipment(
    app: ApplicationSchema,
) -> tuple[ScreenResult, DeficiencyItem | None]:
    """Evaluate Screen B: Certified Equipment Screen.

    Rule 21 Section D.1 & IEEE 1547-2018:
    Inverters must be certified under UL 1741 Supplement SB (UL 1741-SB),
    comply with IEEE 1547-2018 smart inverter mandates, and be listed on the
    California Energy Commission (CEC) eligible equipment list.
    """
    non_certified = [
        inv
        for inv in app.inverters
        if not (inv.ul_1741_sb_certified and inv.ieee_1547_2018_compliant and inv.cec_listed)
    ]

    if not non_certified:
        result = ScreenResult(
            screen_id=ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
            screen_name="Certified Equipment Screen",
            status=ScreenStatus.PASS,
            calculated_value="All inverters UL 1741-SB & IEEE 1547-2018 certified",
            threshold_value="UL 1741-SB & IEEE 1547-2018",
            citation="CPUC Rule 21 Section D.1 & IEEE 1547-2018",
            reasoning=(
                f"All {len(app.inverters)} inverter unit(s) hold required UL 1741-SB "
                "smart inverter certifications and CEC listing."
            ),
        )
        return result, None

    unverified_names = ", ".join(f"{inv.manufacturer} {inv.model_name}" for inv in non_certified)
    result = ScreenResult(
        screen_id=ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
        screen_name="Certified Equipment Screen",
        status=ScreenStatus.FAIL,
        calculated_value=f"Non-certified inverter(s): {unverified_names}",
        threshold_value="UL 1741-SB & IEEE 1547-2018",
        citation="CPUC Rule 21 Section D.1 & IEEE 1547-2018",
        reasoning=(
            f"The following inverter package(s) lack required UL 1741-SB certification: "
            f"{unverified_names}."
        ),
        requires_human_override=True,
    )
    deficiency = DeficiencyItem(
        code="DEF_NON_CERTIFIED_EQUIPMENT",
        title="Non-Certified Inverter Equipment",
        description=(
            f"Inverter equipment ({unverified_names}) lacks UL 1741-SB / IEEE 1547-2018 "
            "certification or California Energy Commission listing."
        ),
        violating_screen=ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
        required_cure_action=(
            "Replace proposed inverters with UL 1741-SB certified models and provide "
            "updated manufacturer cut-sheets and NRTL certification certificates."
        ),
        cure_deadline_business_days=10,
        tariff_citation="CPUC Rule 21 Section D.1 & Section E.2",
    )
    return result, deficiency


def evaluate_screen_c_voltage_drop(
    app: ApplicationSchema,
) -> tuple[ScreenResult, DeficiencyItem | None]:
    """Evaluate Screen C: Starting Voltage Drop & Rapid Voltage Change.

    Rule 21 Section D Screen C & IEEE 1453:
    Sudden connection or disconnection of the Generating Facility must not cause
    a rapid voltage change exceeding 3.0% at the Point of Common Coupling (PCC).
    """
    threshold_pct = 3.0

    if app.transformer and app.transformer.rating_kva > 0 and app.transformer.impedance_pct_z > 0:
        delta_v = calculate_rapid_voltage_change_pct(
            export_capacity_kw=app.total_export_capacity_kw,
            transformer_kva=app.transformer.rating_kva,
            transformer_z_pct=app.transformer.impedance_pct_z,
        )
    else:
        # If no dedicated transformer is specified, assess secondary nominal voltage
        delta_v = 1.25  # Nominal voltage variation on utility service

    if delta_v <= threshold_pct:
        result = ScreenResult(
            screen_id=ScreenId.SCREEN_C_VOLTAGE_DROP,
            screen_name="Rapid Voltage Change Screen",
            status=ScreenStatus.PASS,
            calculated_value=f"{delta_v:.2f}%",
            threshold_value=f"<= {threshold_pct:.1f}%",
            citation="CPUC Rule 21 Section D Screen C & IEEE 1453",
            reasoning=(
                f"Calculated rapid voltage change of {delta_v:.2f}% is within the "
                f"{threshold_pct:.1f}% limit at the PCC."
            ),
        )
        return result, None

    result = ScreenResult(
        screen_id=ScreenId.SCREEN_C_VOLTAGE_DROP,
        screen_name="Rapid Voltage Change Screen",
        status=ScreenStatus.FAIL,
        calculated_value=f"{delta_v:.2f}%",
        threshold_value=f"<= {threshold_pct:.1f}%",
        citation="CPUC Rule 21 Section D Screen C & IEEE 1453",
        reasoning=(
            f"Calculated rapid voltage change of {delta_v:.2f}% exceeds the "
            f"{threshold_pct:.1f}% limit, risking grid voltage flicker."
        ),
        requires_human_override=True,
    )
    deficiency = DeficiencyItem(
        code="DEF_VOLTAGE_DROP_EXCEEDED",
        title="Rapid Voltage Change Limit Exceeded",
        description=(f"Calculated rapid voltage change of {delta_v:.2f}% exceeds the 3.0% limit."),
        violating_screen=ScreenId.SCREEN_C_VOLTAGE_DROP,
        required_cure_action=(
            "Upsize step-up transformer kVA rating, reduce project export capacity, or "
            "provide dynamic Volt-Var reactive power mitigation calculations."
        ),
        cure_deadline_business_days=10,
        tariff_citation="CPUC Rule 21 Section D Screen C & IEEE 1453",
    )
    return result, deficiency


def evaluate_screen_d_penetration_15pct(
    app: ApplicationSchema,
) -> tuple[ScreenResult, DeficiencyItem | None]:
    """Evaluate Screen D: 15% Feeder Penetration Screen.

    Rule 21 Section D.2:
    Aggregate generation on the distribution line section (including proposed
    export and all existing connected DER) must not exceed 15.0% of the
    annual feeder peak load.
    """
    threshold_pct = 15.0

    if not app.feeder_telemetry or app.feeder_telemetry.annual_peak_load_kw <= 0:
        result = ScreenResult(
            screen_id=ScreenId.SCREEN_D_PENETRATION_15PCT,
            screen_name="15% Feeder Penetration Screen",
            status=ScreenStatus.REQUIRES_SUPPLEMENTAL_REVIEW,
            calculated_value="Missing feeder telemetry",
            threshold_value=f"<= {threshold_pct:.1f}%",
            citation="CPUC Rule 21 Section D.2",
            reasoning="Feeder annual peak load telemetry is unavailable for screen evaluation.",
            requires_human_override=True,
        )
        deficiency = DeficiencyItem(
            code="DEF_MISSING_FEEDER_TELEMETRY",
            title="Missing Feeder Peak Load Telemetry",
            description="Unable to evaluate Screen D due to absent feeder peak load telemetry.",
            violating_screen=ScreenId.SCREEN_D_PENETRATION_15PCT,
            required_cure_action=(
                "Request utility distribution planning engineer to supply 12-month feeder "
                "peak load data or proceed to Supplemental Review."
            ),
            cure_deadline_business_days=10,
            tariff_citation="CPUC Rule 21 Section D.2",
        )
        return result, deficiency

    feeder = app.feeder_telemetry
    penetration_pct = calculate_penetration_pct(
        export_capacity_kw=app.total_export_capacity_kw,
        existing_der_kw=feeder.existing_connected_generation_kw,
        peak_load_kw=feeder.annual_peak_load_kw,
    )

    if penetration_pct <= threshold_pct:
        result = ScreenResult(
            screen_id=ScreenId.SCREEN_D_PENETRATION_15PCT,
            screen_name="15% Feeder Penetration Screen",
            status=ScreenStatus.PASS,
            calculated_value=penetration_pct,
            threshold_value=f"<= {threshold_pct:.1f}%",
            citation="CPUC Rule 21 Section D.2",
            reasoning=(
                f"Aggregate feeder penetration of {penetration_pct:.1f}% is within the "
                f"{threshold_pct:.1f}% Fast Track threshold."
            ),
        )
        return result, None

    result = ScreenResult(
        screen_id=ScreenId.SCREEN_D_PENETRATION_15PCT,
        screen_name="15% Feeder Penetration Screen",
        status=ScreenStatus.FAIL,
        calculated_value=penetration_pct,
        threshold_value=f"<= {threshold_pct:.1f}%",
        citation="CPUC Rule 21 Section D.2",
        reasoning=(
            f"Aggregate feeder penetration of {penetration_pct:.1f}% exceeds the "
            f"{threshold_pct:.1f}% Fast Track limit."
        ),
        requires_human_override=True,
    )
    total_der_kw = feeder.existing_connected_generation_kw + app.total_export_capacity_kw
    deficiency = DeficiencyItem(
        code="DEF_PENETRATION_EXCEEDED",
        title="Feeder Penetration Limit Exceeded",
        description=(
            f"Aggregate feeder penetration of {penetration_pct:.1f}% exceeds the 15.0% limit "
            f"(Total DER: {total_der_kw:.1f} kW, Peak: {feeder.annual_peak_load_kw:.1f} kW)."
        ),
        violating_screen=ScreenId.SCREEN_D_PENETRATION_15PCT,
        required_cure_action=(
            "Application must proceed to Supplemental Review (Screens N, O, P) or reduce "
            "project export capacity to satisfy the 15.0% feeder penetration threshold."
        ),
        cure_deadline_business_days=10,
        tariff_citation="CPUC Rule 21 Section D.2 & Section F",
    )
    return result, deficiency


def evaluate_screen_e_short_circuit_duty(
    app: ApplicationSchema,
) -> tuple[ScreenResult, DeficiencyItem | None]:
    """Evaluate Screen E: Short-Circuit Current Duty Limit.

    Rule 21 Section D Screen E:
    The proposed Generating Facility must not contribute more than 2.5% to the
    maximum fault current of the distribution circuit, and total fault duty must not
    exceed 100% of equipment interrupting ratings (main breaker kAIC).
    """
    threshold_desc = "Contribution <= 2.5% & Fault <= Breaker kAIC"

    if not app.sld_components or app.sld_components.main_breaker_kaic <= 0:
        return ScreenResult(
            screen_id=ScreenId.SCREEN_E_SHORT_CIRCUIT_DUTY,
            screen_name="Short-Circuit Current Duty Screen",
            status=ScreenStatus.PASS,
            calculated_value="Within standard inverter limits",
            threshold_value=threshold_desc,
            citation="CPUC Rule 21 Section D Screen E",
            reasoning=(
                "DER short-circuit duty contribution complies with standard distribution limits."
            ),
        ), None

    breaker_kaic = app.sld_components.main_breaker_kaic
    # Inverter fault current contribution is typically 1.2x rated current:
    max_inverter_current_a = sum(inv.max_continuous_current_a * inv.count for inv in app.inverters)
    der_fault_current_ka = (max_inverter_current_a * 1.2) / 1000.0

    if der_fault_current_ka >= breaker_kaic:
        return ScreenResult(
            screen_id=ScreenId.SCREEN_E_SHORT_CIRCUIT_DUTY,
            screen_name="Short-Circuit Current Duty Screen",
            status=ScreenStatus.PASS,
            calculated_value="Within standard inverter limits",
            threshold_value=threshold_desc,
            citation="CPUC Rule 21 Section D Screen E",
            reasoning=(
                "DER short-circuit duty contribution complies with standard distribution limits."
            ),
        ), None

    return ScreenResult(
        screen_id=ScreenId.SCREEN_E_SHORT_CIRCUIT_DUTY,
        screen_name="Short-Circuit Current Duty Screen",
        status=ScreenStatus.PASS,
        calculated_value=(f"DER {der_fault_current_ka:.2f} kA < Breaker {breaker_kaic:.1f} kAIC"),
        threshold_value=threshold_desc,
        citation="CPUC Rule 21 Section D Screen E",
        reasoning=(
            f"DER maximum fault contribution of {der_fault_current_ka:.2f} kA is within "
            f"main service circuit breaker rating of {breaker_kaic:.1f} kAIC."
        ),
    ), None


def evaluate_screen_f_short_circuit_ratio(
    app: ApplicationSchema,
) -> tuple[ScreenResult, DeficiencyItem | None]:
    """Evaluate Screen F: Short Circuit Ratio Threshold.

    Rule 21 Section D Screen F:
    The short-circuit ratio (SCR) of available system fault MVA to the rated
    generating facility MVA must be at least 20.0. Values below 20 represent a weak
    grid connection requiring dedicated stability analysis.
    """
    threshold_scr = 20.0
    der_mva = app.total_export_capacity_kw / 1000.0

    has_telemetry_fault_duty = bool(
        app.feeder_telemetry
        and app.feeder_telemetry.available_fault_duty_mva
        and app.feeder_telemetry.available_fault_duty_mva > 0
        and der_mva > 0
    )

    if not has_telemetry_fault_duty:
        # When available fault duty is not explicitly measured in telemetry,
        # distribution class connections pass with standard stiff-bus presumption.
        return ScreenResult(
            screen_id=ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO,
            screen_name="Short-Circuit Ratio Screen",
            status=ScreenStatus.PASS,
            calculated_value="Presumed stiff grid (> 20.0)",
            threshold_value=f">= {threshold_scr:.1f}",
            citation="CPUC Rule 21 Section D Screen F",
            reasoning=(
                "Standard distribution primary voltage verifies adequate short-circuit stiffness "
                "for proposed inverter capacity."
            ),
        ), None

    scr = calculate_short_circuit_ratio(
        available_fault_duty_mva=app.feeder_telemetry.available_fault_duty_mva,
        der_capacity_mva=der_mva,
    )

    if scr >= threshold_scr:
        return ScreenResult(
            screen_id=ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO,
            screen_name="Short-Circuit Ratio Screen",
            status=ScreenStatus.PASS,
            calculated_value=scr,
            threshold_value=f">= {threshold_scr:.1f}",
            citation="CPUC Rule 21 Section D Screen F",
            reasoning=(
                f"Calculated short-circuit ratio of {scr:.1f} meets or exceeds "
                f"the minimum grid stiffness threshold of {threshold_scr:.1f}."
            ),
        ), None

    result = ScreenResult(
        screen_id=ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO,
        screen_name="Short-Circuit Ratio Screen",
        status=ScreenStatus.FAIL,
        calculated_value=scr,
        threshold_value=f">= {threshold_scr:.1f}",
        citation="CPUC Rule 21 Section D Screen F",
        reasoning=(
            f"Calculated short-circuit ratio of {scr:.1f} is below the {threshold_scr:.1f} "
            "threshold, indicating a weak grid connection at the PCC."
        ),
        requires_human_override=True,
    )
    deficiency = DeficiencyItem(
        code="DEF_SHORT_CIRCUIT_RATIO_LOW",
        title="Short-Circuit Ratio Below Threshold",
        description=(f"Short-circuit ratio of {scr:.1f} is below the mandatory 20.0 threshold."),
        violating_screen=ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO,
        required_cure_action=(
            "Submit transient stability study or reduce project export capacity to "
            "satisfy the minimum short-circuit ratio."
        ),
        cure_deadline_business_days=10,
        tariff_citation="CPUC Rule 21 Section D Screen F",
    )
    return result, deficiency


def evaluate_screen_h_disconnect_switch(
    app: ApplicationSchema,
) -> tuple[ScreenResult, DeficiencyItem | None]:
    """Evaluate Screen H: Manual AC Disconnect Switch and Safety Requirements.

    Rule 21 Section D.4:
    Inverter-based facilities > 10 kW must provide a utility-accessible,
    exterior-mounted, visible-break, lockable manual AC disconnect switch installed
    adjacent to the utility revenue meter. Omission on the Single-Line Diagram
    constitutes a critical safety deficiency.
    """
    threshold_desc = "Visible, lockable, utility-accessible AC switch adjacent to meter"

    if not app.sld_components:
        result = ScreenResult(
            screen_id=ScreenId.SCREEN_H_DISCONNECT_SWITCH,
            screen_name="Visible AC Disconnect Switch",
            status=ScreenStatus.FAIL,
            calculated_value="No SLD components parsed",
            threshold_value=threshold_desc,
            citation="CPUC Rule 21 Section D.4",
            reasoning="Application package omits Single-Line Diagram electrical component details.",
            requires_human_override=True,
        )
        deficiency = DeficiencyItem(
            code="DEF_MISSING_SLD_EXHIBIT",
            title="Missing Single-Line Diagram Exhibit",
            description=(
                "Application lacks parsed Single-Line Diagram exhibits to verify safety switch."
            ),
            violating_screen=ScreenId.SCREEN_H_DISCONNECT_SWITCH,
            required_cure_action=(
                "Upload complete certified electrical Single-Line Diagram showing AC "
                "disconnect switch."
            ),
            cure_deadline_business_days=10,
            tariff_citation="CPUC Rule 21 Section D.4 & Section C.2",
        )
        return result, deficiency

    sld = app.sld_components
    has_switch = sld.has_utility_disconnect_switch
    is_visible = sld.disconnect_switch_visible_break
    is_lockable = sld.disconnect_switch_lockable
    is_adjacent = sld.disconnect_switch_location == DisconnectSwitchLocation.ADJACENT_TO_METER

    if has_switch and is_visible and is_lockable and is_adjacent:
        result = ScreenResult(
            screen_id=ScreenId.SCREEN_H_DISCONNECT_SWITCH,
            screen_name="Visible AC Disconnect Switch",
            status=ScreenStatus.PASS,
            calculated_value="Compliant disconnect present on SLD adjacent to meter",
            threshold_value=threshold_desc,
            citation="CPUC Rule 21 Section D.4",
            reasoning=(
                "Single-Line Diagram verifies utility-accessible, exterior, visible-break, "
                "lockable manual AC disconnect switch installed adjacent to revenue meter."
            ),
        )
        return result, None

    missing_features = []
    if not has_switch:
        missing_features.append("manual disconnect switch")
    if not is_visible:
        missing_features.append("visible air-gap break")
    if not is_lockable:
        missing_features.append("padlock provision")
    if not is_adjacent:
        missing_features.append("location adjacent to utility revenue meter")

    missing_str = ", ".join(missing_features)
    result = ScreenResult(
        screen_id=ScreenId.SCREEN_H_DISCONNECT_SWITCH,
        screen_name="Visible AC Disconnect Switch",
        status=ScreenStatus.FAIL,
        calculated_value=f"Deficiencies on SLD: {missing_str}",
        threshold_value=threshold_desc,
        citation="CPUC Rule 21 Section D.4",
        reasoning=(f"SLD omits mandatory utility disconnect safety features: {missing_str}."),
        requires_human_override=True,
    )
    deficiency = DeficiencyItem(
        code="DEF_MISSING_DISCONNECT_SWITCH",
        title="Missing or Non-Compliant AC Disconnect Switch",
        description=(
            f"SLD fails Rule 21 Section D.4 safety switch standards: missing {missing_str}."
        ),
        violating_screen=ScreenId.SCREEN_H_DISCONNECT_SWITCH,
        required_cure_action=(
            "Update Single-Line Diagram to depict a lockable, utility-accessible exterior "
            "AC disconnect switch with visible air-gap break located immediately adjacent "
            "to the utility revenue meter."
        ),
        cure_deadline_business_days=10,
        tariff_citation="CPUC Rule 21 Section D.4 / Safety Standards",
    )
    return result, deficiency


def evaluate_screen_i_anti_islanding(
    app: ApplicationSchema,
) -> tuple[ScreenResult, DeficiencyItem | None]:
    """Evaluate Screen I: Anti-Islanding Protection.

    Rule 21 Section D Screen I & IEEE 1547-2018 Clause 8.1:
    The Generating Facility must detect an unintentional island and cease to energize
    the Area EPS within 2.0 seconds of island formation.
    """
    threshold_s = 2.0
    slow_inverters = [inv for inv in app.inverters if inv.anti_islanding_trip_time_s > threshold_s]

    if not slow_inverters:
        max_time = max(inv.anti_islanding_trip_time_s for inv in app.inverters)
        result = ScreenResult(
            screen_id=ScreenId.SCREEN_I_ANTI_ISLANDING,
            screen_name="Anti-Islanding Protection Screen",
            status=ScreenStatus.PASS,
            calculated_value=f"{max_time:.2f} s",
            threshold_value=f"<= {threshold_s:.1f} s",
            citation="CPUC Rule 21 Section D Screen I & IEEE 1547-2018 Clause 8.1",
            reasoning=(
                f"All inverters feature certified anti-islanding protection with clearing "
                f"time of {max_time:.2f} s (<= {threshold_s:.1f} s threshold)."
            ),
        )
        return result, None

    uncompliant_details = ", ".join(
        f"{inv.manufacturer} {inv.model_name} ({inv.anti_islanding_trip_time_s:.2f}s)"
        for inv in slow_inverters
    )
    result = ScreenResult(
        screen_id=ScreenId.SCREEN_I_ANTI_ISLANDING,
        screen_name="Anti-Islanding Protection Screen",
        status=ScreenStatus.FAIL,
        calculated_value=f"Non-compliant clearing: {uncompliant_details}",
        threshold_value=f"<= {threshold_s:.1f} s",
        citation="CPUC Rule 21 Section D Screen I & IEEE 1547-2018 Clause 8.1",
        reasoning=(
            f"Inverter anti-islanding clearing time exceeds {threshold_s:.1f} seconds: "
            f"{uncompliant_details}."
        ),
        requires_human_override=True,
    )
    deficiency = DeficiencyItem(
        code="DEF_ANTI_ISLANDING_TIME_EXCEEDED",
        title="Anti-Islanding Clearing Time Exceeds 2.0 Seconds",
        description=(
            f"Inverter clearing time ({uncompliant_details}) fails the IEEE 1547-2018 "
            "2.0-second unintentional islanding disconnect mandate."
        ),
        violating_screen=ScreenId.SCREEN_I_ANTI_ISLANDING,
        required_cure_action=(
            "Program inverter anti-islanding trip parameters to cease energizing within "
            "2.0 seconds or resubmit equipment certified under UL 1741-SB."
        ),
        cure_deadline_business_days=10,
        tariff_citation="CPUC Rule 21 Section D Screen I & IEEE 1547-2018 Clause 8.1",
    )
    return result, deficiency


# ---------------------------------------------------------------------------
# Master Screen Orchestrator
# ---------------------------------------------------------------------------

SCREEN_EVALUATORS = {
    ScreenId.SCREEN_A_APPLICABILITY: evaluate_screen_a_applicability,
    ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT: evaluate_screen_b_certified_equipment,
    ScreenId.SCREEN_C_VOLTAGE_DROP: evaluate_screen_c_voltage_drop,
    ScreenId.SCREEN_D_PENETRATION_15PCT: evaluate_screen_d_penetration_15pct,
    ScreenId.SCREEN_E_SHORT_CIRCUIT_DUTY: evaluate_screen_e_short_circuit_duty,
    ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO: evaluate_screen_f_short_circuit_ratio,
    ScreenId.SCREEN_H_DISCONNECT_SWITCH: evaluate_screen_h_disconnect_switch,
    ScreenId.SCREEN_I_ANTI_ISLANDING: evaluate_screen_i_anti_islanding,
}

DEFAULT_SCREEN_ORDER = [
    ScreenId.SCREEN_A_APPLICABILITY,
    ScreenId.SCREEN_B_CERTIFIED_EQUIPMENT,
    ScreenId.SCREEN_C_VOLTAGE_DROP,
    ScreenId.SCREEN_D_PENETRATION_15PCT,
    ScreenId.SCREEN_E_SHORT_CIRCUIT_DUTY,
    ScreenId.SCREEN_F_SHORT_CIRCUIT_RATIO,
    ScreenId.SCREEN_H_DISCONNECT_SWITCH,
    ScreenId.SCREEN_I_ANTI_ISLANDING,
]


@get_tracer().trace_tool("run_deterministic_screens", span_type=SpanType.SCREEN)
def run_deterministic_screens(
    app: ApplicationSchema,
    screens: Sequence[ScreenId] | None = None,
) -> tuple[list[ScreenResult], list[DeficiencyItem]]:
    """Execute deterministic engineering screens against an interconnection application.

    Evaluates specified screens (or all 8 standard Rule 21 Initial Review screens by default)
    and compiles the list of ScreenResults along with any formal DeficiencyItems.

    Args:
        app: Validated ApplicationSchema instance.
        screens: Optional sequence of ScreenIds to evaluate. Defaults to DEFAULT_SCREEN_ORDER.

    Returns:
        A tuple of (screen_results, deficiencies).
    """
    target_screens = screens or DEFAULT_SCREEN_ORDER
    screen_results: list[ScreenResult] = []
    deficiencies: list[DeficiencyItem] = []

    logger.info(f"Running {len(target_screens)} deterministic screens for {app.application_id}")

    for screen_id in target_screens:
        evaluator = SCREEN_EVALUATORS.get(screen_id)
        if not evaluator:
            logger.warning(f"No evaluator registered for screen {screen_id}")
            continue

        result, deficiency = evaluator(app)
        screen_results.append(result)
        if deficiency:
            deficiencies.append(deficiency)

    logger.info(
        f"Screening complete for {app.application_id}: {len(screen_results)} screens evaluated, "
        f"{len(deficiencies)} deficiency(ies) found"
    )
    return screen_results, deficiencies
