"""Hourly Forecast page: hour-by-hour outlook (see weather_client.
hourly_forecast) — replaces the live radar map. Session history: "get
rid of radar and replace it with hourly weather data" -> "make it look
better and a little more complete" -> "I think Open-Meteo is a little
more accurate... I wanna start using it as our main provider... is
there a way to make Open-Meteo bulletproof."

Open-Meteo primary, Environment Canada as an automatic fallback on any
failure (see weather_client.hourly_forecast's own docstring) — genuine
redundancy across two independent, free, no-key providers rather than
a single point of failure, not a one-time swap that just trades which
provider is the single point of failure.

Shows the next HOURS_SHOWN hours as columns, the same "one tile per
period" shape pages_weather.py's 7-day row already uses — a fixed count
rather than a scrolling timeline, since this kiosk has no way to scroll
to reveal anything below/beyond the fold (see this session's own
"no-scroll content" precedent).
"""

import streamlit as st

import scenery
import weather_client
from icons import icon_for, label_for

HOURS_SHOWN = 12


def _hour_label(at) -> str:
    # "%-I %p" (e.g. "3 PM") rather than 24h time — matches every other
    # time-of-day label already shown elsewhere in this app.
    return at.strftime("%-I %p")


def _render_current(weather: dict | None) -> None:
    """Same real reading (and the same Open-Meteo-primary/EC-fallback
    resilience) the hero row's own clock/weather header already uses —
    this page's own header is just a bigger, dedicated version of that
    same number, not a separate source of truth, so the two can never
    disagree with each other the way this page's first version (reading
    EC's own station directly here, Open-Meteo up top) briefly could."""
    if not weather:
        return
    code = weather.get("weather_code") or 0
    category = scenery.condition_category(code)
    icon_svg = icon_for(category, "day")
    feels_like = weather.get("feels_like_c")
    feels_html = f"<span>Feels like {feels_like:.0f}°C</span>" if feels_like is not None else ""
    uv = weather.get("uv_index")
    uv_html = f"<span>UV {uv:.0f}</span>" if uv is not None else ""

    st.markdown(
        f"""<div class="tile weather-current-tile">
            <div class="tile-label compact">CURRENT CONDITIONS</div>
            <div class="weather-current-row">
                <div class="weather-current-icon">{icon_svg}</div>
                <div class="weather-current-temp">{weather['temp_c']:.0f}°C</div>
                <div class="weather-current-condition">{label_for(code)}</div>
                <div class="weather-current-metrics">
                    {feels_html}{uv_html}
                </div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _day_or_night(at, sunrise, sunset) -> str:
    """"day"/"night" for one hourly reading's own clock time — compared
    against sunrise/sunset's time-of-day only (not date), so an hour
    that lands on tomorrow's calendar date still gets a sensible answer
    without needing a second astral calculation for that date. Good
    enough for picking an icon (sunrise/sunset drift only a minute or
    two day to day this time of year), not precise enough for anything
    that actually needed the real transition moment."""
    if sunrise is None or sunset is None:
        return "day"
    t = at.time()
    return "day" if sunrise.time() <= t <= sunset.time() else "night"


def render() -> None:
    st.markdown('<div class="page-title page-title-hourly">Hourly Forecast</div>', unsafe_allow_html=True)

    weather = weather_client.fetch_weather()
    _render_current(weather)
    st.markdown('<div class="internals-section-gap"></div>', unsafe_allow_html=True)

    hours = weather_client.hourly_forecast()[:HOURS_SHOWN]
    if not hours:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Forecast unavailable right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    sunrise = weather.get("sunrise") if weather else None
    sunset = weather.get("sunset") if weather else None

    cols = st.columns(len(hours))
    for i, hour in enumerate(hours):
        phase = _day_or_night(hour["at"], sunrise, sunset)
        icon_svg = icon_for(hour["category"], phase)
        # Only shown when there's a real chance — an hourly reading
        # always carries a structured precip_chance value even at a
        # genuine 0% (both providers), unlike the daily forecast's own
        # normalized precip_chance (which can be None when neither
        # provider's own reading for that day mentions one at all) — so
        # this needs its own explicit ">0" guard, or every dry hour
        # would carry a cluttering "☔ 0%" badge.
        chance_html = (
            f'<div class="hourly-chance">☔ {hour["precip_chance"]}%</div>' if hour["precip_chance"] else ""
        )
        wind_html = (
            f'<div class="hourly-wind">{hour["wind_dir"]} {hour["wind_speed"]}</div>'
            if hour.get("wind_speed") is not None else ""
        )
        # First card is always the soonest real reading available — the
        # closest thing to "right now" this hourly grid has, so it
        # gets the same left-accent-bar "this is the one that matters"
        # treatment other live boards in this app already use, and its
        # own label reads "NOW" instead of repeating a clock time
        # that's already shown at the top of the screen.
        is_now = i == 0
        tile_class = "tile hourly-tile hourly-tile-now" if is_now else "tile hourly-tile"
        label = "NOW" if is_now else _hour_label(hour["at"])
        with cols[i]:
            st.markdown(
                f"""<div class="{tile_class}">
                    <div class="tile-label compact">{label}</div>
                    <div class="hourly-icon">{icon_svg}</div>
                    <div class="hourly-temp">{hour['temp_c']:.0f}°</div>
                    <div class="hourly-condition">{hour['condition']}</div>
                    {chance_html}{wind_html}</div>""",
                unsafe_allow_html=True,
            )
