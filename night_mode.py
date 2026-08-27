"""Overnight nightstand display — session request: "because this is on
a regular display now and not a monitor... get rid of the smart plug...
replace [it] by a designated night mode where the display goes dark,
and it's used as like a nightstand display... clock, weather...
minimalist... make the colors friendly on the eyes... as little blue
light as possible."

Replaces govee_lighting.sync_plug (which used to cut power to the
monitor overnight on a fixed 9:30pm-4:30am schedule, with the same
live-game/leave-timer/storm overrides this module's own trigger reuses
— see app.py's own night-mode gating for exactly how). The physical
Govee LIGHT automation is untouched — this is a screen-content change
only ("the lights can stay").

Deliberately warm and dim rather than reusing this app's normal dark
theme as-is: the normal palette leans on blue-white text/accents
(#F5F5F7, #0A84FF) for daytime legibility, exactly the wavelengths
that suppress melatonin and make a 3am glance at the screen actually
wake you up. Every color here is a warm amber/ember tone instead, nothing
above a dim brightness, similar in spirit to a red-light flashlight or
f.lux's own night shift, but applied to fixed content rather than a
color-temperature filter over the normal busy dashboard."""

import html
from datetime import datetime

import streamlit as st

from icons import icon_for, label_for


def render(now: datetime, weather: dict | None, category: str, phase: str) -> None:
    time_str = now.strftime("%-I:%M").lstrip("0") or "12:00"
    ampm = now.strftime("%p")
    date_str = now.strftime("%A, %B %-d")

    weather_html = ""
    if weather and weather.get("temp_c") is not None:
        icon_svg = icon_for(category, phase)
        temp = round(weather["temp_c"])
        condition = html.escape(label_for(weather["weather_code"]))
        # Tonight's/today's real forecast low, already fetched alongside
        # the current reading (weather_client.fetch_weather) — a
        # genuinely useful nightstand detail ("how cold is it getting")
        # rather than a second network call for something new.
        low = weather.get("forecast_low_c")
        low_html = f'<span class="night-weather-low">Low {round(low)}°</span>' if low is not None else ""
        weather_html = (
            f'<div class="night-weather">'
            f'<span class="night-weather-icon">{icon_svg}</span>'
            f'<span class="night-weather-temp">{temp}°</span>'
            f'<span class="night-weather-cond">{condition}</span>'
            f"{low_html}"
            f"</div>"
        )

    st.markdown(
        f'<div class="night-mode">'
        f'<div class="night-clock">{time_str}<span class="night-ampm">{ampm}</span></div>'
        f'<div class="night-date">{date_str}</div>'
        f"{weather_html}"
        f"</div>",
        unsafe_allow_html=True,
    )
