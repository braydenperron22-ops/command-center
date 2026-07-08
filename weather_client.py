"""Open-Meteo access for the North Bay, ON current conditions + solar times."""

from datetime import datetime

import requests
import streamlit as st

from config import RAIN_LOOKAHEAD_HOURS, RAIN_PROBABILITY_THRESHOLD, TIMEZONE, WEATHER_LAT, WEATHER_LON

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# This is called unconditionally at the very top of app.py, before any
# page renders — an uncaught exception here used to take down the entire
# app (background, clock, every page), not just the weather widget. Falls
# back to the last successfully fetched reading rather than raising.
_last_good_weather: dict | None = None


def _next_rain_at(now: datetime, hourly: dict) -> datetime | None:
    """Absolute timestamp of the next hour with a real chance of rain,
    within the lookahead window — an absolute target rather than "hours
    from now", so the caller can tick a live countdown every second
    between the 15-minute weather refreshes instead of a relative value
    that would otherwise just sit frozen (or silently go stale) until
    the next fetch. None if nothing's expected."""
    times = hourly.get("time", [])
    probs = hourly.get("precipitation_probability", [])
    for t_str, prob in zip(times, probs):
        t = datetime.fromisoformat(t_str)
        hours_away = (t - now).total_seconds() / 3600
        if hours_away < 0 or hours_away > RAIN_LOOKAHEAD_HOURS:
            continue
        if prob is not None and prob >= RAIN_PROBABILITY_THRESHOLD:
            return t
    return None


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _fetch_weather_raw() -> dict | None:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "current": "temperature_2m,weather_code,uv_index",
        "hourly": "precipitation_probability",
        "daily": "sunrise,sunset,temperature_2m_max,temperature_2m_min",
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
    rain_at = _next_rain_at(datetime.fromisoformat(current["time"]), hourly)

    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []

    return {
        "temp_c": current["temperature_2m"],
        "weather_code": current.get("weather_code", 0),
        "uv_index": current.get("uv_index"),
        "sunrise": sunrise,
        "sunset": sunset,
        "rain_at": rain_at,
        "forecast_high_c": highs[0] if highs else None,
        "forecast_low_c": lows[0] if lows else None,
    }


def fetch_weather() -> dict | None:
    global _last_good_weather
    try:
        result = _fetch_weather_raw()
    except (requests.RequestException, ValueError, KeyError):
        return _last_good_weather
    if result is not None:
        _last_good_weather = result
    return result if result is not None else _last_good_weather
