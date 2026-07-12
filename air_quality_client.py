"""Open-Meteo Air Quality access — same provider as weather_client, no
new vendor or API key needed. Wildfire smoke is a real recurring
seasonal issue for this region, and there was previously zero
visibility into it on this dashboard (UV and precipitation both have a
badge; air quality had nothing)."""

import requests
import streamlit as st

from config import WEATHER_LAT, WEATHER_LON

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

_last_good_aqi: dict | None = None


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _fetch_aqi_raw() -> dict | None:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "current": "us_aqi",
    }
    resp = requests.get(AIR_QUALITY_URL, params=params, timeout=10)
    resp.raise_for_status()
    aqi = resp.json().get("current", {}).get("us_aqi")
    if aqi is None:
        return None
    return {"us_aqi": aqi}


def fetch_air_quality() -> dict | None:
    global _last_good_aqi
    try:
        result = _fetch_aqi_raw()
    except (requests.RequestException, ValueError, KeyError):
        return _last_good_aqi
    if result is not None:
        _last_good_aqi = result
    return result if result is not None else _last_good_aqi
