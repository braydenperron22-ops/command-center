"""Hourly Forecast page: Environment Canada's own hour-by-hour outlook
(see ec_forecast.hourly_forecast) — replaces the live radar map. Session
request: "get rid of radar and replace it with hourly weather data,"
then "make it look better and a little more complete."

Same authoritative EC source the 7-Day Forecast and rain-nowcast badge
already use, just the hourly slice of that one payload instead of the
daily one. Shows the next HOURS_SHOWN hours as columns, the same "one
tile per period" shape pages_weather.py's 7-day row already uses — a
fixed count rather than a scrolling timeline, since this kiosk has no
way to scroll to reveal anything below/beyond the fold (see this
session's own "no-scroll content" precedent).

"More complete" additions over the first version: a current-conditions
header (reusing the same real EC station reading and .weather-current-*
styling the Weather page's own tile already uses, so the page has a
real anchor instead of opening straight into a bare row of cards), each
hour's actual condition text (not just an icon), correct day/night icon
phase per hour (the first version always passed "day," which only
visibly mattered for the "clear" category's sun/moon icon but was still
wrong for real overnight hours), and a highlighted "NOW" card so the
current hour reads as the anchor point for the rest of the row.
"""

import streamlit as st

import ec_forecast
import weather_client
from icons import icon_for

HOURS_SHOWN = 12


def _hour_label(at) -> str:
    # "%-I %p" (e.g. "3 PM") rather than 24h time — matches every other
    # time-of-day label already shown elsewhere in this app.
    return at.strftime("%-I %p")


def _render_current(current: dict | None) -> None:
    """Same tile pages_weather._render_current renders — duplicated
    rather than imported (each page here owns its own markup; the CSS
    classes are already shared, generic names, not weather-page-
    specific) so this page opens with a real "right now" anchor instead
    of starting straight into the hour-by-hour row."""
    if not current:
        return
    icon_svg = icon_for(current["category"], "day")
    wind = ""
    if current.get("wind_speed") is not None:
        gust = f" gust {current['wind_gust']}" if current.get("wind_gust") else ""
        wind_dir = current.get("wind_dir") or ""
        wind = f"{wind_dir} {current['wind_speed']} km/h{gust}"
    wind_html = f"<span>Wind {wind}</span>" if wind else ""
    humidity_html = f"<span>Humidity {current['humidity']}%</span>" if current.get("humidity") is not None else ""

    st.markdown(
        f"""<div class="tile weather-current-tile">
            <div class="tile-label compact">CURRENT · {current['station'].upper()}</div>
            <div class="weather-current-row">
                <div class="weather-current-icon">{icon_svg}</div>
                <div class="weather-current-temp">{current['temp_c']:.0f}°C</div>
                <div class="weather-current-condition">{current['condition']}</div>
                <div class="weather-current-metrics">
                    {humidity_html}{wind_html}
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
    st.markdown('<div class="page-title page-title-hourly">Hourly Forecast — Environment Canada</div>', unsafe_allow_html=True)

    _render_current(ec_forecast.current_conditions())
    st.markdown('<div class="internals-section-gap"></div>', unsafe_allow_html=True)

    hours = ec_forecast.hourly_forecast()[:HOURS_SHOWN]
    if not hours:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Forecast unavailable right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    weather = weather_client.fetch_weather()
    sunrise = weather.get("sunrise") if weather else None
    sunset = weather.get("sunset") if weather else None

    cols = st.columns(len(hours))
    for i, hour in enumerate(hours):
        phase = _day_or_night(hour["at"], sunrise, sunset)
        icon_svg = icon_for(hour["category"], phase)
        # Only shown when there's a real chance — an EC hourly reading
        # always carries a structured lop value even at a genuine 0%,
        # unlike the daily forecast's text-parsed precip_chance (which
        # is only ever present at all when EC's own summary actually
        # mentions a real chance) — so this needs its own explicit ">0"
        # guard rather than the daily page's "is not None" one, or every
        # dry hour would carry a cluttering "☔ 0%" badge.
        chance_html = (
            f'<div class="hourly-chance">☔ {hour["precip_chance"]}%</div>' if hour["precip_chance"] else ""
        )
        wind_html = (
            f'<div class="hourly-wind">{hour["wind_dir"]} {hour["wind_speed"]}</div>'
            if hour.get("wind_speed") is not None else ""
        )
        # First card is always the soonest real reading EC has — the
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
