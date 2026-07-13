"""Renders the weather-statement banner: an active Environment Canada
alert takes priority; our own extreme-heat/extreme-cold fallback only
ever shows when EC has nothing active for the region."""

import streamlit as st

import ec_alerts
from config import EXTREME_COLD_THRESHOLD_C, EXTREME_HEAT_THRESHOLD_C


def _severity(title: str) -> str:
    """"warning" (most severe) > "watch" > "statement" — EC's own title
    text always contains one of these words (e.g. "YELLOW WARNING -
    HEAT...", "Severe Thunderstorm Warning", "Special Weather
    Statement"), so this needs no separate severity field from the feed
    itself. Drives how hard the bar visually pulls attention — a
    statement shouldn't compete for the eye the same way a warning
    does."""
    t = title.lower()
    if "warning" in t:
        return "warning"
    if "watch" in t:
        return "watch"
    return "statement"


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
        # A real EC alert earns the bold, high-contrast treatment
        # (theme.py's weather-statement-{severity} modifiers) — our own
        # manual heat/cold fallback below deliberately keeps the
        # original muted styling instead, since it's a self-generated
        # heuristic, not an official warning, and shouldn't visually
        # compete with a genuine one.
        bar_class = f"weather-statement-bar weather-statement-{_severity(alert['title'])}"
    else:
        text = _fallback_text(weather)
        if not text:
            return
        label = "Weather Advisory"
        bar_class = "weather-statement-bar"

    st.markdown(
        f"""<div class="{bar_class}">
            <span class="weather-statement-dot"></span>
            <span class="weather-statement-label">{label}</span>
            <span class="weather-statement-text">{text}</span>
        </div>""",
        unsafe_allow_html=True,
    )
