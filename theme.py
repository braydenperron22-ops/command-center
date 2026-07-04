"""Global visual theme: typography, chrome removal, base surface styling."""
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@200;300;400;500;600;700&display=swap');

html, body, [class^="st-"], [class*=" st-"], .stMarkdown, .stTextInput, .stButton, p, span, div {
    font-family: 'Manrope', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { visibility: hidden; height: 0; }
[data-testid="stAppViewContainer"] > .main { padding-top: 1.5rem; }
.block-container { padding-top: 1rem; max-width: 1100px; }

.cc-hero { display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 24px; margin-bottom: 6px; }
.cc-clock { font-size: 4.2rem; font-weight: 200; color: #f5f6f8; line-height: 1; letter-spacing: -1px; }
.cc-date { font-size: 0.95rem; font-weight: 500; color: rgba(255,255,255,0.55); text-transform: uppercase; letter-spacing: 1.5px; margin-top: 6px; }
.cc-synced { font-size: 0.78rem; color: rgba(255,255,255,0.35); margin-top: 2px; }

.cc-weather-inline { display: flex; align-items: center; gap: 14px; }
.cc-weather-icon { width: 52px; height: 52px; opacity: 0.92; }
.cc-weather-temp { font-size: 2.6rem; font-weight: 300; color: #f5f6f8; line-height: 1; }
.cc-weather-meta { font-size: 0.85rem; color: rgba(255,255,255,0.6); font-weight: 500; }
.cc-weather-range { font-size: 0.78rem; color: rgba(255,255,255,0.4); }

.cc-chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 4px; }
.cc-chip { display: flex; align-items: center; gap: 8px; padding: 7px 14px; border-radius: 999px;
    font-size: 0.83rem; font-weight: 500; backdrop-filter: blur(6px); }
.cc-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

.cc-section-label { font-size: 0.72rem; font-weight: 700; letter-spacing: 1.8px; text-transform: uppercase;
    color: rgba(255,255,255,0.42); margin-bottom: 10px; }

.st-key-glance_row .stColumn, .cc-panel { background: rgba(22, 26, 34, 0.42) !important; backdrop-filter: blur(16px);
    border-radius: 18px !important; border: 1px solid rgba(255,255,255,0.08) !important; }

.st-key-agenda_card, .st-key-email_card, .st-key-tasks_card,
.st-key-outlook_card, .st-key-deliveries_card {
    background: rgba(22, 26, 34, 0.42) !important;
    backdrop-filter: blur(16px);
    border-radius: 18px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
}

.cc-upcoming { margin-top: 14px; padding: 10px 12px; border-radius: 12px;
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); }
.cc-upcoming-label { font-size: 0.62rem; font-weight: 700; letter-spacing: 1.6px; text-transform: uppercase;
    color: rgba(255,255,255,0.32); margin-bottom: 6px; }
.cc-upcoming .cc-row { padding: 6px 0; font-size: 0.82rem; }
.cc-upcoming .cc-row-title { color: rgba(255,255,255,0.68); font-weight: 400; }
.cc-upcoming .cc-row-meta { color: rgba(255,255,255,0.36); font-size: 0.72rem; }

.cc-row { display: flex; justify-content: space-between; align-items: baseline; padding: 9px 0;
    border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 0.92rem; }
.cc-row:last-child { border-bottom: none; }
.cc-row-title { color: rgba(255,255,255,0.85); font-weight: 500; }
.cc-row-meta { color: rgba(255,255,255,0.4); font-size: 0.78rem; white-space: nowrap; margin-left: 12px; }
.cc-empty { color: rgba(255,255,255,0.35); font-size: 0.88rem; font-style: normal; padding: 4px 0; }

hr { border-color: rgba(255,255,255,0.08) !important; margin: 1.6rem 0 !important; }
</style>
"""


def inject_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
