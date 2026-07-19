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


def _precip_timing_phrase(status: dict | None) -> str | None:
    """"in 45 min" / "approaching" / "clears in 20 min" / "here now" —
    None if there's no confirmed timing yet at all. Same reasoning as
    app.py's identical helper: severity and ETA are two different
    questions, so a "Heavy rain" badge shouldn't drop the timing a
    plain "Rain" badge would still show."""
    if status is None:
        return None
    if status["state"] == "arrived":
        return f"clears in {_format_minutes(status['minutes'])}" if status["minutes"] is not None else "here now"
    return f"in {_format_minutes(status['minutes'])}" if status["minutes"] is not None else "approaching"


def _city_markers_html(cities: list[dict]) -> str:
    """Small neutral-gray dots + labels for real nearby towns (see
    ec_radar.nearby_city_markers) — deliberately much quieter than the
    blue "you" marker or the storm marker, since these are just
    reference points for reading the map, not something to react to."""
    return "".join(
        f'<div class="weather-radar-city-marker" style="left:{c["x_pct"]:.1f}%; top:{c["y_pct"]:.1f}%;"></div>'
        f'<div class="weather-radar-city-label" style="left:{c["x_pct"]:.1f}%; top:{c["y_pct"]:.1f}%;">{c["label"]}</div>'
        for c in cities
    )


def _tracking_overlay_html(overlay: dict | None) -> str:
    """A plain text label at the tracked echo's own position, showing
    where on the map it actually is. Percentage-based (0-100), same
    coordinate space the fixed location marker already uses, so it
    scales correctly with the frame regardless of its rendered size.
    Used to also draw a glowing dot marker plus a connecting line
    straight to the user's own marker — session feedback: both read as
    implying more geometric precision than the underlying radar data
    can really promise, misleading even once the tracking logic itself
    was accurate — so this is now just the label on its own."""
    if overlay is None:
        return ""
    x, y = overlay["x_pct"], overlay["y_pct"]
    minutes_text = f" · {_format_minutes(overlay['minutes'])}" if overlay["minutes"] is not None else ""
    label_text = f"{overlay['distance_km']:.0f} km {overlay['direction']}{minutes_text}"
    return f'<div class="weather-radar-storm-label" style="left:{x:.1f}%; top:{y:.1f}%;">{label_text}</div>'


def render() -> None:
    st.markdown('<div class="page-title page-title-radar">Live Radar — Corbeil</div>', unsafe_allow_html=True)

    current = ec_forecast.current_conditions()
    kind = "snow" if current and current.get("category") == "snow" else "rain"
    label = "Snow" if kind == "snow" else "Rain"

    # Checked before (and independent of) precip_status below — that
    # one requires a CONFIRMED approaching trend (see
    # ec_radar._record_and_trend), which a genuinely severe cell can
    # still be waiting on right after a fresh detection or re-scan.
    # Confirmed live this caused a real contradiction: this badge said
    # "nothing approaching" while the hero row (app.py, which already
    # checks severity first) said "Heavy rain" for the exact same storm
    # at the exact same moment.
    severe = ec_radar.severe_precip_status(kind)
    status = ec_radar.precip_status(kind)
    if severe is not None:
        timing = _precip_timing_phrase(status)
        summary = (
            f"Heavy {label.lower()} {timing} · {severe['mm_h']:.0f} mm/h"
            if timing else f"Heavy {label.lower()} · {severe['mm_h']:.0f} mm/h"
        )
        badge_class = "badge-bad"
    elif status is not None and status["state"] == "arrived":
        summary = f"Clears in {_format_minutes(status['minutes'])}" if status["minutes"] is not None else f"{label} now"
        badge_class = "badge-bad"
    elif status is not None:
        # Guarded the same way the "arrived" branch above already is —
        # see app.py's identical guard for why, even without a concrete
        # path that currently constructs a None here.
        summary = (
            f"{label} in {_format_minutes(status['minutes'])}"
            if status["minutes"] is not None else f"{label} approaching"
        )
        badge_class = "badge-bad"
    else:
        summary = "Nothing approaching right now"
        badge_class = "badge-good"

    overlay_html = _tracking_overlay_html(ec_radar.tracking_overlay(kind))
    city_markers_html = _city_markers_html(ec_radar.nearby_city_markers())

    # A short looping GIF of the last few real radar pulls, backfilled
    # straight from EC's own TIME dimension rather than waited-for
    # organically (session request: cache and play the last few so
    # storm motion is actually visible; then "pull previous radar
    # images directly from the source without having to build the
    # cache manually") — falls back to the plain static frame only in
    # the rare case that backfill hasn't produced 2+ real frames yet.
    loop_uri = ec_radar.radar_loop_data_uri(kind)
    image_src = loop_uri if loop_uri is not None else ec_radar.radar_image_url(kind)

    # Plain "moving NE at 32 km/h" readout of the real measured
    # trajectory (see ec_radar.storm_motion) — shown even when it isn't
    # a confirmed direct hit on the exact location, so a system that's
    # genuinely just passing by to one side still reads as real,
    # grounded information rather than nothing at all. "" when there's
    # no measured motion to report yet.
    motion_label = ec_radar.storm_motion_label(kind)
    motion_html = f'<div class="tile-prev">{motion_label}</div>' if motion_label else ""

    # One flat line, no embedded newlines/indentation — same bug class
    # already documented in pages_weather.py/pages_today.py: a
    # multi-line indented f-string reads fine to the markdown parser
    # AS LONG AS every line has content, but motion_html is "" whenever
    # there's no measured storm motion (confirmed live: any quiet/clear
    # day with nothing on radar), which leaves a blank line in the
    # middle of what CommonMark treats as one continuous raw-HTML
    # block. A blank line ends that block, and everything after gets
    # reparsed as a NEW block — indented 12 spaces, which CommonMark
    # reads as an indented code block, rendering the whole radar frame
    # as literal escaped text instead of the actual map.
    st.markdown(
        f'<div class="tile weather-radar-tile weather-radar-tile-large">'
        f'<div class="tile-label compact">LIVE RADAR · {kind.upper()} · CORBEIL</div>'
        f'<div class="badge {badge_class}">{summary}</div>'
        f'{motion_html}'
        f'<div class="weather-radar-frame weather-radar-frame-large">'
        f'<img class="weather-radar-image" src="{image_src}" />'
        f'{city_markers_html}'
        f'<div class="weather-radar-marker"></div>'
        f'{overlay_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
