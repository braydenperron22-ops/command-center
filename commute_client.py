"""Drive time/distance between COMMUTE_ORIGIN and COMMUTE_DESTINATION,
via OSRM's free public routing server — no key, same reasoning as every
other data source in this app.

Not traffic-aware: OSRM's public instance routes against the static
road network (speed limits/road class), not live conditions, so this is
a "how long does this drive normally take" baseline rather than a
real-time ETA. Cached for a long time (6h) since re-fetching more often
buys nothing — the underlying route doesn't change.
"""

import requests
import streamlit as st

from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
CACHE_TTL_SECONDS = 6 * 60 * 60

_last_good_route: dict | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_route_raw() -> dict:
    url = OSRM_URL.format(
        lon1=COMMUTE_ORIGIN["lon"], lat1=COMMUTE_ORIGIN["lat"],
        lon2=COMMUTE_DESTINATION["lon"], lat2=COMMUTE_DESTINATION["lat"],
    )
    resp = requests.get(url, params={"overview": "false"}, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != "Ok" or not body.get("routes"):
        raise ValueError(f"OSRM returned no route: {body.get('code')}")
    route = body["routes"][0]
    return {"duration_seconds": route["duration"], "distance_km": route["distance"] / 1000}


def route() -> dict | None:
    global _last_good_route
    try:
        result = _fetch_route_raw()
    except Exception:
        return _last_good_route
    _last_good_route = result
    return result
