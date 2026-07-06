"""Renders the weather-statement banner: an active Environment Canada
alert takes priority; our own extreme-heat/extreme-cold fallback only
ever shows when EC has nothing active for the region."""

import streamlit as st

import ec_alerts
from config import EXTREME_COLD_THRESHOLD_C, EXTREME_HEAT_THRESHOLD_C


def _fallback_text(weather: dict | None) -> str | None:
    if not weather:
        return None
    high = weather.get("forecast_high_c")
    low = weather.get("forecast_low_c")
    if high is not None and high >= EXTREME_HEAT_THRESHOLD_C:
        return f"Extreme Heat Advisory — today's high near {high:.0f}°C"
    if low is not None and low <= EXTREME_COLD_THRESHOLD_C:
        return f"Extreme Cold Advisory — today's low near {low:.0f}°C"
    return None


def render(weather: dict | None) -> None:
    alerts = ec_alerts.fetch_alerts()
    if alerts:
        # Several alerts can technically be active at once (e.g. a
        # statement upgraded to a warning); showing just the first one
        # keeps the bar readable rather than concatenating everything —
        # but silently dropping the rest with no indication would hide a
        # second, possibly more severe, active alert entirely. A "+N
        # more" suffix at least surfaces that there's more to know.
        alert = alerts[0]
        text = f"{alert['title']}" + (f" — {alert['summary']}" if alert["summary"] else "")
        if len(alerts) > 1:
            text += f" (+{len(alerts) - 1} more alert{'s' if len(alerts) > 2 else ''})"
        label = "Environment Canada"
    else:
        text = _fallback_text(weather)
        if not text:
            return
        label = "Weather Advisory"

    st.markdown(
        f"""<div class="weather-statement-bar">
            <span class="weather-statement-dot"></span>
            <span class="weather-statement-label">{label}</span>
            <span class="weather-statement-text">{text}</span>
        </div>""",
        unsafe_allow_html=True,
    )
