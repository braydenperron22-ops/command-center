"""Open-Meteo access for the North Bay, ON current conditions + solar times."""

from datetime import datetime

import requests
import streamlit as st

from config import TIMEZONE, WEATHER_LAT, WEATHER_LON

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fetch_weather() -> dict | None:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "current": "temperature_2m,weather_code",
        "daily": "sunrise,sunset",
        "temperature_unit": "celsius",
        "timezone": TIMEZONE,
    }
    resp = requests.get(WEATHER_URL, params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    current = body.get("current", {})
    daily = body.get("daily", {})
    if "temperature_2m" not in current or not daily.get("sunrise"):
        return None

    # Open-Meteo returns these already in the requested local timezone
    # (naive, no offset), which matches the naive Toronto-pinned clock
    # used elsewhere in the app.
    sunrise = datetime.fromisoformat(daily["sunrise"][0])
    sunset = datetime.fromisoformat(daily["sunset"][0])

    return {
        "temp_c": current["temperature_2m"],
        "weather_code": current.get("weather_code", 0),
        "sunrise": sunrise,
        "sunset": sunset,
    }
