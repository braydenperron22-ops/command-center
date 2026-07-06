"""Open-Meteo access for the North Bay, ON current conditions + solar times."""

from datetime import datetime

import requests
import streamlit as st

from config import RAIN_LOOKAHEAD_HOURS, RAIN_PROBABILITY_THRESHOLD, TIMEZONE, WEATHER_LAT, WEATHER_LON

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def _next_rain_hours(now: datetime, hourly: dict) -> float | None:
    """Hours from now until the next hour with a real chance of rain, within
    the lookahead window. None if nothing's expected."""
    times = hourly.get("time", [])
    probs = hourly.get("precipitation_probability", [])
    for t_str, prob in zip(times, probs):
        t = datetime.fromisoformat(t_str)
        hours_away = (t - now).total_seconds() / 3600
        if hours_away < 0 or hours_away > RAIN_LOOKAHEAD_HOURS:
            continue
        if prob is not None and prob >= RAIN_PROBABILITY_THRESHOLD:
            return hours_away
    return None


@st.cache_data(ttl=15 * 60, show_spinner=False)
def fetch_weather() -> dict | None:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "current": "temperature_2m,weather_code,uv_index",
        "hourly": "precipitation_probability",
        "daily": "sunrise,sunset",
        "temperature_unit": "celsius",
        "timezone": TIMEZONE,
        "forecast_days": 2,
    }
    resp = requests.get(WEATHER_URL, params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    current = body.get("current", {})
    daily = body.get("daily", {})
    hourly = body.get("hourly", {})
    if "temperature_2m" not in current or not daily.get("sunrise"):
        return None

    # Open-Meteo returns these already in the requested local timezone
    # (naive, no offset), which matches the naive Toronto-pinned clock
    # used elsewhere in the app.
    sunrise = datetime.fromisoformat(daily["sunrise"][0])
    sunset = datetime.fromisoformat(daily["sunset"][0])
    rain_in_hours = _next_rain_hours(datetime.fromisoformat(current["time"]), hourly)

    return {
        "temp_c": current["temperature_2m"],
        "weather_code": current.get("weather_code", 0),
        "uv_index": current.get("uv_index"),
        "sunrise": sunrise,
        "sunset": sunset,
        "rain_in_hours": rain_in_hours,
    }
