"""Renders the macro-regime banner — see regime.py for the
classification this displays. Called from pages_home.py only: this is
a US macro read, so it belongs with the page that's already showing
US/Canada macro indicators, not persistent across every page the way
the clock/weather is.
"""

import streamlit as st

import market_internals as mi
import regime


def render(readings: dict) -> None:
    try:
        confidence = mi.confidence_index()
        credit = mi.price_ratio("HYG", "LQD")
        breadth = mi.price_ratio("RSP", "SPY")
    except Exception:
        confidence = credit = breadth = None

    data = regime.classify(readings, confidence, credit, breadth)
    if not data:
        return

    macro_positive = data["growth"] >= 0 and data["inflation"] <= 0
    if data["confirms"] is None:
        tone = "good" if macro_positive else "bad"
    elif data["confirms"]:
        tone = "good" if macro_positive else "bad"
    else:
        # Macro and market risk appetite disagree — genuinely worth
        # flagging on its own rather than forcing it into good/bad.
        tone = "neutral"

    st.markdown(
        f"""<div class="regime-bar regime-bar-{tone}">
            <span class="regime-dot"></span>
            <span class="regime-label">Macro Regime</span>
            <span class="regime-text">{data['narrative']}</span>
        </div>""",
        unsafe_allow_html=True,
    )
