"""Rendering helpers for the severity alert chip row."""
import streamlit as st

_SEVERITY_ORDER = {"red": 0, "yellow": 1, "neutral": 2}
_SEVERITY_STYLE = {
    "red": ("rgba(255, 90, 90, 0.14)", "rgba(255, 120, 120, 0.3)", "#ffb3b3", "#ff5a5a"),
    "yellow": ("rgba(255, 200, 80, 0.13)", "rgba(255, 210, 100, 0.28)", "#ffdf9e", "#ffc850"),
    "neutral": ("rgba(255, 255, 255, 0.06)", "rgba(255, 255, 255, 0.12)", "rgba(255,255,255,0.7)", "rgba(255,255,255,0.4)"),
}


def render_alert_bar(alerts: list) -> None:
    if not alerts:
        return
    alerts = sorted(alerts, key=lambda a: _SEVERITY_ORDER.get(a.get("severity", "neutral"), 2))
    chips = []
    for a in alerts:
        severity = a.get("severity", "neutral")
        bg, border, text, dot = _SEVERITY_STYLE.get(severity, _SEVERITY_STYLE["neutral"])
        chips.append(
            f'<div class="cc-chip" style="background:{bg};border:1px solid {border};color:{text};">'
            f'<span class="cc-dot" style="background:{dot};"></span>{a.get("message", "")}</div>'
        )
    st.markdown(f'<div class="cc-chip-row">{"".join(chips)}</div>', unsafe_allow_html=True)
