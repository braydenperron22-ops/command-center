"""Drive time between COMMUTE_ORIGIN and COMMUTE_DESTINATION, traffic-
aware via TomTom's Routing API (free tier: 2,500 requests/day, no
credit card) — this app checks at most once per CACHE_TTL_SECONDS, so
even the kiosk running unattended 24/7 stays a tiny fraction of that.

Replaces an earlier OSRM-based version: OSRM's public server routes
the static road network only (speed limits/road class), no live
conditions, so it could never actually answer "how bad is traffic
right now" — the entire point of this tile.
"""

import requests
import streamlit as st

import commute_history
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN

ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute/{lat1},{lon1}:{lat2},{lon2}/json"
CACHE_TTL_SECONDS = 15 * 60

_last_good_route: dict | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_route_raw(api_key: str) -> dict:
    url = ROUTE_URL.format(
        lat1=COMMUTE_ORIGIN["lat"], lon1=COMMUTE_ORIGIN["lon"],
        lat2=COMMUTE_DESTINATION["lat"], lon2=COMMUTE_DESTINATION["lon"],
    )
    resp = requests.get(url, params={"key": api_key, "traffic": "true"}, timeout=10)
    resp.raise_for_status()
    summary = resp.json()["routes"][0]["summary"]
    # Inside the cached function, not in route() below — st.cache_data
    # only re-executes this body on an actual cache miss, so this
    # naturally records one point per real TomTom call (~every 15 min),
    # not once per rerun.
    commute_history.record(summary["travelTimeInSeconds"])
    return {
        "duration_seconds": summary["travelTimeInSeconds"],
        "delay_seconds": summary["trafficDelayInSeconds"],
        "distance_km": summary["lengthInMeters"] / 1000,
    }


def route() -> dict | None:
    global _last_good_route
    api_key = st.secrets.get("TOMTOM_API_KEY")
    if not api_key:
        return None
    try:
        result = _fetch_route_raw(api_key)
    except Exception:
        return _last_good_route
    _last_good_route = result
    return result
