"""Weather page: Environment Canada's own 7-day outlook plus their live
station reading (see ec_forecast.py) — the same authoritative source
already driving the hero row's rain nowcast, extended out to the full
week and full detail (precip chance, wind, UV, current conditions) EC
already publishes rather than pulled from a different provider just to
get more of it.
"""

import streamlit as st

import ec_forecast
import ec_radar
from icons import icon_for


def _render_radar(current: dict | None) -> None:
    """Live radar reflectivity, not a forecast — see ec_radar.py for
    why this is the closest thing to Apple/Dark-Sky-style nowcasting
    this dashboard can reasonably offer: the actual raw signal that
    class of app is built on, without their proprietary storm-tracking
    layered on top. Rain layer by default; switches to the snow
    composite when current conditions say snow, since the rain layer
    reads empty during a snow event."""
    kind = "snow" if current and current.get("category") == "snow" else "rain"
    st.markdown(
        f"""<div class="tile weather-radar-tile">
            <div class="tile-label compact">LIVE RADAR · {kind.upper()} · ENVIRONMENT CANADA</div>
            <div class="weather-radar-frame">
                <img class="weather-radar-image" src="{ec_radar.radar_image_url(kind)}" />
                <div class="weather-radar-marker"></div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _render_current(current: dict | None) -> None:
    if not current:
        return
    icon_svg = icon_for(current["category"], "day")
    wind = ""
    if current.get("wind_speed") is not None:
        gust = f" gust {current['wind_gust']}" if current.get("wind_gust") else ""
        wind = f"{current.get('wind_dir', '')} {current['wind_speed']} km/h{gust}"
    tendency_arrow = {"falling": "↓", "rising": "↑", "steady": "→"}.get(current.get("pressure_tendency"), "")

    st.markdown(
        f"""<div class="tile weather-current-tile">
            <div class="tile-label compact">CURRENT · {current['station'].upper()}</div>
            <div class="weather-current-row">
                <div class="weather-current-icon">{icon_svg}</div>
                <div class="weather-current-temp">{current['temp_c']:.0f}°C</div>
                <div class="weather-current-condition">{current['condition']}</div>
                <div class="weather-current-metrics">
                    <span>Humidity {current['humidity']}%</span>
                    <span>Wind {wind}</span>
                    <span>Dewpoint {current['dewpoint_c']:.0f}°C</span>
                    <span>Pressure {current['pressure_kpa']:.1f} kPa {tendency_arrow}</span>
                </div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _period_html(detail: dict | None, label: str) -> str:
    if not detail:
        return ""
    chance_html = (
        f'<span class="weather-day-chance">☔ {detail["precip_chance"]}%</span>'
        if detail["precip_chance"] is not None else ""
    )
    uv_html = f'<span class="weather-day-uv">UV {detail["uv_index"]}</span>' if detail["uv_index"] is not None else ""
    wind_html = f'<div class="weather-day-wind">{detail["wind"]}</div>' if detail["wind"] else ""
    # wind_html folded onto the closing tag's line rather than given its
    # own — when it's "" (no wind detail), a lone whitespace line ahead
    # of an indented "</div>" reads to the markdown parser as a blank
    # line followed by an indented code block, and it renders that
    # closing tag as literal text instead of parsing it as HTML (same
    # class of bug fixed earlier in commute_reminder.py/pages_today.py).
    return f"""<div class="weather-day-period">
        <div class="weather-day-period-label">{label}{chance_html}{uv_html}</div>
        <div class="weather-day-summary">{detail['summary']}</div>
        {wind_html}</div>"""


def render() -> None:
    st.markdown('<div class="page-title page-title-weather">7-Day Forecast — Environment Canada</div>', unsafe_allow_html=True)

    current = ec_forecast.current_conditions()
    left, right = st.columns([3, 2])
    with left:
        _render_current(current)
    with right:
        _render_radar(current)
    st.markdown('<div style="height: 0.6rem;"></div>', unsafe_allow_html=True)

    days = ec_forecast.daily_forecast()
    if not days:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Forecast unavailable right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    cols = st.columns(len(days))
    for i, day in enumerate(days):
        icon_svg = icon_for(day["category"], "day" if day["high"] is not None else "night")
        high_html = f'<span class="weather-day-high">{day["high"]}°</span>' if day["high"] is not None else ""
        low_html = f'<span class="weather-day-low">{day["low"]}°</span>' if day["low"] is not None else ""
        periods_html = _period_html(day["day"], "Day") + _period_html(day["night"], "Night")
        with cols[i]:
            st.markdown(
                f"""<div class="tile weather-day-tile">
                    <div class="tile-label compact">{day['name'].upper()}</div>
                    <div class="weather-day-icon">{icon_svg}</div>
                    <div class="weather-day-temps">{high_html}{low_html}</div>
                    {periods_html}</div>""",
                unsafe_allow_html=True,
            )
