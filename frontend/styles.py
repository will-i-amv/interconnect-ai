"""Modern custom CSS styling and design system for the InterconnectAI Streamlit UI."""

from __future__ import annotations

CUSTOM_CSS = """
<style>
/* Import Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* Global Root Styling */
:root {
    --bg-primary: #0b0f19;
    --bg-secondary: #111827;
    --bg-card: rgba(17, 24, 39, 0.7);
    --border-color: rgba(255, 255, 255, 0.08);
    --border-highlight: rgba(56, 189, 248, 0.3);
    --accent-cyan: #06b6d4;
    --accent-blue: #3b82f6;
    --accent-emerald: #10b981;
    --accent-rose: #f43f5e;
    --accent-amber: #f59e0b;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

code, pre {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Metric KPI Card Styling */
.metric-container {
    display: flex;
    flex-direction: column;
    background: linear-gradient(135deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 0.7) 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(8px);
    transition: transform 0.2s ease, border-color 0.2s ease;
}

.metric-container:hover {
    transform: translateY(-2px);
    border-color: rgba(56, 189, 248, 0.3);
}

.metric-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
}

.metric-value {
    font-size: 1.85rem;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -0.02em;
}

.metric-sub {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 4px;
}

/* Status Badges */
.badge-pass {
    display: inline-flex;
    align-items: center;
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}

.badge-fail {
    display: inline-flex;
    align-items: center;
    background: rgba(244, 63, 94, 0.15);
    color: #fb7185;
    border: 1px solid rgba(244, 63, 94, 0.3);
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}

.badge-review {
    display: inline-flex;
    align-items: center;
    background: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}

.badge-info {
    display: inline-flex;
    align-items: center;
    background: rgba(56, 189, 248, 0.15);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.3);
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
}

/* Card for Application Listing */
.app-card {
    background: rgba(17, 24, 39, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    transition: all 0.2s ease-in-out;
}

.app-card:hover {
    border-color: rgba(56, 189, 248, 0.4);
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
}

.app-card-title {
    font-size: 1.15rem;
    font-weight: 600;
    color: #f1f5f9;
    margin-bottom: 4px;
}

.app-card-applicant {
    font-size: 0.88rem;
    color: #94a3b8;
    margin-bottom: 12px;
}

.spec-pill {
    display: inline-block;
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.05);
    color: #cbd5e1;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.78rem;
    margin-right: 6px;
    margin-bottom: 6px;
    font-family: 'JetBrains Mono', monospace;
}

/* Header Banner */
.header-banner {
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(99, 102, 241, 0.15) 100%);
    border: 1px solid rgba(56, 189, 248, 0.2);
    border-radius: 14px;
    padding: 24px 28px;
    margin-bottom: 24px;
}

.header-title {
    font-size: 2rem;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.03em;
    margin-bottom: 6px;
}

.header-desc {
    font-size: 0.95rem;
    color: #cbd5e1;
    max-width: 850px;
    line-height: 1.5;
}
</style>
"""


def inject_custom_css() -> None:
    """Inject the InterconnectAI custom CSS styling into the Streamlit session."""
    import streamlit as st

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
