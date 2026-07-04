"""Rendering helpers for the severity alert bar."""
import streamlit as st

_SEVERITY_ORDER = {"red": 0, "yellow": 1, "neutral": 2}
_SEVERITY_STYLE = {
    "red": ("#4a1414", "#ff6b6b", "#ffdcdc"),
    "yellow": ("#4a3e14", "#ffd166", "#fff3d1"),
    "neutral": ("#20242c", "#9aa5b1", "#e4e7eb"),
}


def render_alert_bar(alerts: list) -> None:
    if not alerts:
        return
    alerts = sorted(alerts, key=lambda a: _SEVERITY_ORDER.get(a.get("severity", "neutral"), 2))
    rows = []
    for a in alerts:
        severity = a.get("severity", "neutral")
        bg, border, text = _SEVERITY_STYLE.get(severity, _SEVERITY_STYLE["neutral"])
        rows.append(
            f'<div style="background:{bg};border-left:4px solid {border};color:{text};'
            f'padding:10px 16px;border-radius:8px;margin-bottom:8px;font-size:0.95rem;">'
            f'{a.get("message", "")}</div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)
