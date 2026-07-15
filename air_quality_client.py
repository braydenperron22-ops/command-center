"""Open-Meteo Air Quality access — same provider as weather_client, no
new vendor or API key needed. Wildfire smoke is a real recurring
seasonal issue for this region, and there was previously zero
visibility into it on this dashboard (UV and precipitation both have a
badge; air quality had nothing).

Also tracks a rising/falling trend over time (see _record_and_trend) —
a static "AQI 57" doesn't say whether it's a smoke plume rolling in or
one already clearing out, which is the more useful half of the
question most days.
"""

import time

import requests
import streamlit as st

import fetch_throttle
from config import WEATHER_LAT, WEATHER_LON

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# AQI only really moves meaningfully over hours, not minutes (smoke
# plumes drift, don't teleport) — a wide window with a real minimum gap
# before trusting a direction, so two readings 15 minutes apart (the
# very next cache refresh) don't get overinterpreted as a trend.
HISTORY_WINDOW_MINUTES = 180
MIN_TREND_GAP_MINUTES = 30
STATIONARY_THRESHOLD = 8  # AQI points — smaller than this over the window reads as noise, not a real trend

_last_good_aqi: dict | None = None
_history: list[tuple[float, int]] = []


def _record_and_trend(now_ts: float, aqi: int) -> str | None:
    """"rising" / "falling" / "steady", or None if there isn't enough
    history yet to judge a trend from. Called only from inside the
    cached raw fetch below, so this naturally records one point per
    real API call (~every 15 min) rather than once per rerun."""
    _history.append((now_ts, aqi))
    cutoff = now_ts - HISTORY_WINDOW_MINUTES * 60
    _history[:] = [(t, v) for t, v in _history if t >= cutoff]

    if len(_history) < 2:
        return None
    old_t, old_v = _history[0]
    new_t, new_v = _history[-1]
    if (new_t - old_t) / 60 < MIN_TREND_GAP_MINUTES:
        return None
    change = new_v - old_v
    if abs(change) < STATIONARY_THRESHOLD:
        return "steady"
    return "rising" if change > 0 else "falling"


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _fetch_aqi_raw() -> dict | None:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "current": "us_aqi",
    }
    fetch_throttle.wait_turn()
    resp = requests.get(AIR_QUALITY_URL, params=params, timeout=10)
    resp.raise_for_status()
    aqi = resp.json().get("current", {}).get("us_aqi")
    if aqi is None:
        return None
    return {"us_aqi": aqi, "trend": _record_and_trend(time.time(), aqi)}


def fetch_air_quality() -> dict | None:
    global _last_good_aqi
    try:
        result = _fetch_aqi_raw()
    except (requests.RequestException, ValueError, KeyError):
        return _last_good_aqi
    if result is not None:
        _last_good_aqi = result
    return result if result is not None else _last_good_aqi
