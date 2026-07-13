"""Open-Meteo access for the North Bay, ON current conditions + solar times."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from astral import LocationInfo
from astral.sun import sun

import ec_forecast
import fetch_throttle
from config import TIMEZONE, WEATHER_LAT, WEATHER_LON

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo has no civil-twilight variable (only the sunrise/sunset disk
# crossing), so first/last light are computed locally instead — astral's
# `sun()` gives dawn/dusk at the standard 6° civil-twilight depression by
# default, no API call needed. Cross-checked against a real forecast (July
# 2026, North Bay): computed dawn/dusk landed within a minute of the
# figures actually observed for that day.
_LOCATION = LocationInfo(latitude=WEATHER_LAT, longitude=WEATHER_LON, timezone=TIMEZONE)


def _first_last_light(day: date) -> tuple[datetime, datetime]:
    s = sun(_LOCATION.observer, date=day, tzinfo=ZoneInfo(TIMEZONE))
    return s["dawn"].replace(tzinfo=None), s["dusk"].replace(tzinfo=None)

# This is called unconditionally at the very top of app.py, before any
# page renders — an uncaught exception here used to take down the entire
# app (background, clock, every page), not just the weather widget. Falls
# back to the last successfully fetched reading rather than raising.
_last_good_weather: dict | None = None


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _fetch_weather_raw() -> dict | None:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "current": "temperature_2m,weather_code,uv_index",
        "daily": "sunrise,sunset,temperature_2m_max,temperature_2m_min",
        "temperature_unit": "celsius",
        "timezone": TIMEZONE,
        "forecast_days": 2,
    }
    fetch_throttle.wait_turn()
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
    first_light, last_light = _first_last_light(sunrise.date())
    # Environment Canada's own forecast, not Open-Meteo's — see
    # ec_forecast.py for why (EC's official numbers disagreed with
    # Open-Meteo's generic global blend for this exact location).
    precip = ec_forecast.next_precip_at(datetime.fromisoformat(current["time"]))

    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []

    return {
        "temp_c": current["temperature_2m"],
        "weather_code": current.get("weather_code", 0),
        "uv_index": current.get("uv_index"),
        "sunrise": sunrise,
        "sunset": sunset,
        "first_light": first_light,
        "last_light": last_light,
        "rain_at": precip[0] if precip else None,
        "precip_kind": precip[1] if precip else None,
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
