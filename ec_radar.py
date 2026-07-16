"""Live weather radar imagery and a simple approach/recede tracker built
on top of it — the same raw signal (real-time precipitation
reflectivity, not a forecast model) that minute-by-minute nowcasting
apps like Apple Weather/Dark Sky are actually built on top of. Their
edge is a proprietary storm-tracking algorithm layered over that
signal; this isn't that, but it's a reasonable approximation of the
same idea: sample the nearest detected echo's distance every time the
radar refreshes (~6 min), and if that distance has been shrinking, it's
approaching — extrapolate the closing speed into an ETA, and probe
further out along the same bearing for where the echo ends to estimate
when it'll clear, too.

`radar_image_url` builds the image URL for the Radar page's <img> tag —
the browser fetches that one directly, not our own backend, so it
needs no throttle/cache of its own. Everything else here does fetch
server-side (to read pixels), so it goes through fetch_throttle and is
cached to the radar's own real update cadence.
"""

import io
import time
from datetime import datetime
from math import asin, atan2, cos, degrees, radians, sin, sqrt

import requests
import streamlit as st
from PIL import Image

import fetch_throttle
from config import WEATHER_LAT, WEATHER_LON

WMS_URL = "https://geo.weather.gc.ca/geomet"
RAIN_LAYER = "RADAR_1KM_RRAI"
SNOW_LAYER = "RADAR_1KM_RSNO"
# Centered on the user's own location in Corbeil (not EC's North Bay
# Airport station, which is only where their point-forecast numbers
# come from) with a fixed margin either side — a symmetric bbox means
# that point always lands exactly at the image's center (50%/50%), so
# the location marker overlay never needs per-request pixel math.
BBOX_MARGIN_DEGREES = 1.5
IMAGE_SIZE = 640
REFRESH_SECONDS = 6 * 60  # matches the radar composite's own update cadence

# How far out counts as "nearby" for the hero-row badge — roughly what
# a cell moving at typical storm speeds (20-30 km/h, EC's own forecasts
# for today) could cover within the hour, not the full ~85km the image
# itself spans.
NEARBY_RADIUS_KM = 25
# How far past the near edge to probe for where the echo ends, to
# estimate a clearing time — well within the image's own ~110km
# longitudinal half-span at this latitude, so a real far edge is
# almost always still inside the frame if one exists.
FAR_EDGE_MAX_KM = 100
FAR_EDGE_STEP_KM = 2
# WMS renders true-transparent background as alpha 0; real echo pixels
# (even the faintest trace-precipitation color) render meaningfully
# above that. A small margin above 0 filters out compression artifacts
# at tile edges without needing to hand-check every legend color.
ALPHA_THRESHOLD = 20
_SEARCH_PX = 90  # comfortably covers NEARBY_RADIUS_KM in both axes at this latitude; real distance is what actually filters below
_SAMPLE_STRIDE = 3

# How much history to keep for the approach/recede trend, and how far
# apart two samples need to be before trusting a speed estimate from
# them — the radar itself only refreshes every REFRESH_SECONDS, so two
# samples closer together than that are the same frame twice, not a
# real trend point.
HISTORY_WINDOW_MINUTES = 30
MIN_TREND_GAP_MINUTES = 5
# A distance change smaller than this over the tracked window is
# treated as noise (radar echo edges flicker slightly frame to frame
# even for a genuinely stationary cell), not real approach/recede.
STATIONARY_THRESHOLD_KM = 1.5

_last_good_bytes: dict[str, bytes] = {}
_history: dict[str, list[tuple[datetime, float]]] = {"rain": [], "snow": []}


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


_COMPASS_ABBR = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
_COMPASS_WORDS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


def _compass_index(bearing_deg_: float) -> int:
    return round(bearing_deg_ / 45) % 8


def compass_abbr(bearing_deg_: float) -> str:
    return _COMPASS_ABBR[_compass_index(bearing_deg_)]


def compass_word(bearing_deg_: float) -> str:
    return _COMPASS_WORDS[_compass_index(bearing_deg_)]


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2, dl = radians(lat1), radians(lat2), radians(lon2 - lon1)
    x = sin(dl) * cos(p2)
    y = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    return (degrees(atan2(x, y)) + 360) % 360


