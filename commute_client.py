"""Drive time between COMMUTE_ORIGIN and a destination, traffic-aware
via TomTom's Routing API (free tier: 2,500 requests/day, no credit
card) — this app checks at most once per CACHE_TTL_SECONDS, so even
the kiosk running unattended 24/7 stays a tiny fraction of that.
Destination defaults to COMMUTE_DESTINATION but callers (see
commute_reminder.todays_destination) can route somewhere else entirely
— today's shift's own calendar location, if it has one.

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
GEOCODE_URL = "https://api.tomtom.com/search/2/geocode/{query}.json"
# 5 min still only burns ~288 calls/day (11.5% of the free-tier quota)
# even running unattended 24/7 — 15 min was needlessly conservative and
# let the shown time lag real conditions by up to a quarter hour.
CACHE_TTL_SECONDS = 5 * 60
# Addresses don't move — cache geocoding results for a long time rather
# than re-spending a request on the same event location every time it
# comes up. Long enough to cover a recurring shift's whole run without
# needing a re-lookup, short enough that a typo'd address fixed in the
# calendar doesn't stay wrong for a similarly long time.
GEOCODE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

_last_good_route: dict | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_route_raw(api_key: str, dest_lat: float, dest_lon: float, record_history: bool) -> dict:
    url = ROUTE_URL.format(
        lat1=COMMUTE_ORIGIN["lat"], lon1=COMMUTE_ORIGIN["lon"],
        lat2=dest_lat, lon2=dest_lon,
    )
    resp = requests.get(url, params={"key": api_key, "traffic": "true"}, timeout=10)
    resp.raise_for_status()
    summary = resp.json()["routes"][0]["summary"]
    # Inside the cached function, not in route() below — st.cache_data
    # only re-executes this body on an actual cache miss, so this
    # naturally records one point per real TomTom call (~every 15 min),
    # not once per rerun. Only for the default destination: mixing in
    # durations to whatever one-off location a shift happened to have
    # would make the "X min in the last 30 min" trend compare two
    # different routes against each other.
    if record_history:
        commute_history.record(summary["travelTimeInSeconds"])
    return {
        "duration_seconds": summary["travelTimeInSeconds"],
        "delay_seconds": summary["trafficDelayInSeconds"],
        "distance_km": summary["lengthInMeters"] / 1000,
    }


def route(destination: dict | None = None) -> dict | None:
    """`destination` is {"lat", "lon"} (a "label" key, if present, is
    ignored here) — None routes to the default COMMUTE_DESTINATION.
    The last-good fallback only applies to that default: a stale route
    to some other day's one-off event location would be actively
    misleading rather than merely outdated."""
    global _last_good_route
    api_key = st.secrets.get("TOMTOM_API_KEY")
    if not api_key:
        return None
    is_default = destination is None
    dest = destination or COMMUTE_DESTINATION
    try:
        result = _fetch_route_raw(api_key, dest["lat"], dest["lon"], is_default)
    except Exception:
        return _last_good_route if is_default else None
    if is_default:
        _last_good_route = result
    return result


@st.cache_data(ttl=GEOCODE_CACHE_TTL_SECONDS, show_spinner=False)
def _geocode_raw(address: str, api_key: str) -> dict | None:
    url = GEOCODE_URL.format(query=requests.utils.quote(address))
    resp = requests.get(url, params={"key": api_key, "limit": 1}, timeout=10)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    pos = results[0]["position"]
    return {"lat": pos["lat"], "lon": pos["lon"]}


def geocode(address: str) -> dict | None:
    """{"lat", "lon"} for a free-text address/place name, or None if
    it's blank, geocoding is unavailable, or nothing matched."""
    api_key = st.secrets.get("TOMTOM_API_KEY")
    if not api_key or not address.strip():
        return None
    try:
        return _geocode_raw(address, api_key)
    except Exception:
        return None
