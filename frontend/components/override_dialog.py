"""Human-in-the-loop override interface and engineering sign-off dialog component."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import streamlit as st
from pydantic import BaseModel, ConfigDict, Field

from frontend.api_client import InterconnectApiClient
from src.agents.state import AuditAction, AuditEntry, WorkflowStep
from src.schemas.application import (
    ApplicationSchema,
    DisconnectSwitchLocation,
    FeederTelemetrySchema,
    InverterSchema,
    SLDComponentSchema,
)
from src.schemas.screening import OverallOutcome
from src.utils.dataset import load_application_schema

logger = logging.getLogger(__name__)


class EngineerSignoffRecord(BaseModel):
    """Immutable audit record of an engineer's formal sign-off and override."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str
    engineer_name: str
    pe_license_number: str
    decision: str
    rationale: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    modified_parameters: dict[str, Any] = Field(default_factory=dict)


@st.dialog("🛠️ Human-in-the-Loop Override & Engineer Sign-Off", width="large")
def show_override_dialog(app_id: str, client: InterconnectApiClient) -> None:
    """Render modal dialog for parameter correction, manual screen overrides, and PE sign-off."""
    current_result = st.session_state.get(f"result_{app_id}", {})
    requires_override = current_result.get("requires_human_override", False)
    current_outcome = current_result.get("overall_outcome", "UNKNOWN")

    st.markdown(
        """
        <div style="font-size: 0.9rem; color: #cbd5e1; margin-bottom: 16px;">
            Review extracted electrical parameters, correct parsing discrepancies
            from SLD/cut-sheets, and execute statutory engineering determinations
            under <strong>California Rule 21</strong>.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if requires_override:
        st.warning(
            f"⚠️ **Engineering Intervention Flagged**: Application determination is currently "
            f"**{current_outcome}**. Review required before issuing final determination."
        )

    # 1. Load baseline application schema
    try:
        base_schema = load_application_schema(app_id)
    except Exception as exc:
        st.error(f"Failed to load application baseline schema: {exc}")
        return

    # -------------------------------------------------------------------------
    # Section 1: Electrical Parameter Overrides
    # -------------------------------------------------------------------------
    st.markdown("#### 1. Correct Extracted Electrical Parameters")

    p_col1, p_col2 = st.columns(2)
    with p_col1:
        capacity_kw = st.number_input(
            "Total Export Capacity (kW)",
            min_value=1.0,
            max_value=50000.0,
            value=float(base_schema.total_export_capacity_kw),
            step=10.0,
            help="Aggregate nameplate export capacity to the distribution feeder",
        )
        inv_count = st.number_input(
            "Inverter Count",
            min_value=1,
            max_value=100,
            value=len(base_schema.inverters),
            step=1,
        )
        ul_cert = st.checkbox(
            "Inverters UL 1741-SB & IEEE 1547-2018 Certified",
            value=(
                base_schema.inverters[0].ul_1741_sb_certified if base_schema.inverters else True
            ),
            help="Certifies smart inverter grid support (Volt-Var, frequency ride-through)",
        )

    with p_col2:
        has_disconnect = st.checkbox(
            "Utility Disconnect Switch Installed",
            value=(
                base_schema.sld_components.has_utility_disconnect_switch
                if base_schema.sld_components
                else True
            ),
        )
        vis_break = st.checkbox(
            "Disconnect Switch Visible-Break Verified",
            value=(
                base_schema.sld_components.disconnect_switch_visible_break
                if base_schema.sld_components
                else True
            ),
        )
        lockable = st.checkbox(
            "Disconnect Switch Lockable (Utility Padlock)",
            value=(
                base_schema.sld_components.disconnect_switch_lockable
                if base_schema.sld_components
                else True
            ),
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # Telemetry Overrides
    st.markdown("##### Feeder Telemetry Adjustments")
    tel_col1, tel_col2 = st.columns(2)
    with tel_col1:
        peak_load = st.number_input(
            "Feeder Annual Peak Load (kW)",
            min_value=100.0,
            max_value=100000.0,
            value=float(base_schema.feeder_telemetry.annual_peak_load_kw),
            step=100.0,
        )
    with tel_col2:
        min_load = st.number_input(
            "Feeder Daytime Minimum Load (kW)",
            min_value=10.0,
            max_value=50000.0,
            value=float(base_schema.feeder_telemetry.minimum_daytime_load_kw),
            step=50.0,
        )

    st.markdown("---")

    # -------------------------------------------------------------------------
    # Section 2: Professional Engineer Sign-Off & Rationale
    # -------------------------------------------------------------------------
    st.markdown("#### 2. Professional Engineer (PE) Authorization")

    pe_col1, pe_col2 = st.columns(2)
    with pe_col1:
        engineer_name = st.text_input(
            "Reviewing Engineer Full Name",
            value=st.session_state.get("engineer_name", "Jane Doe, PE"),
            placeholder="e.g. Jane Doe, PE",
        )
    with pe_col2:
        pe_license = st.text_input(
            "PE License / Stamp Number",
            value=st.session_state.get("pe_license", "PE-CA-987654"),
            placeholder="e.g. PE-CA-987654",
        )

    determination = st.selectbox(
        "Formal Regulatory Determination",
        options=[
            "APPROVE_FAST_TRACK (Fast-Track Interconnection Approval)",
            "CONFIRM_DEFICIENCY (Issue Formal 10-Day Deficiency Notice)",
            "ESCALATE_DETAILED_STUDY (Route to Supplemental Review / Study)",
        ],
        index=0 if current_outcome == OverallOutcome.FAST_TRACK_APPROVED.value else 1,
    )

    rationale = st.text_area(
        "Engineering Justification & Audit Rationale (Mandatory)",
        placeholder=(
            "Provide detailed engineering justification for parameter overrides, "
            "mitigating factors, or rationale for regulatory determination..."
        ),
        height=100,
    )

    st.markdown("---")

    # -------------------------------------------------------------------------
    # Section 3: Dialog Action Buttons
    # -------------------------------------------------------------------------
    act_col1, act_col2, act_col3 = st.columns([4, 4, 3])

    with act_col1:
        recalc_clicked = st.button(
            "🔄 Apply Overrides & Re-Run",
            type="primary",
            use_container_width=True,
        )

    with act_col2:
        signoff_clicked = st.button(
            "🔒 Submit Formal PE Sign-Off",
            use_container_width=True,
        )

    with act_col3:
        if st.button("Cancel", use_container_width=True):
            st.rerun()

    # Handle Re-Run Calculation
    if recalc_clicked:
        if not rationale.strip():
            st.error("Engineering justification rationale is required when applying overrides.")
            return

        # Construct updated ApplicationSchema with overridden values
        inverters = [
            InverterSchema(
                manufacturer=base_schema.inverters[0].manufacturer,
                model_name=base_schema.inverters[0].model_name,
                rated_ac_power_kw=capacity_kw / max(1, inv_count),
                nominal_voltage_v=base_schema.inverters[0].nominal_voltage_v,
                max_continuous_current_a=base_schema.inverters[0].max_continuous_current_a,
                ul_1741_sb_certified=ul_cert,
                ieee_1547_2018_compliant=ul_cert,
                count=inv_count,
            )
        ]
        sld = SLDComponentSchema(
            has_utility_disconnect_switch=has_disconnect,
            disconnect_switch_visible_break=vis_break,
            disconnect_switch_lockable=lockable,
            disconnect_switch_location=(
                DisconnectSwitchLocation.ADJACENT_TO_METER
                if has_disconnect
                else DisconnectSwitchLocation.NOT_DEPICTED
            ),
            main_breaker_rating_a=base_schema.sld_components.main_breaker_rating_a,
            main_breaker_kaic=base_schema.sld_components.main_breaker_kaic,
        )
        telemetry = FeederTelemetrySchema(
            feeder_id=base_schema.feeder_telemetry.feeder_id,
            utility=base_schema.feeder_telemetry.utility,
            nominal_voltage_kv=base_schema.feeder_telemetry.nominal_voltage_kv,
            annual_peak_load_kw=peak_load,
            minimum_daytime_load_kw=min_load,
            existing_connected_generation_kw=(
                base_schema.feeder_telemetry.existing_connected_generation_kw
            ),
        )
        updated_schema = ApplicationSchema(
            application_id=app_id,
            applicant_name=base_schema.applicant_name,
            site_address=base_schema.site_address,
            utility_provider=base_schema.utility_provider,
            utility_account_number=base_schema.utility_account_number,
            project_type=base_schema.project_type,
            total_export_capacity_kw=capacity_kw,
            service_voltage=base_schema.service_voltage,
            inverters=inverters,
            transformer=base_schema.transformer,
            sld_components=sld,
            feeder_telemetry=telemetry,
        )

        # Run screening with overridden schema
        updated_result = client.run_screening(
            app_id,
            custom_schema=updated_schema.model_dump(mode="json"),
        )

        # Append human override audit entry
        override_audit = AuditEntry(
            step=WorkflowStep.HUMAN_REVIEW,
            action=AuditAction.OVERRIDE_APPLIED,
            message=f"Human override applied by {engineer_name} ({pe_license}): {rationale}",
            details={
                "engineer_name": engineer_name,
                "pe_license": pe_license,
                "capacity_kw": capacity_kw,
                "ul_certified": ul_cert,
                "has_disconnect": has_disconnect,
            },
        )
        updated_result.setdefault("audit_log", []).append(override_audit.model_dump(mode="json"))

        st.session_state[f"result_{app_id}"] = updated_result
        st.session_state["engineer_name"] = engineer_name
        st.session_state["pe_license"] = pe_license
        st.toast("Overrides successfully applied and screening re-executed!", icon="✅")
        st.rerun()

    # Handle Formal PE Sign-Off Lock
    if signoff_clicked:
        if not engineer_name.strip() or not pe_license.strip() or not rationale.strip():
            st.error("Engineer Name, PE License, and Rationale are required for formal sign-off.")
            return

        chosen_code = determination.split(" ")[0]
        signoff_rec = EngineerSignoffRecord(
            application_id=app_id,
            engineer_name=engineer_name,
            pe_license_number=pe_license,
            decision=chosen_code,
            rationale=rationale,
            modified_parameters={"capacity_kw": capacity_kw, "ul_cert": ul_cert},
        )

        # Store in session state
        st.session_state[f"signoff_{app_id}"] = signoff_rec.model_dump(mode="json")
        st.session_state["engineer_name"] = engineer_name
        st.session_state["pe_license"] = pe_license

        # Record sign-off audit entry into active screening result
        if f"result_{app_id}" in st.session_state:
            res = st.session_state[f"result_{app_id}"]
            signoff_audit = AuditEntry(
                step=WorkflowStep.HUMAN_REVIEW,
                action=AuditAction.STATE_TRANSITION,
                message=(
                    f"Formal PE Sign-Off executed by {engineer_name} [{pe_license}]: {chosen_code}"
                ),
                details=signoff_rec.model_dump(mode="json"),
            )
            res.setdefault("audit_log", []).append(signoff_audit.model_dump(mode="json"))
            res["requires_human_override"] = False
            st.session_state[f"result_{app_id}"] = res

        st.toast(f"Application {app_id} successfully signed off as {chosen_code}!", icon="🔒")
        st.rerun()
