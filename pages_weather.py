"""Weather page: Environment Canada's own 7-day outlook plus their live
station reading (see ec_forecast.py) — the same authoritative source
already driving the hero row's rain nowcast, extended out to the full
week and full detail (precip chance, wind, UV, current conditions) EC
already publishes rather than pulled from a different provider just to
get more of it.
"""

import streamlit as st

import ec_forecast
from icons import icon_for


def _render_current(current: dict | None) -> None:
    if not current:
        return
    icon_svg = icon_for(current["category"], "day")
    wind = ""
    if current.get("wind_speed") is not None:
        gust = f" gust {current['wind_gust']}" if current.get("wind_gust") else ""
        wind_dir = current.get("wind_dir") or ""
        wind = f"{wind_dir} {current['wind_speed']} km/h{gust}"
    tendency_arrow = {"falling": "↓", "rising": "↑", "steady": "→"}.get(current.get("pressure_tendency"), "")

    # EC's station can independently omit any of humidity/dewpoint/
    # pressure even while temperature still reports (a real sensor-gap
    # pattern, not hypothetical) — only temp is guaranteed non-None by
    # ec_forecast.current_conditions(), so every other metric here needs
    # its own None guard rather than assuming the whole reading is
    # all-or-nothing.
    humidity_html = f"<span>Humidity {current['humidity']}%</span>" if current.get("humidity") is not None else ""
    wind_html = f"<span>Wind {wind}</span>" if wind else ""
    dewpoint_html = (
        f"<span>Dewpoint {current['dewpoint_c']:.0f}°C</span>" if current.get("dewpoint_c") is not None else ""
    )
    pressure_html = (
        f"<span>Pressure {current['pressure_kpa']:.1f} kPa {tendency_arrow}</span>"
        if current.get("pressure_kpa") is not None else ""
    )

    st.markdown(
        f"""<div class="tile weather-current-tile">
            <div class="tile-label compact">CURRENT · {current['station'].upper()}</div>
            <div class="weather-current-row">
                <div class="weather-current-icon">{icon_svg}</div>
                <div class="weather-current-temp">{current['temp_c']:.0f}°C</div>
                <div class="weather-current-condition">{current['condition']}</div>
                <div class="weather-current-metrics">
                    {humidity_html}{wind_html}{dewpoint_html}{pressure_html}
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

    _render_current(ec_forecast.current_conditions())
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
