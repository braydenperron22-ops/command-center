"""Environment Canada's own Air Quality Health Index (AQHI) — a 1-10+
health-risk scale, and a genuinely separate product from both
air_quality_client.py's Open-Meteo US AQI (a different provider, a
different scale, confirmed live capable of disagreeing with EC's own
reading) and ec_alerts.py's general weather-warnings feed (tornado,
thunderstorm, heat, etc. — confirmed live it does not carry AQHI at
all). Session request: "there's an air quality alert from Environment
Canada that you aren't picking up" — this was the actual gap: nothing
in this app queried EC's AQHI in any form before now.

Accessed via MSC GeoMet's OGC API (api.weather.gc.ca), same general
approach as ec_forecast.py's citypageweather collection — confirmed
live via the aqhi-stations collection that North Bay's own real AQHI
monitoring station ("FCFUU") sits a few km from WEATHER_LAT/
WEATHER_LON (same kind of offset ec_forecast.py's own station already
has), so this queries by that station's own documented location_id
rather than a bbox, which missed it entirely in a first attempt.
"""

import requests
import streamlit as st

import fetch_throttle

AQHI_STATION_ID = "FCFUU"  # North Bay — confirmed live via the aqhi-stations collection
AQHI_URL = "https://api.weather.gc.ca/collections/aqhi-observations-realtime/items"
CACHE_TTL_SECONDS = 15 * 60

# EC's own official AQHI health-risk categories (1-3 Low, 4-6 Moderate,
# 7-10 High, 10+ Very High) — https://www.canada.ca/en/environment-
# climate-change/services/air-quality-health-index.html
_HIGH_RISK_AQHI = 7.0
_VERY_HIGH_RISK_AQHI = 10.5

_last_good_aqhi: dict | None = None


def _risk_category(aqhi: float) -> str:
    if aqhi >= _VERY_HIGH_RISK_AQHI:
        return "Very High Risk"
    if aqhi >= _HIGH_RISK_AQHI:
        return "High Risk"
    if aqhi >= 4:
        return "Moderate Risk"
    return "Low Risk"


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_aqhi_raw() -> dict | None:
    fetch_throttle.wait_turn()
    resp = requests.get(
        AQHI_URL,
        params={"f": "json", "location_id": AQHI_STATION_ID, "latest": "true", "limit": 1},
        timeout=10,
    )
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return None
    props = features[0]["properties"]
    aqhi = props.get("aqhi")
    if aqhi is None:
        return None
    return {
        "aqhi": aqhi,
        "risk": _risk_category(aqhi),
        "observed_at": props.get("observation_datetime_text_en", ""),
    }


def fetch_aqhi() -> dict | None:
    """{"aqhi": float, "risk": "Low"/"Moderate"/"High"/"Very High" Risk,
    "observed_at": "7:00 AM EDT Saturday 18 July 2026"} for North Bay's
    own real AQHI station, or the last successfully fetched reading if
    this particular refresh failed (same _last_good_X fallback pattern
    every other client in this app already uses)."""
    global _last_good_aqhi
    try:
        result = _fetch_aqhi_raw()
    except Exception:
        return _last_good_aqhi
    if result is not None:
        _last_good_aqhi = result
    return result if result is not None else _last_good_aqhi


def aqhi_alert() -> dict | None:
    """{"title", "summary"} — the same shape ec_alerts.fetch_alerts()
    returns, so a genuinely elevated AQHI (High Risk or worse) can slot
    directly into weather_alerts_bar's existing selection/severity
    logic alongside real EC weather alerts, rather than needing a
    second, parallel display path. None below _HIGH_RISK_AQHI —
    Moderate/Low AQHI is routine, not alert-worthy.

    Title leads with "Air Quality Statement" (EC's own real product
    name for this) at High Risk, matching how weather_alerts_bar's own
    _tier() reads a title with no "warning"/"watch" wording as
    "statement" tier — genuinely accurate to what EC calls it, not just
    a convenient tier-word match. Bumped to "Air Quality Warning" at
    Very High Risk specifically, since that level is a real step up in
    urgency this app's own hazard-ranking already treats a plain
    "statement" as too muted for."""
    reading = fetch_aqhi()
    if reading is None or reading["aqhi"] < _HIGH_RISK_AQHI:
        return None
    tier_word = "Warning" if reading["aqhi"] >= _VERY_HIGH_RISK_AQHI else "Statement"
    return {
        "title": f"Air Quality {tier_word} — {reading['risk']} (AQHI {reading['aqhi']:.0f})",
        "summary": f"Environment Canada AQHI observation for North Bay, {reading['observed_at']}",
    }
