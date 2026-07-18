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

import base64
import io
import time
from collections import deque
from datetime import datetime
from math import asin, atan2, cos, degrees, radians, sin, sqrt

import numpy as np
import requests
import streamlit as st
from PIL import Image

import fetch_throttle
from config import RADAR_NEARBY_CITIES, WEATHER_LAT, WEATHER_LON

WMS_URL = "https://geo.weather.gc.ca/geomet"
RAIN_LAYER = "RADAR_1KM_RRAI"
SNOW_LAYER = "RADAR_1KM_RSNO"
# Centered on the user's own location in Corbeil (not EC's North Bay
# Airport station, which is only where their point-forecast numbers
# come from) with a fixed margin either side — a symmetric bbox means
# that point always lands exactly at the image's center (50%/50%), so
# the location marker overlay never needs per-request pixel math.
#
# Wide rather than square — matches the Radar page's own wide tile
# instead of a square inset sitting in the middle of it with empty
# space on either side. Vertical extent (BBOX_MARGIN_DEGREES_LAT,
# IMAGE_HEIGHT) is exactly what it always was, so north/south detection
# range and resolution are unchanged; only the horizontal extent grew.
# BBOX_MARGIN_DEGREES_LON is scaled by the same IMAGE_ASPECT_RATIO as
# IMAGE_WIDTH, which keeps degrees-per-pixel identical along both axes
# (confirmed: (2*LON_MARGIN)/WIDTH reduces to the same ratio as
# (2*LAT_MARGIN)/HEIGHT) — a circular echo still reads as circular on
# screen, not stretched, and every distance/bearing calculation below
# can keep using one shared _DEG_PER_PX for both axes.
IMAGE_ASPECT_RATIO = 2.5  # width : height
IMAGE_HEIGHT = 640
IMAGE_WIDTH = round(IMAGE_HEIGHT * IMAGE_ASPECT_RATIO)
BBOX_MARGIN_DEGREES_LAT = 1.5
BBOX_MARGIN_DEGREES_LON = BBOX_MARGIN_DEGREES_LAT * IMAGE_ASPECT_RATIO
_DEG_PER_PX = (2 * BBOX_MARGIN_DEGREES_LAT) / IMAGE_HEIGHT
REFRESH_SECONDS = 6 * 60  # matches the radar composite's own update cadence

# How far out counts as "nearby" for the hero-row badge — widened from
# a original 25km (which only ever caught a cell already close enough
# to arrive within the hour) after confirming live that a genuinely
# large, coherent system can sit with its closest edge 130km+ out while
# still filling most of the visible frame — 25km meant tracking simply
# never started until the storm was nearly on top of the user. 150km
# comfortably covers that and leaves real margin to keep tracking it
# closing in, while staying safely inside the image's own ~166km
# vertical half-span (the tighter of its two axes) so the search below
# doesn't run off the edge of the fetched frame.
NEARBY_RADIUS_KM = 150
# How far past the near edge to probe for where the echo ends, to
# estimate a clearing time — well within the image's own ~166km
# half-span in every direction (the tighter of the two axes), so a real
# far edge is almost always still inside the frame if one exists.
FAR_EDGE_MAX_KM = 100
FAR_EDGE_STEP_KM = 2
# WMS renders true-transparent background as alpha 0; real echo pixels
# (even the faintest trace-precipitation color) render meaningfully
# above that. A small margin above 0 filters out compression artifacts
# at tile edges without needing to hand-check every legend color.
ALPHA_THRESHOLD = 20
# Must actually reach NEARBY_RADIUS_KM in pixel terms along the
# TIGHTER axis for km-per-pixel, which is horizontal/longitude here
# (~0.36 km/px at this latitude — longitude lines are closer together
# away from the equator), not vertical/latitude (~0.52 km/px, farther-
# reaching per pixel). Confirmed live this actually matters: a real
# echo sitting at dx=-330px was silently missed by a 300px box sized
# off the vertical ratio, 30px short of reaching it. 150km needs
# ~418px on the horizontal axis; 430 leaves a small margin. This can
# run past the image's own ~320px vertical half-height without issue —
# the existing in-bounds check below just skips those rows, which is
# correct: there's no data past the real edge of the fetched frame
# regardless of how far the search loop itself reaches.
_SEARCH_PX = 430
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
        f"{WEATHER_LAT - BBOX_MARGIN_DEGREES_LAT},{WEATHER_LON - BBOX_MARGIN_DEGREES_LON},"
        f"{WEATHER_LAT + BBOX_MARGIN_DEGREES_LAT},{WEATHER_LON + BBOX_MARGIN_DEGREES_LON}"
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
        f"&format=image/png&transparent=true&width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}"
        f"&crs=EPSG:4326&bbox={_bbox()}&_t={cache_bust}"
    )


