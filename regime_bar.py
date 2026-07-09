"""Renders the persistent macro-regime banner — see regime.py for the
classification this displays. Sits with the app's other persistent
elements (clock/weather, top news alert) rather than in the page
rotation: the whole point is a glance-any-time read, not something
worth waiting through a 90-second rotation to see.
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
