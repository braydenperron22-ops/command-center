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


def _tracking_overlay_html(overlay: dict | None) -> str:
    """A line drawn straight from the tracked echo to the user's own
    marker, plus a label at the echo's position — turns the map from
    "here's a picture, and separately here's a text badge" into an
    actual visual tracker. Percentage-based (0-100), same coordinate
    space the fixed location marker already uses, so it scales
    correctly with the frame regardless of its rendered size. Dashed
    and animated while there's an active approaching/arrived event (see
    ec_radar.tracking_overlay) — a cell that's merely nearby but not
    closing in gets a plain static line, not the same urgency treatment."""
    if overlay is None:
        return ""
    x, y = overlay["x_pct"], overlay["y_pct"]
    modifier = "approaching" if overlay["active"] else "idle"
    minutes_text = f" · {_format_minutes(overlay['minutes'])}" if overlay["minutes"] is not None else ""
    label_text = f"{overlay['distance_km']:.0f} km{minutes_text}"
    return f"""<svg class="weather-radar-track" viewBox="0 0 100 100" preserveAspectRatio="none">
            <line x1="{x:.1f}" y1="{y:.1f}" x2="50" y2="50" class="weather-radar-track-line weather-radar-track-line-{modifier}" />
        </svg>
        <div class="weather-radar-storm-marker weather-radar-storm-marker-{modifier}" style="left:{x:.1f}%; top:{y:.1f}%;"></div>
        <div class="weather-radar-storm-label" style="left:{x:.1f}%; top:{y:.1f}%;">{label_text}</div>"""


def render() -> None:
    st.markdown('<div class="page-title page-title-radar">Live Radar — Corbeil</div>', unsafe_allow_html=True)

    current = ec_forecast.current_conditions()
    kind = "snow" if current and current.get("category") == "snow" else "rain"
    label = "Snow" if kind == "snow" else "Rain"

    status = ec_radar.precip_status(kind)
    if status is not None and status["state"] == "arrived":
        summary = f"Clears in {_format_minutes(status['minutes'])}" if status["minutes"] is not None else f"{label} now"
        badge_class = "badge-bad"
    elif status is not None:
        summary = f"{label} in {_format_minutes(status['minutes'])}"
        badge_class = "badge-bad"
    else:
        summary = "Nothing approaching right now"
        badge_class = "badge-good"

    overlay_html = _tracking_overlay_html(ec_radar.tracking_overlay(kind))

    st.markdown(
        f"""<div class="tile weather-radar-tile weather-radar-tile-large">
            <div class="tile-label compact">LIVE RADAR · {kind.upper()} · CORBEIL</div>
            <div class="weather-radar-frame weather-radar-frame-large">
                <img class="weather-radar-image" src="{ec_radar.radar_image_url(kind)}" />
                <div class="weather-radar-marker"></div>
                {overlay_html}</div>
            <div class="badge {badge_class}">{summary}</div>
        </div>""",
        unsafe_allow_html=True,
    )
