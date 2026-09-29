"""Interactive Queue Dashboard View for InterconnectAI."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from frontend.api_client import InterconnectApiClient


def render_dashboard(client: InterconnectApiClient) -> None:
    """Render the master application queue dashboard, KPI metrics, and filtering controls."""
    # 1. Header Banner
    is_online = client.is_api_online()
    status_badge = (
        '<span class="badge-pass">🟢 FastAPI Backend: Online</span>'
        if is_online
        else '<span class="badge-info">🔵 Standalone Mode: Direct Engine</span>'
    )

    st.markdown(
        f"""
        <div class="header-banner">
            <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                <div>
                    <div class="header-title">⚡ InterconnectAI Technical Queue</div>
                    <div class="header-desc">
                        Autonomous Distribution Interconnection Screening & Technical Review Copilot
                        grounded in California Electric Rule 21, FERC Order 2023, and
                        IEEE 1547-2018.
                    </div>
                </div>
                <div style="margin-top: 4px;">
                    {status_badge}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. Fetch Applications Data
    apps = client.get_applications_catalog()
    if not apps:
        st.warning("No applications found in the benchmark catalog.")
        return

    # Compute KPI Metrics
    total_apps = len(apps)
    approved_apps = sum(1 for a in apps if a.get("expected_outcome") == "FAST_TRACK_APPROVED")
    deficient_apps = sum(1 for a in apps if a.get("expected_outcome") == "DEFICIENCY_ISSUED")
    total_capacity_mw = sum(a.get("capacity_kw", 0.0) for a in apps) / 1000.0
    pass_pct = (approved_apps / total_apps * 100) if total_apps else 0.0
    def_pct = (deficient_apps / total_apps * 100) if total_apps else 0.0

    # 3. Render KPI Metric Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Queue Applications</div>
                <div class="metric-value">{total_apps}</div>
                <div class="metric-sub">Active reviews in queue</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Fast-Track Pass</div>
                <div class="metric-value" style="color: #34d399;">{approved_apps}</div>
                <div class="metric-sub">{pass_pct:.0f}% approval rate</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Deficiencies</div>
                <div class="metric-value" style="color: #fb7185;">{deficient_apps}</div>
                <div class="metric-sub">{def_pct:.0f}% cure required</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Total DER Capacity</div>
                <div class="metric-value" style="color: #38bdf8;">{total_capacity_mw:.2f} MW</div>
                <div class="metric-sub">Clean energy requested</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col5:
        st.markdown(
            """
            <div class="metric-container">
                <div class="metric-label">Automated Review</div>
                <div class="metric-value" style="color: #fbbf24;">&lt; 500 ms</div>
                <div class="metric-sub">vs. 4-6 hrs manual review</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # 4. Search and Filter Bar
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([3, 2, 2, 2])
    with filter_col1:
        search_query = st.text_input(
            "Search Applications",
            placeholder="Search by Application ID, Applicant, or Feeder...",
            label_visibility="collapsed",
        )
    with filter_col2:
        utilities = sorted(list({a.get("utility", "") for a in apps if a.get("utility")}))
        selected_utility = st.selectbox(
            "Filter by Utility",
            options=["All Utilities"] + utilities,
            label_visibility="collapsed",
        )
    with filter_col3:
        selected_outcome = st.selectbox(
            "Filter by Status",
            options=["All Outcomes", "Approved (Fast-Track)", "Deficient (Requires Cure)"],
            label_visibility="collapsed",
        )
    with filter_col4:
        sort_by = st.selectbox(
            "Sort By",
            options=["ID (Ascending)", "Capacity: High to Low", "Capacity: Low to High"],
            label_visibility="collapsed",
        )

    # Apply Filters
    filtered_apps = list(apps)

    if search_query:
        q = search_query.lower()
        filtered_apps = [
            a
            for a in filtered_apps
            if q in a.get("application_id", "").lower()
            or q in a.get("applicant_name", "").lower()
            or q in a.get("feeder_id", "").lower()
        ]

    if selected_utility != "All Utilities":
        filtered_apps = [a for a in filtered_apps if a.get("utility") == selected_utility]

    if selected_outcome == "Approved (Fast-Track)":
        filtered_apps = [
            a for a in filtered_apps if a.get("expected_outcome") == "FAST_TRACK_APPROVED"
        ]
    elif selected_outcome == "Deficient (Requires Cure)":
        filtered_apps = [
            a for a in filtered_apps if a.get("expected_outcome") == "DEFICIENCY_ISSUED"
        ]

    # Apply Sorting
    if sort_by == "Capacity: High to Low":
        filtered_apps.sort(key=lambda x: x.get("capacity_kw", 0.0), reverse=True)
    elif sort_by == "Capacity: Low to High":
        filtered_apps.sort(key=lambda x: x.get("capacity_kw", 0.0))
    else:
        filtered_apps.sort(key=lambda x: x.get("application_id", ""))

    st.markdown(
        f"<div style='font-size: 0.9rem; color: #94a3b8; margin: 10px 0 16px 0;'>"
        f"Showing <strong>{len(filtered_apps)}</strong> of {total_apps} applications"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 5. Display Modes: Engineering Cards vs. Data Table
    tab_cards, tab_table = st.tabs(["📇 Engineering Queue Cards", "📋 Tabular Catalog"])

    with tab_cards:
        for app in filtered_apps:
            _render_application_card(app, client)

    with tab_table:
        table_records = []
        for a in filtered_apps:
            table_records.append(
                {
                    "Application ID": a.get("application_id"),
                    "Applicant": a.get("applicant_name"),
                    "Type": a.get("project_type"),
                    "Capacity (kW)": a.get("capacity_kw"),
                    "Utility": a.get("utility"),
                    "Feeder ID": a.get("feeder_id"),
                    "Status": a.get("expected_outcome"),
                    "Failing Screens": ", ".join(a.get("failing_screens", [])) or "None (Clean)",
                }
            )
        df = pd.DataFrame(table_records)
        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "Capacity (kW)": st.column_config.NumberColumn(format="%.1f kW"),
            },
            hide_index=True,
        )


def _render_application_card(app: dict[str, Any], client: InterconnectApiClient) -> None:
    """Render a card for an individual application with inspection actions."""
    app_id = app.get("application_id", "")
    outcome = app.get("expected_outcome", "")
    failing = app.get("failing_screens", [])

    if outcome == "FAST_TRACK_APPROVED":
        badge_html = '<span class="badge-pass">FAST-TRACK APPROVED</span>'
    elif outcome == "DEFICIENCY_ISSUED":
        badge_html = f'<span class="badge-fail">DEFICIENT ({len(failing)} VIOLATION)</span>'
    else:
        badge_html = '<span class="badge-review">UNDER REVIEW</span>'

    with st.container():
        st.markdown(
            f"""
            <div class="app-card">
                <div style="display: flex; justify-content: space-between; flex-wrap: wrap;">
                    <div>
                        <div class="app-card-title">{app_id}</div>
                        <div class="app-card-applicant">
                            {app.get("applicant_name")} &bull; {app.get("project_type")}
                        </div>
                    </div>
                    <div>
                        {badge_html}
                    </div>
                </div>
                <div style="margin-top: 10px; margin-bottom: 12px;">
                    <span class="spec-pill">⚡ Capacity: {app.get("capacity_kw", 0.0):.1f} kW</span>
                    <span class="spec-pill">🏛️ Utility: {app.get("utility")}</span>
                    <span class="spec-pill">🔌 Feeder: {app.get("feeder_id")}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_act1, col_act2, col_act3 = st.columns([2, 2, 4])
        with col_act1:
            if st.button("🔍 Inspect Details", key=f"inspect_{app_id}", use_container_width=True):
                st.session_state[f"show_detail_{app_id}"] = not st.session_state.get(
                    f"show_detail_{app_id}", False
                )
        with col_act2:
            if st.button(
                "⚡ Review Console",
                key=f"review_{app_id}",
                type="primary",
                use_container_width=True,
            ):
                st.session_state["selected_application_id"] = app_id
                st.session_state["current_page"] = "review_console"
                st.rerun()
        with col_act3:
            # Inline quick screening trigger
            if st.button(
                "▶️ Run Fast-Track Screening",
                key=f"run_inline_{app_id}",
                use_container_width=True,
            ):
                with st.spinner(f"Running LangGraph technical screening for {app_id}..."):
                    result = client.run_screening(app_id)
                    st.session_state[f"result_{app_id}"] = result

        # Render Inline Screening Result if available
        if f"result_{app_id}" in st.session_state:
            res = st.session_state[f"result_{app_id}"]
            time_ms = res.get("execution_time_ms", 0.0)
            scr_count = len(res.get("screen_results", []))
            def_count = len(res.get("deficiencies", []))
            has_letter = "Yes" if res.get("formal_letter_markdown") else "No"
            st.markdown(
                f"""
                <div style="background: rgba(15, 23, 42, 0.9);
                            border: 1px solid rgba(56, 189, 248, 0.3);
                            border-radius: 8px; padding: 14px; margin-top: 10px;">
                    <div style="font-weight: 600; color: #38bdf8; margin-bottom: 6px;">
                        Screening Result: {res.get("overall_outcome")} ({time_ms:.1f} ms)
                    </div>
                    <div style="font-size: 0.85rem; color: #cbd5e1;">
                        Evaluated {scr_count} screens &bull;
                        Found {def_count} deficiency(ies) &bull;
                        Formal memo generated: {has_letter}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Render Expanded Telemetry & Document Details
        if st.session_state.get(f"show_detail_{app_id}", False):
            with st.expander(f"Telemetry & Documents ({app_id})", expanded=True):
                details = client.get_application_details(app_id)
                telemetry = details.get("telemetry", {})
                files = details.get("files", {})

                st.markdown("**Grid Feeder Telemetry**")
                tel_c1, tel_c2, tel_c3, tel_c4 = st.columns(4)
                with tel_c1:
                    v_kv = telemetry.get(
                        "nominal_voltage_kv", telemetry.get("distribution_voltage_kv", 12.47)
                    )
                    st.metric("Distribution Voltage", f"{v_kv:.2f} kV")
                with tel_c2:
                    pk = telemetry.get("feeder_peak_load_kw", 0.0)
                    st.metric("Annual Peak Load", f"{pk:,.0f} kW")
                with tel_c3:
                    mn = telemetry.get("daytime_min_load_kw", 0.0)
                    st.metric("Daytime Min Load", f"{mn:,.0f} kW")
                with tel_c4:
                    der = telemetry.get("existing_der_kw", 0.0)
                    st.metric("Existing DER", f"{der:,.0f} kW")

                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                st.markdown("**Associated Application Documents**")
                for doc_label, doc_path in files.items():
                    title = doc_label.replace("_", " ").title()
                    if doc_path:
                        st.markdown(f"- 📄 **{title}**: `{doc_path}`")
                    else:
                        st.markdown(f"- 📄 **{title}**: *Not supplied*")

        st.markdown(
            "<hr style='border: none; border-top: 1px solid rgba(255, 255, 255, 0.06); "
            "margin: 18px 0;'>",
            unsafe_allow_html=True,
        )