def _destination(lat: float, lon: float, bearing_deg_: float, distance_km: float) -> tuple[float, float]:
    earth_radius_km = 6371
    delta = distance_km / earth_radius_km
    theta = radians(bearing_deg_)
    p1, l1 = radians(lat), radians(lon)
    p2 = asin(sin(p1) * cos(delta) + cos(p1) * sin(delta) * cos(theta))
    l2 = l1 + atan2(sin(theta) * sin(delta) * cos(p1), cos(delta) - sin(p1) * sin(p2))
    return degrees(p2), degrees(l2)


def _latlon_to_pixel(lat: float, lon: float) -> tuple[int, int]:
    deg_per_px = (2 * BBOX_MARGIN_DEGREES) / IMAGE_SIZE
    dx = round((lon - WEATHER_LON) / deg_per_px)
    dy = round((WEATHER_LAT - lat) / deg_per_px)  # image y increases downward, latitude increases upward
    return IMAGE_SIZE // 2 + dx, IMAGE_SIZE // 2 + dy


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


def _pixel_has_echo(img: Image.Image, px: int, py: int) -> bool | None:
    """True/False, or None if (px, py) falls outside the image entirely
    — distinct from False (checked and empty), since "we can't see that
    far" and "we looked and there's nothing there" need different
    handling by the far-edge search below."""
    if px < 0 or px >= IMAGE_SIZE or py < 0 or py >= IMAGE_SIZE:
        return None
    return img.getpixel((px, py))[3] > ALPHA_THRESHOLD


def _nearest_echo(img: Image.Image) -> tuple[float, float, float] | None:
    """(lat, lon, distance_km) of the closest detected echo pixel to
    WEATHER_LAT/WEATHER_LON, within NEARBY_RADIUS_KM — or None."""
    cx, cy = IMAGE_SIZE // 2, IMAGE_SIZE // 2
    deg_per_px = (2 * BBOX_MARGIN_DEGREES) / IMAGE_SIZE
    best = None
    for dy in range(-_SEARCH_PX, _SEARCH_PX + 1, _SAMPLE_STRIDE):
        py = cy + dy
        if py < 0 or py >= IMAGE_SIZE:
            continue
        for dx in range(-_SEARCH_PX, _SEARCH_PX + 1, _SAMPLE_STRIDE):
            px = cx + dx
            if px < 0 or px >= IMAGE_SIZE or img.getpixel((px, py))[3] <= ALPHA_THRESHOLD:
                continue
            lat = WEATHER_LAT - dy * deg_per_px
            lon = WEATHER_LON + dx * deg_per_px
            dist = _distance_km(WEATHER_LAT, WEATHER_LON, lat, lon)
            if dist <= NEARBY_RADIUS_KM and (best is None or dist < best[2]):
                best = (lat, lon, dist)
    return best


def _far_edge_km(img: Image.Image, bearing_deg_: float, start_km: float) -> float | None:
    """Walking outward from WEATHER_LAT/WEATHER_LON along bearing_deg_,
    starting just past the near edge (start_km), the distance at which
    the echo stops — an approximation of the storm's depth along its
    line of approach, used to estimate when it'll clear rather than
    just when it'll arrive. None if the echo still hasn't ended by
    FAR_EDGE_MAX_KM, or by the time the search runs off the edge of the
    image — either way, "we don't actually know" is more honest than
    guessing a number."""
    d = start_km + FAR_EDGE_STEP_KM
    while d <= FAR_EDGE_MAX_KM:
        lat, lon = _destination(WEATHER_LAT, WEATHER_LON, bearing_deg_, d)
        px, py = _latlon_to_pixel(lat, lon)
        has_echo = _pixel_has_echo(img, px, py)
        if has_echo is None:  # ran off the edge of the image before finding the end
            return None
        if not has_echo:
            return d
        d += FAR_EDGE_STEP_KM
    return None


def _record_and_trend(kind: str, now: datetime, nearest_km: float | None) -> dict:
    """Appends the latest reading to this kind's history (only while
    something's actually detected — a gap just ages out naturally
    rather than needing an explicit reset) and returns the trend
    computed from the oldest and newest samples still in the window."""
    history = _history[kind]
    if nearest_km is not None:
        history.append((now, nearest_km))
    cutoff = now.timestamp() - HISTORY_WINDOW_MINUTES * 60
    history[:] = [(t, km) for t, km in history if t.timestamp() >= cutoff]

    if len(history) < 2:
        return {"speed_kmh": None, "trend": "detecting"}

    old_t, old_km = history[0]
    new_t, new_km = history[-1]
    gap_minutes = (new_t - old_t).total_seconds() / 60
    if gap_minutes < MIN_TREND_GAP_MINUTES:
        return {"speed_kmh": None, "trend": "detecting"}

    change_km = old_km - new_km  # positive = got closer
    if abs(change_km) < STATIONARY_THRESHOLD_KM:
        return {"speed_kmh": None, "trend": "stationary"}
    speed_kmh = abs(change_km) / (gap_minutes / 60)
    return {"speed_kmh": speed_kmh, "trend": "approaching" if change_km > 0 else "receding"}


