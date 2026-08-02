"""Hourly Forecast page: Environment Canada's own hour-by-hour outlook
(see ec_forecast.hourly_forecast) — replaces the live radar map. Session
request: "get rid of radar and replace it with hourly weather data."

Same authoritative EC source the 7-Day Forecast and rain-nowcast badge
already use, just the hourly slice of that one payload instead of the
daily one. Shows the next HOURS_SHOWN hours as columns, the same "one
tile per period" shape pages_weather.py's 7-day row already uses — a
fixed count rather than a scrolling timeline, since this kiosk has no
way to scroll to reveal anything below/beyond the fold (see this
session's own "no-scroll content" precedent).
"""

import streamlit as st

import ec_forecast
from icons import icon_for

HOURS_SHOWN = 12


def _hour_label(at) -> str:
    # "%-I %p" (e.g. "3 PM") rather than 24h time — matches every other
    # time-of-day label already shown elsewhere in this app.
    return at.strftime("%-I %p")


def render() -> None:
    st.markdown('<div class="page-title page-title-hourly">Hourly Forecast — Environment Canada</div>', unsafe_allow_html=True)

    hours = ec_forecast.hourly_forecast()[:HOURS_SHOWN]
    if not hours:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Forecast unavailable right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    cols = st.columns(len(hours))
    for i, hour in enumerate(hours):
        icon_svg = icon_for(hour["category"], "day")
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
        with cols[i]:
            st.markdown(
                f"""<div class="tile hourly-tile">
                    <div class="tile-label compact">{_hour_label(hour['at'])}</div>
                    <div class="hourly-icon">{icon_svg}</div>
                    <div class="hourly-temp">{hour['temp_c']:.0f}°</div>
                    {chance_html}{wind_html}</div>""",
                unsafe_allow_html=True,
            )
