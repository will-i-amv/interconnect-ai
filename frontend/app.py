"""Master Streamlit Application Entry Point for InterconnectAI."""

from __future__ import annotations

import streamlit as st

from frontend.api_client import InterconnectApiClient
from frontend.styles import inject_custom_css
from frontend.views.dashboard import render_dashboard

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="InterconnectAI - Technical Screening Copilot",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject Modern CSS Design System
inject_custom_css()

# Initialize API Client and Session State
if "api_client" not in st.session_state:
    st.session_state["api_client"] = InterconnectApiClient()

if "current_page" not in st.session_state:
    st.session_state["current_page"] = "dashboard"

if "selected_application_id" not in st.session_state:
    st.session_state["selected_application_id"] = "APP-001-PASS-ROOFTOP-SOLAR"

client: InterconnectApiClient = st.session_state["api_client"]

# -----------------------------------------------------------------------------
# Sidebar Navigation & Regulatory Controls
# -----------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
            <div style="font-size: 2rem;">⚡</div>
            <div>
                <div style="font-size: 1.25rem; font-weight: 700; color: #f8fafc;">
                    InterconnectAI
                </div>
                <div style="font-size: 0.75rem; color: #38bdf8; font-weight: 600;">
                    Grid Review Copilot
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Navigation")
    nav_choice = st.radio(
        "Select View",
        options=["📊 Queue Dashboard", "🔍 Review Console"],
        index=0 if st.session_state["current_page"] == "dashboard" else 1,
        label_visibility="collapsed",
    )

    is_dash = st.session_state["current_page"] == "dashboard"
    if nav_choice == "📊 Queue Dashboard" and not is_dash:
        st.session_state["current_page"] = "dashboard"
        st.rerun()
    elif nav_choice == "🔍 Review Console" and is_dash:
        st.session_state["current_page"] = "review_console"
        st.rerun()

    st.markdown("---")

    st.markdown("### Regulatory Framework")
    jurisdiction = st.selectbox(
        "Governing Tariff Standard",
        options=[
            "California Electric Rule 21 (CPUC)",
            "IEEE 1547-2018 Interconnection Standard",
            "FERC Order 2023 Fast Track",
        ],
        index=0,
    )

    st.markdown("---")

    # Backend Connection Status Pill
    is_online = client.is_api_online()
    if is_online:
        st.success("🟢 FastAPI Backend: Connected")
    else:
        st.info("🔵 Standalone: Python Engine")

    st.markdown("---")
    st.markdown(
        """
        <div style="font-size: 0.75rem; color: #64748b; line-height: 1.4;">
            <strong>Rule 21 Screening Rules:</strong><br>
            &bull; Screen D: &le; 15% feeder peak load<br>
            &bull; Screen B: UL 1741-SB certification<br>
            &bull; Screen H: Visible-break disconnect<br>
            &bull; Statutory Cure: 10 business days
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Main Content Routing
# -----------------------------------------------------------------------------

if st.session_state["current_page"] == "dashboard":
    render_dashboard(client)
elif st.session_state["current_page"] == "review_console":
    app_id = st.session_state.get("selected_application_id", "APP-001-PASS-ROOFTOP-SOLAR")
    st.markdown(
        f"""
        <div class="header-banner">
            <div class="header-title">🔍 Split-Screen Review Console: {app_id}</div>
            <div class="header-desc">
                Side-by-side engineering evaluation console with multi-page vector PDF inspection
                and real-time LangGraph state machine execution reasoning.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_back, col_status = st.columns([2, 8])
    with col_back:
        if st.button("⬅️ Return to Queue Dashboard"):
            st.session_state["current_page"] = "dashboard"
            st.rerun()

    st.info(
        f"Selected Application: **{app_id}**. The full split-screen console with "
        "embedded PDF viewer and live LangGraph SSE reasoning log will be fully "
        "wired in **Ticket T-113**."
    )

    # Allow running screening directly here as well
    if st.button("▶️ Execute Full Technical Screening Now", type="primary"):
        with st.spinner("Executing screening state machine..."):
            result = client.run_screening(app_id)
            st.markdown(f"### Screening Determination: `{result.get('overall_outcome')}`")
            if result.get("formal_letter_markdown"):
                st.markdown(result["formal_letter_markdown"])
