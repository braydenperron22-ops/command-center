"""Weather page: the 7-day outlook (see weather_client.daily_forecast)
plus Environment Canada's own live station reading for full atmospheric
detail (humidity/dewpoint/pressure — EC-only, Open-Meteo's own current
endpoint doesn't carry those).

Session follow-up: "I think Open-Meteo is a little more accurate... I
wanna start using it as our main provider... is there a way to make
Open-Meteo bulletproof." The 7-day outlook itself is now Open-Meteo
primary with EC as an automatic fallback (see weather_client.
daily_forecast's own docstring) — genuine redundancy across two
independent, free, no-key providers. The current-conditions tile below
stays EC-sourced deliberately: it's showing detail (dewpoint, pressure,
pressure tendency) neither provider's own forecast carries, a different
feature from the forecast accuracy question that prompted this change.
"""

import streamlit as st

import ec_forecast
import weather_client
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


def render() -> None:
    st.markdown('<div class="page-title page-title-weather">7-Day Forecast</div>', unsafe_allow_html=True)

    _render_current(ec_forecast.current_conditions())
    st.markdown('<div style="height: 0.6rem;"></div>', unsafe_allow_html=True)

    days = weather_client.daily_forecast()
    if not days:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Forecast unavailable right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    # One reading per day now (weather_client.daily_forecast's own flat
    # shape — see its docstring for why this no longer splits into a
    # Day/Night pair the way ec_forecast.daily_forecast used to):
    # Open-Meteo's daily endpoint doesn't carry that finer split at all,
    # and the EC-fallback path is normalized down to this same shape
    # too, so this is the one card layout regardless of which provider
    # actually answered.
    chance_html_by_day = [
        f'<span class="weather-day-chance">☔ {d["precip_chance"]}%</span>' if d["precip_chance"] else ""
        for d in days
    ]
    uv_html_by_day = [
        f'<span class="weather-day-uv">UV {d["uv_index"]}</span>' if d.get("uv_index") is not None else ""
        for d in days
    ]

    cols = st.columns(len(days))
    for i, day in enumerate(days):
        icon_svg = icon_for(day["category"], "day" if day["high"] is not None else "night")
        high_html = f'<span class="weather-day-high">{day["high"]}°</span>' if day["high"] is not None else ""
        low_html = f'<span class="weather-day-low">{day["low"]}°</span>' if day["low"] is not None else ""
        wind_html = f'<div class="weather-day-wind">{day["wind"]}</div>' if day.get("wind") else ""
        # wind_html folded onto the closing tag's line rather than given
        # its own — when it's "" (no wind detail), a lone whitespace
        # line ahead of an indented "</div>" reads to the markdown
        # parser as a blank line followed by an indented code block,
        # and it renders that closing tag as literal text instead of
        # parsing it as HTML (same class of bug fixed earlier in
        # commute_reminder.py/pages_today.py).
        with cols[i]:
            st.markdown(
                f"""<div class="tile weather-day-tile">
                    <div class="tile-label compact">{day['name'].upper()}</div>
                    <div class="weather-day-icon">{icon_svg}</div>
                    <div class="weather-day-temps">{high_html}{low_html}</div>
                    <div class="weather-day-period">
                    <div class="weather-day-period-label">{chance_html_by_day[i]}{uv_html_by_day[i]}</div>
                    <div class="weather-day-summary">{day['condition']}</div>
                    {wind_html}</div></div>""",
                unsafe_allow_html=True,
            )
