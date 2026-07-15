"""Radar page: Environment Canada's own live radar reflectivity,
centered on Corbeil, plus the approach/recede tracker built on top of
it (see ec_radar.py) — split out from the Weather page since a live map
deserves real screen space of its own, not a shared column next to the
7-day forecast.
"""

import streamlit as st

import ec_forecast
import ec_radar


def _format_minutes(total_minutes: float) -> str:
    total = max(0, int(total_minutes))
    hours, minutes = divmod(total, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes} min"


def render() -> None:
    st.markdown('<div class="page-title page-title-radar">Live Radar — Corbeil</div>', unsafe_allow_html=True)

    current = ec_forecast.current_conditions()
    kind = "snow" if current and current.get("category") == "snow" else "rain"
    label = "Snow" if kind == "snow" else "Rain"

    forecast = ec_radar.precip_forecast(kind)
    if forecast is not None:
        summary = f"{label} approaching · arriving in {_format_minutes(forecast['eta_minutes'])}"
        if forecast["end_minutes"] is not None:
            summary += f" · clearing in {_format_minutes(forecast['end_minutes'])}"
        badge_class = "badge-bad"
    else:
        summary = "Nothing approaching right now"
        badge_class = "badge-good"

    st.markdown(
        f"""<div class="tile weather-radar-tile weather-radar-tile-large">
            <div class="tile-label compact">LIVE RADAR · {kind.upper()} · CORBEIL</div>
            <div class="weather-radar-frame weather-radar-frame-large">
                <img class="weather-radar-image" src="{ec_radar.radar_image_url(kind)}" />
                <div class="weather-radar-marker"></div>
            </div>
            <div class="badge {badge_class}">{summary}</div>
        </div>""",
        unsafe_allow_html=True,
    )
