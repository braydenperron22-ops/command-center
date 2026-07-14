"""Live weather radar imagery — the same raw signal (real-time
precipitation reflectivity, not a forecast model) that minute-by-minute
nowcasting apps like Apple Weather/Dark Sky are actually built on top
of. Their edge is a proprietary storm-tracking algorithm layered over
that signal, which isn't something to reasonably reimplement here — but
seeing the live radar directly is most of the real value on its own,
and it's public data.

Environment Canada's own 1km North American radar composite (rain and
snow separately, updated every 6 minutes) is served as a standard OGC
WMS map layer via MSC GeoMet. `radar_image_url` just builds the image
URL for the Weather page's <img> tag — the browser fetches that one
directly, not our own backend, so it needs no throttle/cache of its
own. `nearby_precip_km` is different: it fetches the same image
server-side and samples its pixels directly, giving a second,
independent "is there real precipitation nearby right now" signal for
the hero row's rain badge — one that can catch a real nearby cell
EC's own area-wide forecast percentage doesn't (the exact gap that
made Apple's notification right when this dashboard's EC-forecast-only
badge stayed quiet).
"""

import io
import time
from math import asin, cos, radians, sin, sqrt

import requests
import streamlit as st
from PIL import Image

import fetch_throttle
from config import WEATHER_LAT, WEATHER_LON

WMS_URL = "https://geo.weather.gc.ca/geomet"
RAIN_LAYER = "RADAR_1KM_RRAI"
SNOW_LAYER = "RADAR_1KM_RSNO"
# Centered on the user's own location (not EC's station point, which
# is only where their point-forecast numbers come from) with a fixed
# margin either side — a symmetric bbox means that point always lands
# exactly at the image's center (50%/50%), so the location marker
# overlay never needs per-request pixel math.
BBOX_MARGIN_DEGREES = 1.5
IMAGE_SIZE = 640
REFRESH_SECONDS = 6 * 60  # matches the radar composite's own update cadence

# How far out counts as "nearby" for the hero-row badge — roughly what
# a cell moving at typical storm speeds (20-30 km/h, EC's own forecasts
# for today) could cover within the hour, not the full ~85km the image
# itself spans.
NEARBY_RADIUS_KM = 25
# WMS renders true-transparent background as alpha 0; real echo pixels
# (even the faintest trace-precipitation color) render meaningfully
# above that. A small margin above 0 filters out compression artifacts
# at tile edges without needing to hand-check every legend color.
ALPHA_THRESHOLD = 20
_SEARCH_PX = 90  # comfortably covers NEARBY_RADIUS_KM in both axes at this latitude; real distance is what actually filters below
_SAMPLE_STRIDE = 3

_last_good_bytes: dict[str, bytes] = {}


def _bbox() -> str:
    return (
        f"{WEATHER_LAT - BBOX_MARGIN_DEGREES},{WEATHER_LON - BBOX_MARGIN_DEGREES},"
        f"{WEATHER_LAT + BBOX_MARGIN_DEGREES},{WEATHER_LON + BBOX_MARGIN_DEGREES}"
    )


def radar_image_url(kind: str = "rain") -> str:
    layer = SNOW_LAYER if kind == "snow" else RAIN_LAYER
    # Rounded to REFRESH_SECONDS rather than a raw timestamp — busts the
    # browser's image cache exactly when a new radar frame is actually
    # available, not on every single page rerun (which would force a
    # full-size image refetch every 5s for no reason).
    cache_bust = int(time.time() // REFRESH_SECONDS)
    return (
        f"{WMS_URL}?service=WMS&version=1.3.0&request=GetMap&layers={layer}"
        f"&format=image/png&transparent=true&width={IMAGE_SIZE}&height={IMAGE_SIZE}"
        f"&crs=EPSG:4326&bbox={_bbox()}&_t={cache_bust}"
    )


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def _fetch_radar_bytes_raw(layer: str, cache_bust: int) -> bytes:
    fetch_throttle.wait_turn()
    resp = requests.get(
        WMS_URL,
        params={
            "service": "WMS", "version": "1.3.0", "request": "GetMap", "layers": layer,
            "format": "image/png", "transparent": "true",
            "width": IMAGE_SIZE, "height": IMAGE_SIZE, "crs": "EPSG:4326", "bbox": _bbox(),
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.content


def _fetch_radar_bytes(layer: str) -> bytes | None:
    cache_bust = int(time.time() // REFRESH_SECONDS)
    try:
        result = _fetch_radar_bytes_raw(layer, cache_bust)
    except Exception:
        return _last_good_bytes.get(layer)
    _last_good_bytes[layer] = result
    return result


def nearby_precip_km(kind: str = "rain") -> float | None:
    """Distance in km to the nearest real radar-detected precipitation
    echo, sampled directly from the same live image the Weather page's
    radar tile shows — independent of EC's forecast percentage, this is
    what's actually on the radar right now. None if nothing's detected
    within NEARBY_RADIUS_KM (or the radar fetch/parse fails; this is a
    bonus signal layered on top of the forecast-based badge, not a
    replacement, so it fails quiet rather than breaking the hero row)."""
    layer = SNOW_LAYER if kind == "snow" else RAIN_LAYER
    raw = _fetch_radar_bytes(layer)
    if not raw:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None

    cx, cy = IMAGE_SIZE // 2, IMAGE_SIZE // 2
    deg_per_px = (2 * BBOX_MARGIN_DEGREES) / IMAGE_SIZE
    closest_km = None
    for dy in range(-_SEARCH_PX, _SEARCH_PX + 1, _SAMPLE_STRIDE):
        py = cy + dy
        if py < 0 or py >= IMAGE_SIZE:
            continue
        for dx in range(-_SEARCH_PX, _SEARCH_PX + 1, _SAMPLE_STRIDE):
            px = cx + dx
            if px < 0 or px >= IMAGE_SIZE:
                continue
            if img.getpixel((px, py))[3] <= ALPHA_THRESHOLD:
                continue
            # Image y increases downward while latitude increases
            # upward — dy has to flip sign, dx doesn't (both x and
            # longitude increase rightward/eastward).
            lat = WEATHER_LAT - dy * deg_per_px
            lon = WEATHER_LON + dx * deg_per_px
            dist = _distance_km(WEATHER_LAT, WEATHER_LON, lat, lon)
            if dist <= NEARBY_RADIUS_KM and (closest_km is None or dist < closest_km):
                closest_km = dist
    return closest_km
