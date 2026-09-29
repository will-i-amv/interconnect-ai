"""Split-Screen Review Console View for InterconnectAI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from frontend.api_client import InterconnectApiClient
from frontend.components.override_dialog import show_override_dialog
from frontend.components.pdf_viewer import render_pdf_viewer
from src.agents.letter_generator import export_letter_pdf


def render_review_console(client: InterconnectApiClient, app_id: str) -> None:
    """Render the split-screen PDF document inspection and engineering evaluation console."""
    # 1. Fetch Application Catalog for quick selector
    apps = client.get_applications_catalog()
    all_app_ids = [a["application_id"] for a in apps] if apps else [app_id]
    current_index = all_app_ids.index(app_id) if app_id in all_app_ids else 0

    # 2. Top Header & Application Switcher
    col_nav, col_select, col_meta = st.columns([2, 3, 5])
    with col_nav:
        if st.button("⬅️ Return to Queue", use_container_width=True):
            st.session_state["current_page"] = "dashboard"
            st.rerun()

    with col_select:
        new_app_id = st.selectbox(
            "Application Under Review",
            options=all_app_ids,
            index=current_index,
            label_visibility="collapsed",
        )
        if new_app_id != app_id:
            st.session_state["selected_application_id"] = new_app_id
            st.rerun()

    app_details = client.get_application_details(app_id)
    summary = app_details.get("summary", {})
    cap_kw = summary.get("capacity_kw", 0.0)
    utility = summary.get("utility", "Unknown Utility")
    feeder = summary.get("feeder_id", "FEEDER-01")

    with col_meta:
        st.markdown(
            f"""
            <div style="display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end;
                        align-items: center; padding-top: 4px;">
                <span class="spec-pill">⚡ {cap_kw:.1f} kW</span>
                <span class="spec-pill">🏛️ {utility}</span>
                <span class="spec-pill">🔌 {feeder}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        "<hr style='border: none; border-top: 1px solid rgba(255, 255, 255, 0.08); "
        "margin: 12px 0 18px 0;'>",
        unsafe_allow_html=True,
    )

    # 3. Main Split-Screen Layout
    col_pdf, col_eval = st.columns([1, 1], gap="medium")

    # -------------------------------------------------------------------------
    # Left Column: Embedded PDF Viewer
    # -------------------------------------------------------------------------
    with col_pdf:
        st.markdown("### 📑 Application Documents")
        raw_files = app_details.get("files", {})

        # Map to readable titles
        formatted_files: dict[str, str] = {}
        if raw_files.get("single_line_diagram"):
            formatted_files["Single-Line Diagram (SLD)"] = raw_files["single_line_diagram"]
        if raw_files.get("inverter_cutsheet"):
            formatted_files["Inverter Cut-Sheet / Datasheet"] = raw_files["inverter_cutsheet"]
        if raw_files.get("application_form"):
            formatted_files["Utility Application Form"] = raw_files["application_form"]

        render_pdf_viewer(formatted_files, key_prefix=f"console_{app_id}")

    # -------------------------------------------------------------------------
    # Right Column: Engineering Screening Evaluation Console
    # -------------------------------------------------------------------------
    with col_eval:
        st.markdown("### ⚡ Engineering Review Console")

        # Action Bar: Trigger screening run & override dialog
        btn_col1, btn_col2, status_col = st.columns([3, 3, 4])
        with btn_col1:
            run_clicked = st.button(
                "▶️ Run Screening",
                key=f"console_run_{app_id}",
                type="primary",
                use_container_width=True,
            )

        with btn_col2:
            if st.button(
                "🛠️ Override / Sign-Off",
                key=f"console_override_{app_id}",
                use_container_width=True,
            ):
                show_override_dialog(app_id, client)

        if run_clicked or f"result_{app_id}" not in st.session_state:
            with st.spinner(f"Evaluating technical screens for {app_id}..."):
                result = client.run_screening(app_id)
                st.session_state[f"result_{app_id}"] = result

        result = st.session_state[f"result_{app_id}"]
        outcome = result.get("overall_outcome", "UNKNOWN")
        time_ms = result.get("execution_time_ms", 0.0)

        with status_col:
            if outcome == "FAST_TRACK_APPROVED":
                st.markdown(
                    f'<div style="text-align: right;"><span class="badge-pass">'
                    f"FAST-TRACK APPROVED ({time_ms:.0f} ms)</span></div>",
                    unsafe_allow_html=True,
                )
            elif outcome == "DEFICIENCY_ISSUED":
                st.markdown(
                    f'<div style="text-align: right;"><span class="badge-fail">'
                    f"DEFICIENCY ISSUED ({time_ms:.0f} ms)</span></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="text-align: right;"><span class="badge-review">'
                    f"{outcome} ({time_ms:.0f} ms)</span></div>",
                    unsafe_allow_html=True,
                )

        # Render PE Sign-Off Banner if present
        if f"signoff_{app_id}" in st.session_state:
            so = st.session_state[f"signoff_{app_id}"]
            eng = so.get("engineer_name")
            lic = so.get("pe_license_number")
            dec = so.get("decision")
            st_utc = str(so.get("timestamp_utc", ""))[:19]
            rat = so.get("rationale")
            st.markdown(
                f"""
                <div style="background: rgba(16, 185, 129, 0.12);
                            border: 1px solid rgba(16, 185, 129, 0.4);
                            border-radius: 8px; padding: 10px 14px;
                            margin-top: 10px; margin-bottom: 10px;">
                    <div style="font-weight: 700; color: #34d399; font-size: 0.9rem;">
                        🔒 Formally Signed Off: {eng} [{lic}]
                    </div>
                    <div style="font-size: 0.8rem; color: #cbd5e1; margin-top: 2px;">
                        <strong>Determination:</strong> {dec} &bull;
                        <strong>Stamped:</strong> {st_utc} UTC
                    </div>
                    <div style="font-size: 0.78rem; color: #94a3b8;
                                margin-top: 4px; font-style: italic;">
                        "{rat}"
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

        # Tabbed Evaluation Views
        tab_matrix, tab_def, tab_letter, tab_audit = st.tabs(
            [
                "📊 Screen Matrix (A-I)",
                "⚠️ Deficiencies",
                "📝 Decision Memo",
                "🕵️ Audit Log",
            ]
        )

        # Tab 1: Screen Evaluation Matrix
        with tab_matrix:
            _render_screen_matrix(result.get("screen_results", []))

        # Tab 2: Deficiencies and Cure Window
        with tab_def:
            _render_deficiencies(result.get("deficiencies", []))

        # Tab 3: Formal Utility Decision Memo
        with tab_letter:
            _render_decision_memo(result.get("formal_letter_markdown", ""), app_id)

        # Tab 4: LangGraph Audit Trail
        with tab_audit:
            _render_audit_log(result.get("audit_log", []))


def _render_screen_matrix(screen_results: list[dict[str, Any]]) -> None:
    """Render individual screen cards for Screens A through I."""
    if not screen_results:
        st.info("No screen results available.")
        return

    for screen in screen_results:
        status = screen.get("status", "NOT_EVALUATED")
        status_pill = (
            '<span class="badge-pass">PASS</span>'
            if status == "PASS"
            else '<span class="badge-fail">FAIL</span>'
        )
        scr_name = screen.get("screen_name", screen.get("screen_id"))

        with st.container():
            st.markdown(
                f"""
                <div style="background: rgba(17, 24, 39, 0.6);
                            border: 1px solid rgba(255, 255, 255, 0.07);
                            border-radius: 8px; padding: 12px 16px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between;
                                align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 600; color: #f1f5f9;">{scr_name}</span>
                        {status_pill}
                    </div>
                    <div style="display: flex; gap: 16px; font-size: 0.82rem;
                                color: #94a3b8; margin-bottom: 6px;">
                        <span><strong>Calculated:</strong> {screen.get("calculated_value")}</span>
                        <span><strong>Threshold:</strong> {screen.get("threshold_value")}</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #cbd5e1; margin-bottom: 4px;">
                        {screen.get("reasoning")}
                    </div>
                    <div style="font-size: 0.75rem; color: #38bdf8;">
                        📜 <em>{screen.get("citation")}</em>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_deficiencies(deficiencies: list[dict[str, Any]]) -> None:
    """Render technical deficiencies and statutory cure windows."""
    if not deficiencies:
        st.success(
            "✅ Zero technical deficiencies identified. "
            "Project qualifies for Fast-Track Interconnection Approval."
        )
        return

    st.error(f"⚠️ {len(deficiencies)} Technical Deficiency(ies) Identified Under Electric Rule 21")

    for d in deficiencies:
        cure_days = d.get("cure_deadline_business_days", 10)
        with st.container():
            st.markdown(
                f"""
                <div style="background: rgba(244, 63, 94, 0.08);
                            border: 1px solid rgba(244, 63, 94, 0.3);
                            border-radius: 8px; padding: 14px; margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between;
                                align-items: flex-start; margin-bottom: 6px;">
                        <span style="font-weight: 700; color: #fb7185;">
                            {d.get("code")}: {d.get("title")}
                        </span>
                        <span class="badge-fail">{cure_days} Days to Cure</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #e2e8f0; margin-bottom: 6px;">
                        {d.get("description")}
                    </div>
                    <div style="font-size: 0.82rem; color: #fecdd3; margin-bottom: 6px;">
                        <strong>Required Cure Action:</strong> {d.get("required_cure_action")}
                    </div>
                    <div style="font-size: 0.75rem; color: #94a3b8;">
                        Tariff Citation: <code>{d.get("tariff_citation")}</code> &bull;
                        Screen: <code>{d.get("violating_screen")}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_decision_memo(markdown_text: str, app_id: str) -> None:
    """Render generated decision memo with PDF export option."""
    if not markdown_text:
        st.info("No formal decision memo generated.")
        return

    # PDF Download Option
    try:
        temp_pdf = Path(f"/tmp/{app_id}_memo.pdf")
        export_letter_pdf(markdown_text, temp_pdf)
        pdf_bytes = temp_pdf.read_bytes()
        temp_pdf.unlink(missing_ok=True)

        st.download_button(
            label="⬇️ Download Official Decision Memo (PDF)",
            data=pdf_bytes,
            file_name=f"{app_id}_Interconnection_Decision.pdf",
            mime="application/pdf",
            key=f"dl_memo_{app_id}",
            use_container_width=True,
        )
    except Exception:
        pass

    st.markdown("---")
    st.markdown(markdown_text)


def _render_audit_log(audit_log: list[dict[str, Any]]) -> None:
    """Render chronological LangGraph state machine audit trail."""
    if not audit_log:
        st.info("No audit entries recorded.")
        return

    for entry in audit_log:
        step = entry.get("step", "STEP")
        action = entry.get("action", "ACTION")
        msg = entry.get("message", "")
        ts = entry.get("timestamp_utc", "")

        is_override = action == "OVERRIDE_APPLIED"
        border_color = "#f59e0b" if is_override else "#38bdf8"
        bg_color = "rgba(245, 158, 11, 0.12)" if is_override else "rgba(15, 23, 42, 0.4)"
        action_label = f"🛠️ {action}" if is_override else str(action)

        st.markdown(
            f"""
            <div style="padding: 8px 12px; border-left: 3px solid {border_color};
                        background: {bg_color};
                        margin-bottom: 8px; border-radius: 0 6px 6px 0;">
                <div style="display: flex; justify-content: space-between;
                            font-size: 0.75rem; color: #94a3b8;">
                    <span><strong>[{step}]</strong> {action_label}</span>
                    <span>{ts}</span>
                </div>
                <div style="font-size: 0.85rem; color: #f1f5f9; margin-top: 4px;">
                    {msg}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