# Within this distance, the nearest echo counts as "here" rather than
# "approaching" — the badge switches from a countdown-to-arrival to a
# countdown-to-clearing at this point (see precip_status below).
ARRIVED_RADIUS_KM = 5


def precip_status(kind: str = "rain") -> dict | None:
    """The one signal behind the hero badge and the Radar page's own
    badge — collapsed to two states on purpose (see session request:
    "rain in ___" while it's inbound, "clears in ___" once it's here),
    rather than the previous separate distance/eta/end-time fields a
    caller had to assemble into text itself.

    {"state": "approaching", "minutes": int} — nearest echo is outside
    ARRIVED_RADIUS_KM and genuinely closing in; minutes is the ETA.

    {"state": "arrived", "minutes": int|None} — nearest echo is within
    ARRIVED_RADIUS_KM (it's here); minutes is when it's expected to
    clear, from the same tracked speed used for the ETA above, probing
    outward for the echo's far edge — None if that can't be pinned down
    yet (echo runs off the image edge, or a speed estimate isn't
    available yet).

    Both states also carry "direction"/"direction_word" (e.g. "NW" /
    "northwest") — the bearing from Corbeil to the nearest echo, so
    where the storm currently *is*, not which way it's moving (that
    would need tracking its position over time, not just its distance,
    which is all HISTORY_WINDOW_MINUTES of samples give us). Least
    meaningful right at "arrived", where the echo's close enough that
    pixel-level jitter can swing the bearing around a bit.

    None — nothing detected within NEARBY_RADIUS_KM, or something's
    nearby but not moving in (sitting still, or drifting away): "only
    say something when it's happening or about to" is the point of this
    over a flat nearby-or-not signal.
    """
    layer = SNOW_LAYER if kind == "snow" else RAIN_LAYER
    raw = _fetch_radar_bytes(layer)
    now = datetime.now()
    if not raw:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None

    nearest = _nearest_echo(img)
    trend = _record_and_trend(kind, now, nearest[2] if nearest else None)
    if nearest is None:
        return None
    lat, lon, distance_km = nearest
    bearing_deg_ = _bearing_deg(WEATHER_LAT, WEATHER_LON, lat, lon)
    direction = {"direction": compass_abbr(bearing_deg_), "direction_word": compass_word(bearing_deg_)}

    if distance_km <= ARRIVED_RADIUS_KM:
        minutes = None
        if trend["speed_kmh"]:
            far_km = _far_edge_km(img, bearing_deg_, distance_km)
            if far_km is not None:
                minutes = round((far_km / trend["speed_kmh"]) * 60)
        return {"state": "arrived", "minutes": minutes, **direction}

    if trend["trend"] != "approaching":
        return None
    eta_minutes = (distance_km / trend["speed_kmh"]) * 60
    return {"state": "approaching", "minutes": round(eta_minutes), **direction}


def tracking_overlay(kind: str = "rain") -> dict | None:
    """Where the nearest detected echo actually sits on the frame — as a
    0-100 position (matching how the fixed location marker is already
    positioned with top/left percentages), so the Radar page can draw a
    real line from the threat to the user's own marker instead of
    leaving the tracking data as a separate text-only badge underneath
    the map. None if nothing's within NEARBY_RADIUS_KM right now."""
    layer = SNOW_LAYER if kind == "snow" else RAIN_LAYER
    raw = _fetch_radar_bytes(layer)
    if not raw:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None
    nearest = _nearest_echo(img)
    if nearest is None:
        return None
    lat, lon, distance_km = nearest
    px, py = _latlon_to_pixel(lat, lon)
    status = precip_status(kind)
    return {
        "x_pct": max(0.0, min(100.0, px / IMAGE_SIZE * 100)),
        "y_pct": max(0.0, min(100.0, py / IMAGE_SIZE * 100)),
        "distance_km": distance_km,
        "active": status is not None,
        "minutes": status["minutes"] if status else None,
        "direction": status["direction"] if status else compass_abbr(_bearing_deg(WEATHER_LAT, WEATHER_LON, lat, lon)),
    }