# Matches .weather-radar-frame's own CSS background (theme.py) — GIF
# has no partial-alpha transparency (only a single fully-transparent
# color index), unlike the PNG this app fetches directly, so each
# frame is flattened against this exact color before encoding rather
# than trying to preserve any transparency in the loop itself. The
# static single-frame <img> already visually reads this same way (the
# browser composites its own transparent PNG against this same tile
# background), so the loop looks identical, just animated.
_RADAR_TILE_BG = (0x0A, 0x14, 0x20, 255)
RADAR_LOOP_FRAME_MS = 600  # per-frame duration; the last frame holds roughly 2x this so the "current" moment is easy to register before it loops


def radar_loop_data_uri(kind: str = "rain") -> str | None:
    """A short looping GIF built from the last FRAME_HISTORY_SIZE real
    radar frames (oldest first, see _fetch_radar_bytes), as a data:
    URI ready to drop straight into an <img src="...">. None until at
    least 2 real frames have been captured (right after a fresh
    deploy/restart there's only ever the current one yet) — the
    static single-frame image is the correct fallback for that window,
    not an error.

    All frames share the exact same bbox (same WMS request shape every
    time, just a different moment), so anything already positioned
    against the image by percentage — the city markers, the tracking
    line — stays correctly placed regardless of which frame the loop
    happens to be showing; nothing else needs to change to support
    this."""
    layer = SNOW_LAYER if kind == "snow" else RAIN_LAYER
    _fetch_radar_bytes(layer)  # ensures this rerun's frame is recorded before reading history
    frames_raw = [raw for _, raw in _frame_history[kind]]
    if len(frames_raw) < 2:
        return None

    try:
        composited = []
        for raw in frames_raw:
            frame = Image.open(io.BytesIO(raw)).convert("RGBA")
            bg = Image.new("RGBA", frame.size, _RADAR_TILE_BG)
            composited.append(Image.alpha_composite(bg, frame).convert("RGB"))
    except Exception:
        return None

    durations = [RADAR_LOOP_FRAME_MS] * (len(composited) - 1) + [RADAR_LOOP_FRAME_MS * 2]
    buf = io.BytesIO()
    composited[0].save(
        buf, format="GIF", save_all=True, append_images=composited[1:],
        duration=durations, loop=0, optimize=True,
    )
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/gif;base64,{encoded}"


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
    dx = round((lon - WEATHER_LON) / _DEG_PER_PX)
    dy = round((WEATHER_LAT - lat) / _DEG_PER_PX)  # image y increases downward, latitude increases upward
    return IMAGE_WIDTH // 2 + dx, IMAGE_HEIGHT // 2 + dy


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def _fetch_radar_bytes_raw(layer: str, cache_bust: int) -> bytes:
    fetch_throttle.wait_turn()
    resp = requests.get(
        WMS_URL,
        params={
            "service": "WMS", "version": "1.3.0", "request": "GetMap", "layers": layer,
            "format": "image/png", "transparent": "true",
            "width": IMAGE_WIDTH, "height": IMAGE_HEIGHT, "crs": "EPSG:4326", "bbox": _bbox(),
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.content


# Last few real radar frames, oldest first, so a short loop can show
# where the storm's actually been moving — not just a single static
# snapshot (session request: "cache the last three pulls... play them
# in order", later widened to 5: "use this to actually gauge storm
# direction instead of guessing"). Each real fetch is REFRESH_SECONDS
# (~6 min) apart, so 5 frames covers roughly the last 24-30 minutes of
# real motion — the same raw frames storm_motion() below measures
# actual bearing/speed from, not just what the loop animates. Keyed by
# kind ("rain"/"snow", inherently bounded) the same way _history
# already is.
FRAME_HISTORY_SIZE = 5
_frame_history: dict[str, list[tuple[int, bytes]]] = {"rain": [], "snow": []}


def _fetch_radar_bytes(layer: str) -> bytes | None:
    kind = "snow" if layer == SNOW_LAYER else "rain"
    cache_bust = int(time.time() // REFRESH_SECONDS)
    try:
        result = _fetch_radar_bytes_raw(layer, cache_bust)
    except Exception:
        return _last_good_bytes.get(layer)
    _last_good_bytes[layer] = result

    history = _frame_history[kind]
    if not history or history[-1][0] != cache_bust:
        history.append((cache_bust, result))
        del history[: -FRAME_HISTORY_SIZE]
    return result


def _pixel_has_echo(img: Image.Image, px: int, py: int) -> bool | None:
    """True/False, or None if (px, py) falls outside the image entirely
    — distinct from False (checked and empty), since "we can't see that
    far" and "we looked and there's nothing there" need different
    handling by the far-edge search below."""
    if px < 0 or px >= IMAGE_WIDTH or py < 0 or py >= IMAGE_HEIGHT:
        return None
    return img.getpixel((px, py))[3] > ALPHA_THRESHOLD


# Sampled directly from EC's own RADAR_1KM_RRAI GetLegendGraphic
# (confirmed live via a real GetLegendGraphic request — light blue
# 0.1mm/h up through green/yellow/orange/red/magenta to dark purple at
# 200mm/h; RADAR_1KM_RSNO uses the identical color scale, confirmed
# too) — lets a detected echo be classified by actual intensity, not
# just "is there an echo at all."
_INTENSITY_SWATCHES = [
    (200.0, (48, 0, 73)),
    (125.0, (93, 0, 140)),
    (100.0, (150, 49, 201)),
    (64.0, (254, 2, 146)),
    (50.0, (254, 13, 0)),
    (32.0, (254, 112, 0)),
    (24.0, (254, 169, 0)),
    (16.0, (254, 226, 0)),
    (12.0, (106, 165, 0)),
    (8.0, (0, 135, 0)),
    (4.0, (0, 191, 0)),
    (2.0, (0, 248, 89)),
    (1.0, (0, 152, 254)),
    (0.1, (76, 178, 254)),
]
# EC's own scale steps from "moderate" (16) to this tick — used as the
# bar for "worth flagging as genuinely heavy," not just "there's rain
# or snow somewhere nearby."
SIGNIFICANT_MM_H = 24.0


def _classify_mm_h(rgb: tuple[int, int, int]) -> float:
    """Nearest-color match (by Euclidean RGB distance) against EC's own
    legend swatches — an approximate precipitation rate in mm/h for a
    single pixel's color."""
    best_value, best_dist = 0.1, None
    for value, swatch in _INTENSITY_SWATCHES:
        dist = sum((a - b) ** 2 for a, b in zip(rgb, swatch))
        if best_dist is None or dist < best_dist:
            best_value, best_dist = value, dist
    return best_value


# A storm system needs real areal extent to count as the thing being
# tracked — confirmed live (a real screenshot from the actual kiosk)
# that plain "whichever single pixel is geometrically closest" tracking
# locked onto a tiny, likely-noise blob at 40km while a genuinely
# massive, coherent storm system sat at 64km, 274x the size, completely
# ignored. A coarse CELL_PX x CELL_PX grid (not per-pixel) keeps the
# clustering fast in pure Python — confirmed live ~15-35ms for a full
# wide-frame scan — without needing scipy, which isn't a dependency
# here. Roughly 12 km² per cell at this latitude, so MIN_SIGNIFICANT_CELLS
# is a ~500km² minimum footprint: comfortably bigger than a stray
# sprinkle, comfortably smaller than a real system worth tracking.
_CLUSTER_CELL_PX = 8
MIN_SIGNIFICANT_CELLS = 40


def _cluster_blobs(alpha_mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """8-connected clusters of occupied _CLUSTER_CELL_PX-sized grid
    cells over the full echo mask (each list entry is that blob's
    (grid_y, grid_x) cell coordinates)."""
    h, w = alpha_mask.shape
    gh, gw = h // _CLUSTER_CELL_PX, w // _CLUSTER_CELL_PX
    trimmed = alpha_mask[: gh * _CLUSTER_CELL_PX, : gw * _CLUSTER_CELL_PX]
    occupied = trimmed.reshape(gh, _CLUSTER_CELL_PX, gw, _CLUSTER_CELL_PX).any(axis=(1, 3))

    visited = np.zeros_like(occupied)
    blobs = []
    for gy in range(gh):
        for gx in range(gw):
            if not occupied[gy, gx] or visited[gy, gx]:
                continue
            queue = deque([(gy, gx)])
            visited[gy, gx] = True
            cells = []
            while queue:
                y, x = queue.popleft()
                cells.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < gh and 0 <= nx < gw and occupied[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((ny, nx))
            blobs.append(cells)
    return blobs


# A blob this small (in cells) is almost certainly a rendering/
# compression artifact rather than a real, distinct shower — filters
# out single-pixel noise from the "any size" trajectory check below
# without imposing the full MIN_SIGNIFICANT_CELLS size bar on it.
MIN_REAL_CELLS = 3


def _nearest_point_in_blob(alpha_mask: np.ndarray, cells: list[tuple[int, int]], cx: int, cy: int) -> tuple | None:
    """(lat, lon, distance_km) of the closest in-range echo pixel
    belonging to this one blob, or None if every pixel in it (after
    NEARBY_RADIUS_KM filtering) turns out to be out of range."""
    nearest = None
    for gy, gx in cells:
        py0, px0 = gy * _CLUSTER_CELL_PX, gx * _CLUSTER_CELL_PX
        for py in range(py0, min(py0 + _CLUSTER_CELL_PX, IMAGE_HEIGHT), _SAMPLE_STRIDE):
            for px in range(px0, min(px0 + _CLUSTER_CELL_PX, IMAGE_WIDTH), _SAMPLE_STRIDE):
                if not alpha_mask[py, px]:
                    continue
                lat = WEATHER_LAT - (py - cy) * _DEG_PER_PX
                lon = WEATHER_LON + (px - cx) * _DEG_PER_PX
                dist = _distance_km(WEATHER_LAT, WEATHER_LON, lat, lon)
                if dist > NEARBY_RADIUS_KM:
                    continue
                if nearest is None or dist < nearest[2]:
                    nearest = (lat, lon, dist)
    return nearest


def _max_mm_h_in_blob(img: Image.Image, alpha_mask: np.ndarray, cells: list[tuple[int, int]]) -> float:
    max_mm_h = 0.0
    for gy, gx in cells:
        py0, px0 = gy * _CLUSTER_CELL_PX, gx * _CLUSTER_CELL_PX
        for py in range(py0, min(py0 + _CLUSTER_CELL_PX, IMAGE_HEIGHT), _SAMPLE_STRIDE):
            for px in range(px0, min(px0 + _CLUSTER_CELL_PX, IMAGE_WIDTH), _SAMPLE_STRIDE):
                if not alpha_mask[py, px]:
                    continue
                max_mm_h = max(max_mm_h, _classify_mm_h(img.getpixel((px, py))[:3]))
    return max_mm_h


def _blob_centroid(alpha_mask: np.ndarray, cells: list[tuple[int, int]], cx: int, cy: int) -> tuple[float, float]:
    """Mean lat/lon over this blob's own occupied pixels — a far
    steadier position to track across frames than the nearest edge
    pixel (see _nearest_point_in_blob), which shifts around as a
    storm's leading edge changes shape frame to frame even when its
    bulk hasn't actually moved much. Used by storm_motion below, where
    that steadiness is the whole point."""
    xs, ys = [], []
    for gy, gx in cells:
        py0, px0 = gy * _CLUSTER_CELL_PX, gx * _CLUSTER_CELL_PX
        for py in range(py0, min(py0 + _CLUSTER_CELL_PX, IMAGE_HEIGHT), _SAMPLE_STRIDE):
            for px in range(px0, min(px0 + _CLUSTER_CELL_PX, IMAGE_WIDTH), _SAMPLE_STRIDE):
                if alpha_mask[py, px]:
                    xs.append(px)
                    ys.append(py)
    mean_px, mean_py = sum(xs) / len(xs), sum(ys) / len(ys)
    lat = WEATHER_LAT - (mean_py - cy) * _DEG_PER_PX
    lon = WEATHER_LON + (mean_px - cx) * _DEG_PER_PX
    return lat, lon


def _track_blob_for_motion(img: Image.Image) -> tuple[float, float] | None:
    """This one frame's own centroid (see _blob_centroid) for whichever
    blob is "the storm" to track for motion purposes — the largest
    significant-sized blob if one exists (same MIN_SIGNIFICANT_CELLS
    bar the badges use), else the largest blob of any real size. No
    frame-to-frame object identity/correspondence is attempted (there's
    no cell-tracking algorithm here, just this one heuristic) — for a
    single dominant system near the location this tracks the same real
    storm each frame; for genuinely scattered, unrelated showers it can
    occasionally jump between them, same honest approximation this
    whole module already is (see its own module docstring)."""
    cx, cy = IMAGE_WIDTH // 2, IMAGE_HEIGHT // 2
    arr = np.array(img)
    alpha_mask = arr[:, :, 3] > ALPHA_THRESHOLD
    real_blobs = [b for b in _cluster_blobs(alpha_mask) if len(b) >= MIN_REAL_CELLS]
    if not real_blobs:
        return None
    significant = [b for b in real_blobs if len(b) >= MIN_SIGNIFICANT_CELLS]
    largest = max(significant or real_blobs, key=len)
    return _blob_centroid(alpha_mask, largest, cx, cy)


def storm_motion(kind: str) -> dict | None:
    """{"bearing_deg", "speed_kmh", "sample_count"} measured directly
    from the real cached radar frames (see _frame_history,
    FRAME_HISTORY_SIZE) — the dominant tracked blob's own centroid in
    the oldest cached frame vs. the newest, which is a genuine measured
    displacement over real elapsed time rather than a guess. Session
    request: "use this [the cached frames] to actually gauge storm
    direction instead of guessing."

    None if fewer than 2 cached frames have a trackable blob at all
    (early in a fresh deploy/restart, or right after switching kind,
    before enough real pulls have accumulated), the two usable samples
    are less than MIN_TREND_GAP_MINUTES apart (guards the same "not
    actually a new sample" case _record_and_trend already guards
    against), or the measured displacement is under
    STATIONARY_THRESHOLD_KM (not moving meaningfully enough to trust a
    bearing from it)."""
    points = []
    for cache_bust, raw in _frame_history[kind]:
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            continue
        centroid = _track_blob_for_motion(img)
        if centroid is not None:
            points.append((cache_bust, centroid[0], centroid[1]))
    if len(points) < 2:
        return None

    old_bust, old_lat, old_lon = points[0]
    new_bust, new_lat, new_lon = points[-1]
    gap_minutes = (new_bust - old_bust) * REFRESH_SECONDS / 60
    if gap_minutes < MIN_TREND_GAP_MINUTES:
        return None
    moved_km = _distance_km(old_lat, old_lon, new_lat, new_lon)
    if moved_km < STATIONARY_THRESHOLD_KM:
        return None
    return {
        "bearing_deg": _bearing_deg(old_lat, old_lon, new_lat, new_lon),
        "speed_kmh": moved_km / (gap_minutes / 60),
        "sample_count": len(points),
    }


def _scan_nearby(img: Image.Image) -> dict:
    """{"nearest", "max_mm_h", "nearest_any", "max_mm_h_any"} within
    NEARBY_RADIUS_KM.

    "nearest"/"max_mm_h": the nearest point (and its blob's own peak
    intensity) belonging to whichever cluster of connected
    precipitation actually has real areal extent (see
    MIN_SIGNIFICANT_CELLS) — not just whichever single pixel happens to
    be geometrically closest (see _cluster_blobs' comment for why that
    distinction turned out to matter for real). None/0.0 if nothing
    qualifies.

    "nearest_any"/"max_mm_h_any": the nearest point (and ITS OWN blob's
    peak intensity, not the significant blob's) belonging to ANY real
    blob (MIN_REAL_CELLS, a much lower bar — just enough to exclude
    single-pixel rendering noise), regardless of overall size. This
    exists so a small blob that doesn't clear the significance bar can
    still be checked for (a) whether its own direction of travel is a
    genuine direct hit on WEATHER_LAT/WEATHER_LON (see
    _heading_toward_me), and (b) whether IT is severe in its own right
    — a small, fast, intense cell on a direct course is exactly the
    kind of thing that shouldn't be under-reported just for lacking
    the significant blob's areal extent."""
    cx, cy = IMAGE_WIDTH // 2, IMAGE_HEIGHT // 2
    arr = np.array(img)
    alpha_mask = arr[:, :, 3] > ALPHA_THRESHOLD
    all_blobs = _cluster_blobs(alpha_mask)

    real_blobs = [b for b in all_blobs if len(b) >= MIN_REAL_CELLS]
    any_blob, nearest_any = None, None
    for cells in real_blobs:
        point = _nearest_point_in_blob(alpha_mask, cells, cx, cy)
        if point is not None and (nearest_any is None or point[2] < nearest_any[2]):
            nearest_any = point
            any_blob = cells
    max_mm_h_any = _max_mm_h_in_blob(img, alpha_mask, any_blob) if any_blob is not None else 0.0

    significant_blobs = [b for b in real_blobs if len(b) >= MIN_SIGNIFICANT_CELLS]
    best_blob, best_nearest = None, None
    for cells in significant_blobs:
        point = _nearest_point_in_blob(alpha_mask, cells, cx, cy)
        if point is not None and (best_nearest is None or point[2] < best_nearest[2]):
            best_nearest = point
            best_blob = cells

    # The significant blob and the nearest-any blob are frequently the
    # same one (whenever the closest real precipitation is itself
    # significant) — skip re-scanning intensity in that case rather
    # than doing the same work twice.
    if best_blob is any_blob:
        max_mm_h = max_mm_h_any
    else:
        max_mm_h = _max_mm_h_in_blob(img, alpha_mask, best_blob) if best_blob is not None else 0.0

    return {
        "nearest": best_nearest, "max_mm_h": max_mm_h,
        "nearest_any": nearest_any, "max_mm_h_any": max_mm_h_any,
    }


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


# Separate, parallel position history for the nearest blob of ANY real
# size (see _scan_nearby's "nearest_any", MIN_REAL_CELLS) — used only
# to work out whether a small blob's own direction of travel is a
# genuine, direct hit on WEATHER_LAT/WEATHER_LON, not just "it's
# somewhere nearby and getting closer in a generic sense" (which could
# just as easily mean it's going to pass 50km to one side). Confirmed
# by session request: a small blob should still be tracked, but only
# when it's actually headed here — being small on its own is no longer
# disqualifying by itself, the way MIN_SIGNIFICANT_CELLS alone would
# otherwise make it.
_any_history: dict[str, list[tuple[datetime, float, float]]] = {"rain": [], "snow": []}
# How close the extrapolated path needs to pass to WEATHER_LAT/LON to
# count as "heading toward my exact location" — wider than a literal 0
# to allow for real imprecision in a bearing estimated from only two
# radar samples, not a demand for pixel-perfect aim.
DIRECT_HIT_RADIUS_KM = 15


def _closest_approach_km(
    storm_lat: float, storm_lon: float, bearing_deg_: float, target_lat: float, target_lon: float
) -> float | None:
    """Perpendicular (cross-track) distance from the target to the
    storm's forward path, given its current position and bearing of
    travel — standard point-to-ray geometry, using a local flat-earth
    approximation (fine at these ranges, well under 150km). None if the
    closest point on that path lies BEHIND the storm's current
    position: it's already moving away from the target along its own
    track, not toward it, regardless of the raw straight-line distance
    between them right now."""
    dir_east = sin(radians(bearing_deg_))
    dir_north = cos(radians(bearing_deg_))
    rel_east = (target_lon - storm_lon) * 111.0 * cos(radians(storm_lat))
    rel_north = (target_lat - storm_lat) * 111.0
    along_track = rel_east * dir_east + rel_north * dir_north
    if along_track <= 0:
        return None
    return abs(rel_east * dir_north - rel_north * dir_east)


def _heading_toward_me(kind: str, now: datetime, position: tuple[float, float] | None) -> dict | None:
    """{"eta_minutes", "direction", "direction_word"} once a real
    measured bearing of travel (see storm_motion, preferred) — or, in
    its cold-start window, the older per-rerun position-history proxy
    below — shows this blob's own direction of travel would bring it
    within DIRECT_HIT_RADIUS_KM of WEATHER_LAT/WEATHER_LON if it keeps
    moving the way it has been. None otherwise (not enough samples yet,
    not moving meaningfully, or genuinely headed somewhere else).
    eta_minutes is how long until it reaches the closest point on that
    path to here, at its currently tracked speed — not necessarily a
    literal overhead pass, just within DIRECT_HIT_RADIUS_KM of it.

    position is this frame's current closest-approach point (from
    _scan_nearby's "nearest_any") — used as the storm's current
    location for the along-track/ETA math and for the "direction"
    compass label (bearing FROM here TO the storm), which is a
    different question from bearing_deg_ below (the storm's OWN
    direction of travel)."""
    history = _any_history[kind]
    if position is not None:
        history.append((now, position[0], position[1]))
    cutoff = now.timestamp() - HISTORY_WINDOW_MINUTES * 60
    history[:] = [(t, lat, lon) for t, lat, lon in history if t.timestamp() >= cutoff]

    if position is None:
        return None

    motion = storm_motion(kind)
    if motion is not None:
        bearing_deg_, speed_kmh = motion["bearing_deg"], motion["speed_kmh"]
    else:
        if len(history) < 2:
            return None
        old_t, old_lat, old_lon = history[0]
        new_t, new_lat, new_lon = history[-1]
        gap_minutes = (new_t - old_t).total_seconds() / 60
        if gap_minutes < MIN_TREND_GAP_MINUTES:
            return None
        moved_km = _distance_km(old_lat, old_lon, new_lat, new_lon)
        if moved_km < STATIONARY_THRESHOLD_KM:
            return None  # not moving meaningfully enough to trust a bearing from it
        bearing_deg_ = _bearing_deg(old_lat, old_lon, new_lat, new_lon)
        speed_kmh = moved_km / (gap_minutes / 60)

    new_lat, new_lon = position
    approach = _closest_approach_km(new_lat, new_lon, bearing_deg_, WEATHER_LAT, WEATHER_LON)
    if approach is None or approach > DIRECT_HIT_RADIUS_KM:
        return None

    rel_east = (WEATHER_LON - new_lon) * 111.0 * cos(radians(new_lat))
    rel_north = (WEATHER_LAT - new_lat) * 111.0
    along_track_km = rel_east * sin(radians(bearing_deg_)) + rel_north * cos(radians(bearing_deg_))
    eta_minutes = round((along_track_km / speed_kmh) * 60)
    to_bearing = _bearing_deg(WEATHER_LAT, WEATHER_LON, new_lat, new_lon)
    return {
        "eta_minutes": max(0, eta_minutes),
        "direction": compass_abbr(to_bearing),
        "direction_word": compass_word(to_bearing),
    }


# Within this distance, the nearest echo counts as "here" rather than
# "approaching" — the badge switches from a countdown-to-arrival to a
# countdown-to-clearing at this point (see precip_status below).
ARRIVED_RADIUS_KM = 5

# precip_status is called independently from the hero badge, the
# morning briefing, and the Radar page itself — which in turn calls
# tracking_overlay, which used to call precip_status AGAIN internally.
# That meant a single rerun could decode + pixel-scan the same radar
# frame up to 4 times over, and worse, called _record_and_trend that
# many times too, each with its own datetime.now() — its own docstring
# says "one point per real API call (~every 6 min)" but it was actually
# recording one point per CALLER per rerun. Keyed by kind (only ever
# "rain"/"snow", so inherently bounded) the same way _history already
# is, this caches the decode+scan+trend-record once per real
# REFRESH_SECONDS window regardless of how many callers ask for it.
_echo_cache: dict[str, tuple[int, dict]] = {}


def _decode_and_scan(kind: str) -> dict:
    """{"img", "nearest", "trend", "max_mm_h", "nearest_any",
    "max_mm_h_any", "heading_toward_me"} for the current radar frame —
    see _heading_toward_me for that field's shape (a dict once a small
    blob's own path is a confirmed direct hit, else None)."""
    layer = SNOW_LAYER if kind == "snow" else RAIN_LAYER
    cache_bust = int(time.time() // REFRESH_SECONDS)
    cached = _echo_cache.get(kind)
    if cached is not None and cached[0] == cache_bust:
        return cached[1]

    raw = _fetch_radar_bytes(layer)
    now = datetime.now()
    img = nearest = nearest_any = None
    max_mm_h = max_mm_h_any = 0.0
    if raw:
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            scan = _scan_nearby(img)
            nearest, max_mm_h = scan["nearest"], scan["max_mm_h"]
            nearest_any, max_mm_h_any = scan["nearest_any"], scan["max_mm_h_any"]
        except Exception:
            img = nearest = nearest_any = None
            max_mm_h = max_mm_h_any = 0.0
    trend = _record_and_trend(kind, now, nearest[2] if nearest else None)
    heading_toward_me = _heading_toward_me(kind, now, nearest_any[:2] if nearest_any else None)
    result = {
        "img": img, "nearest": nearest, "trend": trend, "max_mm_h": max_mm_h,
        "nearest_any": nearest_any, "max_mm_h_any": max_mm_h_any, "heading_toward_me": heading_toward_me,
    }
    _echo_cache[kind] = (cache_bust, result)
    return result


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

    Below MIN_SIGNIFICANT_CELLS, a blob is still reported here if (and
    only if) its own tracked direction of travel is a confirmed direct
    hit on WEATHER_LAT/WEATHER_LON (see _heading_toward_me) — a small
    cell that's genuinely headed straight here matters regardless of
    its size; one that's merely nearby but on course to pass well to
    one side stays correctly ignored.
    """
    state = _decode_and_scan(kind)
    img, nearest, trend = state["img"], state["nearest"], state["trend"]

    if nearest is None:
        # No significant-sized system nearby — but a smaller blob can
        # still matter if it's genuinely on course for here (see
        # _heading_toward_me): being small no longer disqualifies it on
        # its own, only "not actually headed this way" does.
        nearest_any = state["nearest_any"]
        if nearest_any is not None and nearest_any[2] <= ARRIVED_RADIUS_KM:
            bearing_deg_ = _bearing_deg(WEATHER_LAT, WEATHER_LON, nearest_any[0], nearest_any[1])
            return {
                "state": "arrived", "minutes": None,
                "direction": compass_abbr(bearing_deg_), "direction_word": compass_word(bearing_deg_),
            }
        direct_hit = state["heading_toward_me"]
        if direct_hit is None:
            return None
        return {
            "state": "approaching", "minutes": direct_hit["eta_minutes"],
            "direction": direct_hit["direction"], "direction_word": direct_hit["direction_word"],
        }

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


def severe_precip_status(kind: str = "rain") -> dict | None:
    """{"mm_h", "direction", "direction_word"} once the strongest echo
    within the tracked system (not just the nearest point — a genuinely
    severe cell is often small and embedded in broader lighter
    precipitation, see _scan_nearby) meets or exceeds SIGNIFICANT_MM_H,
    EC's own scale step from "moderate" into "heavy". None most of the
    time — ordinary rain/snow sits well under this.

    Checks the significant blob first (see MIN_SIGNIFICANT_CELLS); if
    that one isn't severe (or doesn't exist), also checks a smaller
    blob's own intensity, but only when it's confirmed genuinely headed
    straight at WEATHER_LAT/WEATHER_LON (see _heading_toward_me) — a
    small, fast, intense cell on a direct course is exactly the kind of
    thing that shouldn't be under-reported just for lacking the
    significant blob's areal extent. Direction is the bearing to
    whichever blob's own nearest pixel produced the match, same
    convention as precip_status — not necessarily the exact spot of the
    heaviest cell, but the closest real reference point for "which way
    to look.\""""
    state = _decode_and_scan(kind)

    if state["max_mm_h"] >= SIGNIFICANT_MM_H and state["nearest"] is not None:
        lat, lon, _ = state["nearest"]
        mm_h = state["max_mm_h"]
    elif (
        state["heading_toward_me"] is not None
        and state["max_mm_h_any"] >= SIGNIFICANT_MM_H
        and state["nearest_any"] is not None
    ):
        lat, lon, _ = state["nearest_any"]
        mm_h = state["max_mm_h_any"]
    else:
        return None

    bearing_deg_ = _bearing_deg(WEATHER_LAT, WEATHER_LON, lat, lon)
    return {
        "mm_h": mm_h,
        "direction": compass_abbr(bearing_deg_),
        "direction_word": compass_word(bearing_deg_),
    }


# Tracks whether each kind was already flagged as severe as of the last
# check — module-level (not st.session_state) so the "only alert once
# per event" edge-detection below is shared process-wide the same way
# _history already is, not reset by a session reconnect.
_severe_flagged: dict[str, bool] = {"rain": False, "snow": False}


def severe_weather_alert(kind: str = "rain") -> dict | None:
    """A one-time toast-ready alert dict (see app.py's news_queue) the
    moment genuinely heavy precipitation is newly detected nearby —
    fires once per event (edge-triggered off _severe_flagged), not
    every rerun while it persists, and resets once conditions drop
    back under SIGNIFICANT_MM_H so a later, genuinely new event can
    fire again.

    Takes a single `kind`, caller-chosen, rather than checking both
    rain and snow internally — confirmed live that EC's snow layer
    (RADAR_1KM_RSNO) isn't itself gated by temperature and can show the
    exact same reflectivity echo as the rain layer regardless of
    season, so checking both unconditionally could fire a "heavy snow"
    alert in the middle of July. Callers should pass whichever kind
    actually matches the current weather category (see app.py's own
    `precip_kind`, computed from the real forecast) the same way
    precip_status already expects."""
    status = severe_precip_status(kind)
    was_flagged = _severe_flagged[kind]
    _severe_flagged[kind] = status is not None
    if status is not None and not was_flagged:
        label = "Snow" if kind == "snow" else "Rain"
        return {
            "kind": "weather",
            "headline": f"Heavy {label.lower()} moving in from the {status['direction_word']} "
            f"— {status['mm_h']:.0f} mm/h",
            "category": "Severe Weather",
            "important": True,
        }
    return None


# Tracks whether each kind had anything detected nearby as of the last
# check — a separate, earlier-firing flag from _severe_flagged above
# (this one triggers on mere detection, not on crossing an intensity
# threshold), same module-level/edge-triggered reasoning.
_tracking_flagged: dict[str, bool] = {"rain": False, "snow": False}


def tracking_started_alert(kind: str = "rain") -> dict | None:
    """A one-time toast-ready alert dict the moment radar first picks
    up ANYTHING within NEARBY_RADIUS_KM — regardless of confirmed
    direction or intensity (see severe_weather_alert for the intensity-
    gated version of this same idea, and for why this takes a single
    caller-chosen `kind` rather than checking both internally). This is
    deliberately the earliest possible signal: precip_status itself
    won't call something "approaching" until a real closing trend has
    had time to establish, but this fires the moment there's anything
    to track at all. Edge-triggered off _tracking_flagged the same way
    severe_weather_alert is off _severe_flagged — fires once per event,
    resets once nothing's detected so a later, genuinely new detection
    can fire again."""
    state = _decode_and_scan(kind)
    currently_tracking = state["nearest"] is not None
    was_tracking = _tracking_flagged[kind]
    _tracking_flagged[kind] = currently_tracking
    if currently_tracking and not was_tracking:
        distance_km = state["nearest"][2]
        label = "Snow" if kind == "snow" else "Rain"
        return {
            "kind": "weather",
            "headline": f"{label} now on the radar, {distance_km:.0f} km out",
            "category": "Weather Tracking",
            "important": False,
        }
    return None


def tracking_overlay(kind: str = "rain") -> dict | None:
    """Where the nearest detected echo actually sits on the frame — as a
    0-100 position (matching how the fixed location marker is already
    positioned with top/left percentages), so the Radar page can draw a
    real line from the threat to the user's own marker instead of
    leaving the tracking data as a separate text-only badge underneath
    the map. None if nothing's within NEARBY_RADIUS_KM right now.

    Shares its decode+scan with precip_status via _decode_and_scan (see
    its comment above) — calling precip_status(kind) below reuses that
    same cached state rather than repeating the work.

    Falls back to "nearest_any" (any real blob, not just a
    significant-sized one) the same way precip_status does — confirmed
    live this mattered: without it, a small blob confirmed heading
    straight at WEATHER_LAT/WEATHER_LON would show up in the text badge
    but draw no line/marker at all on the map itself, since this
    function returned None outright whenever no significant blob
    existed."""
    state = _decode_and_scan(kind)
    nearest = state["nearest"] or state["nearest_any"]
    if nearest is None:
        return None
    lat, lon, distance_km = nearest
    px, py = _latlon_to_pixel(lat, lon)
    status = precip_status(kind)
    return {
        "x_pct": max(0.0, min(100.0, px / IMAGE_WIDTH * 100)),
        "y_pct": max(0.0, min(100.0, py / IMAGE_HEIGHT * 100)),
        "distance_km": distance_km,
        "active": status is not None,
        "minutes": status["minutes"] if status else None,
        "direction": status["direction"] if status else compass_abbr(_bearing_deg(WEATHER_LAT, WEATHER_LON, lat, lon)),
    }


def nearby_city_markers() -> list[dict]:
    """Neutral reference points for real nearby towns (see config.
    RADAR_NEARBY_CITIES), same 0-100 coordinate space tracking_overlay
    already uses — so it's obvious where the rain actually is relative
    to real places, not just relative to Corbeil's own marker. Purely
    local pixel math, no fetch — any city that happens to fall outside
    the image's own bbox is silently dropped rather than shown clipped
    at the edge, so RADAR_NEARBY_CITIES doesn't need to stay hand-tuned
    to BBOX_MARGIN_DEGREES_LAT/LON."""
    markers = []
    for city in RADAR_NEARBY_CITIES:
        px, py = _latlon_to_pixel(city["lat"], city["lon"])
        if 0 <= px < IMAGE_WIDTH and 0 <= py < IMAGE_HEIGHT:
            markers.append({"label": city["label"], "x_pct": px / IMAGE_WIDTH * 100, "y_pct": py / IMAGE_HEIGHT * 100})
    return markers
