"""Nearby wildfire hotspots — Natural Resources Canada's CWFIS satellite
detections (VIIRS/MODIS), the actual cause behind days the AQI badge
already flags for wildfire smoke, not just the downstream symptom. Free,
public, no key, updated continuously through the day as satellites pass
over.

Gated hard to WILDFIRE_SEASON_MONTHS before any network call happens at
all — outside the real Canadian wildfire season, a stray winter
detection would be an industrial heat source or flare, not a wildfire,
so this returns None unconditionally in those months regardless of
what the feed says, on purpose.
"""

import csv
import io
from datetime import date, timedelta
from math import asin, cos, radians, sin, sqrt

import requests
import streamlit as st

import fetch_throttle
from config import WEATHER_LAT, WEATHER_LON

HOTSPOTS_URL = "https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/{day}.csv"
# April-November — Canada's actual wildfire season; snow cover makes
# Dec-Mar detections a non-issue in practice, but this is an explicit
# gate regardless of what the feed happens to contain those months.
WILDFIRE_SEASON_MONTHS = {4, 5, 6, 7, 8, 9, 10, 11}
SHOW_RADIUS_KM = 300  # close enough that smoke from it is a real, not theoretical, concern
CACHE_TTL_SECONDS = 60 * 60  # satellite passes trickle in through the day; hourly is plenty for a proximity badge

_last_good_hotspots: list[dict] | None = None


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_hotspots_raw(day: str) -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(HOTSPOTS_URL.format(day=day), timeout=15)
    resp.raise_for_status()
    # Columns are comma-space-separated ("lat, lon, rep_date, ..."), so
    # DictReader's default comma delimiter leaves a leading space on
    # every field name but the first — stripped here rather than
    # referencing " lon" etc. everywhere below.
    reader = csv.DictReader(io.StringIO(resp.text))
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    hotspots = []
    for row in reader:
        try:
            hotspots.append({"lat": float(row["lat"]), "lon": float(row["lon"])})
        except (KeyError, ValueError):
            continue
    return hotspots


def _fetch_hotspots(today: date) -> list[dict]:
    """Today's file, falling back to yesterday's if today's hasn't been
    published yet (satellite passes/processing can lag a few hours) —
    same last-good-copy resilience every other client in this app uses,
    just with a same-day fallback layered in front of it."""
    global _last_good_hotspots
    for day in (today, today - timedelta(days=1)):
        try:
            result = _fetch_hotspots_raw(day.strftime("%Y%m%d"))
        except Exception:
            continue
        _last_good_hotspots = result
        return result
    return _last_good_hotspots or []


def nearest_wildfire(today: date | None = None) -> dict | None:
    """{"distance_km", "count_nearby"} for the closest satellite-detected
    hotspot within SHOW_RADIUS_KM, or None if it's outside wildfire
    season, nothing's within range, or the feed's unreachable — this is
    a bonus proximity signal, not a safety-critical one, so it fails
    quiet rather than raising."""
    today = today or date.today()
    if today.month not in WILDFIRE_SEASON_MONTHS:
        return None
    hotspots = _fetch_hotspots(today)
    if not hotspots:
        return None
    distances = [_distance_km(WEATHER_LAT, WEATHER_LON, h["lat"], h["lon"]) for h in hotspots]
    nearby = [d for d in distances if d <= SHOW_RADIUS_KM]
    if not nearby:
        return None
    return {"distance_km": min(nearby), "count_nearby": len(nearby)}
