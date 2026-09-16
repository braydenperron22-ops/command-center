"""Shared raw fetch for 511 Ontario's /event (v2) endpoint — one real
Upstash-free, no-auth GET, cached once, used by two independent
consumers that each apply their own filtering:

- road_conditions_511.py: IsFullClosure == True regardless of
  EventType, matched against the commute route's decoded polyline.
- local_news_client.py: EventType in {roadwork, accidentsAndIncidents},
  matched against COMMUTE_ORIGIN/COMMUTE_DESTINATION by straight-line
  distance.

Performance/resilience audit: these two used to each keep a private,
separately-cached copy of the identical unparameterized request (same
URL, no query params — the response is identical either way), so a
cold cache paid for the same ~province-wide event list twice every 15
minutes. road_conditions_511.py's own docstring already flagged this
as a known consequence of local_news_client's own fetcher being a
private helper nested inside a different function's cache boundary,
"not meant to be called from outside it" — this module is the proper
shared home instead of either module reaching into the other's
internals.
"""

import requests
import streamlit as st

import fetch_throttle

EVENTS_URL = "https://511on.ca/api/v2/get/event"
CACHE_TTL_SECONDS = 15 * 60


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_raw() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(EVENTS_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()
