"""Live weather radar imagery from Environment Canada — a looping GIF of
the last several real frames, nearby city reference markers, and a
plain "Moving NE at 32 km/h" readout of the dominant echo's own
currently-measured drift. No arrival prediction: this app used to also
project the storm's own measured motion forward to guess when/if it
would reach the user's exact location, at increasing range (a near-term
shape-and-motion projection, then a separate longer-range straight-line
extrapolation on top of that) — removed at the user's own request after
judging the whole lookahead-forecasting layer too inconsistent to trust,
in favor of just the raw radar map, readable manually. Everything below
describes where precipitation currently IS and how it's currently
moving, not predictions of where it's going to be.

`radar_image_url` builds the image URL for the Radar page's <img> tag —
the browser fetches that one directly, not our own backend, so it
needs no throttle/cache of its own. Everything else here does fetch
server-side (to read pixels), so it goes through fetch_throttle and is
cached to the radar's own real update cadence.
"""

import base64
import io
import re
import time
from collections import deque
from datetime import datetime, timedelta
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

# WMS renders true-transparent background as alpha 0; real echo pixels
# (even the faintest trace-precipitation color) render meaningfully
# above that. A small margin above 0 filters out compression artifacts
# at tile edges without needing to hand-check every legend color.
ALPHA_THRESHOLD = 20
_SAMPLE_STRIDE = 3

# How far apart two samples need to be before trusting a speed estimate
# from them — the radar itself only refreshes every REFRESH_SECONDS, so
# two samples closer together than that are the same frame twice, not a
# real trend point.
MIN_TREND_GAP_MINUTES = 5
# A distance change smaller than this over the tracked window is
# treated as noise (radar echo edges flicker slightly frame to frame
# even for a genuinely stationary cell), not real movement.
STATIONARY_THRESHOLD_KM = 1.5

_last_good_bytes: dict[str, bytes] = {}


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
RADAR_LOOP_FRAME_MS = 600  # per-frame duration
# How much longer the true final frame holds, relative to every other
# frame — dialed back from 2x to 1.5x (900ms): with FRAME_HISTORY_SIZE
# now spanning up to an hour, real consecutive captures can genuinely
# look near-identical when a storm's motion is slow, which combined
# with a long hold on the last one can read as "more than one frame is
# lingering" even though the duration metadata itself only ever marks
# the single true final frame — confirmed live by decoding a real saved
# GIF and checking its own per-frame durations directly. A shorter hold
# still gives the "current moment" a distinguishing pause without
# making that impression last as long.
RADAR_LOOP_FINAL_HOLD_MULTIPLIER = 1.5

# Rebuilding and re-encoding the whole GIF is real work (decode N real
# PNGs, composite each against the tile background, re-encode as GIF)
# that only ever needs to happen once per real REFRESH_SECONDS window —
# the underlying frames don't change in between. This used to run fresh
# on every single 5s autorefresh rerun regardless, for no benefit,
# producing an identical result every time within that window. Cached
# by exactly which real frame timestamps are currently in play, so a
# genuinely new frame arriving still rebuilds it right away.
_loop_cache: dict[str, tuple[tuple, str]] = {}


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
    against the image by percentage — the city markers — stays
    correctly placed regardless of which frame the loop happens to be
    showing; nothing else needs to change to support this."""
    layer = SNOW_LAYER if kind == "snow" else RAIN_LAYER
    _fetch_radar_bytes(layer)  # ensures this rerun's frame is recorded before reading history
    history = _frame_history[kind]
    if len(history) < 2:
        return None

    cache_key = tuple(t for t, _ in history)
    cached = _loop_cache.get(kind)
    if cached is not None and cached[0] == cache_key:
        return cached[1]

    try:
        composited = []
        for _, raw in history:
            frame = Image.open(io.BytesIO(raw)).convert("RGBA")
            bg = Image.new("RGBA", frame.size, _RADAR_TILE_BG)
            composited.append(Image.alpha_composite(bg, frame).convert("RGB"))
    except Exception:
        return None

    durations = [RADAR_LOOP_FRAME_MS] * (len(composited) - 1) + [round(RADAR_LOOP_FRAME_MS * RADAR_LOOP_FINAL_HOLD_MULTIPLIER)]
    buf = io.BytesIO()
    composited[0].save(
        buf, format="GIF", save_all=True, append_images=composited[1:],
        duration=durations, loop=0, optimize=True,
    )
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    result = f"data:image/gif;base64,{encoded}"
    _loop_cache[kind] = (cache_key, result)
    return result


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


def _parse_ec_time(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


_TIME_DIMENSION_RE_TEMPLATE = (
    r'<Name>{layer}</Name>.*?<Dimension name="time"[^>]*default="([^"]+)"[^>]*>([^<]+)</Dimension>'
)


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def _fetch_time_dimension_raw(layer: str) -> tuple[datetime, datetime]:
    """(default_time, start_time) — the newest and oldest real radar
    timestamps EC's own WMS currently has available for this layer
    (confirmed live: a rolling ~3 hour window at native PT6M steps),
    read straight from its own GetCapabilities Dimension element rather
    than assumed, since EC controls both numbers, not us."""
    fetch_throttle.wait_turn()
    resp = requests.get(
        WMS_URL, params={"service": "WMS", "version": "1.3.0", "request": "GetCapabilities", "layers": layer},
        timeout=10,
    )
    resp.raise_for_status()
    match = re.search(_TIME_DIMENSION_RE_TEMPLATE.format(layer=re.escape(layer)), resp.text, re.DOTALL)
    if not match:
        raise ValueError(f"no time dimension found for {layer}")
    default_str, extent_str = match.groups()
    return _parse_ec_time(default_str), _parse_ec_time(extent_str.split("/")[0])


_last_good_time_dimension: dict[str, tuple[datetime, datetime]] = {}


def _fetch_time_dimension(layer: str) -> tuple[datetime, datetime] | None:
    try:
        result = _fetch_time_dimension_raw(layer)
    except Exception:
        return _last_good_time_dimension.get(layer)
    _last_good_time_dimension[layer] = result
    return result


def _fetch_radar_bytes_at(layer: str, frame_time: datetime) -> bytes | None:
    """One specific past real radar frame, fetched directly from EC's
    own WMS TIME dimension instead of waited-for organically — see
    _fetch_time_dimension for how far back that's actually available.
    None on any failure: a network error, or (confirmed live) EC
    rejecting a timestamp outside its own retained window with an XML
    ServiceExceptionReport instead of a PNG — either way, a missing
    historical frame just means a shorter loop/motion sample this one
    time, not a crash."""
    try:
        fetch_throttle.wait_turn()
        resp = requests.get(
            WMS_URL,
            params={
                "service": "WMS", "version": "1.3.0", "request": "GetMap", "layers": layer,
                "format": "image/png", "transparent": "true",
                "width": IMAGE_WIDTH, "height": IMAGE_HEIGHT, "crs": "EPSG:4326", "bbox": _bbox(),
                "time": frame_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            timeout=10,
        )
        resp.raise_for_status()
        if not resp.headers.get("content-type", "").startswith("image"):
            return None  # a ServiceExceptionReport came back instead of a real frame
        return resp.content
    except Exception:
        return None


# Last few real radar frames, oldest first, so a short loop can show
# where the storm's actually been moving — not just a single static
# snapshot (session request: "cache the last three pulls... play them
# in order", later widened to 5 and backfilled straight from EC's own
# TIME dimension: "use this to actually gauge storm direction instead
# of guessing" / "pull previous radar images directly from the source
# without having to build the cache manually", then to 10: "get an
# hour's worth of movement"). Each real frame is REFRESH_SECONDS (~6
# min) apart, so 10 frames covers roughly the last 54-60 minutes of
# real motion — the same raw frames storm_motion() below measures
# actual bearing/speed from, not just what the loop animates. Keyed by
# the frame's own real EC timestamp (not a locally-computed bucket) so
# live-fetched and backfilled frames share one consistent, ground-truth
# timeline — storm_motion's elapsed-time math is then a real measured
# duration, not an assumption that our own clock lines up with EC's
# composite schedule.
FRAME_HISTORY_SIZE = 10
_frame_history: dict[str, list[tuple[datetime, bytes]]] = {"rain": [], "snow": []}
# How many NEW historical frames _ensure_frame_history will fetch in a
# single call, and how soon it's allowed to pick up where it left off.
# Confirmed live earlier this session that even ONE extra network-
# shaped call on the cold-start path was enough to stall the app's
# entire autorefresh cycle — backfilling all of a 10-frame gap (9
# sequential throttled fetches) in one script run risked a much bigger
# version of that exact outage. Spreading it across several quick
# reruns instead keeps any single run's own fetch burden small, at the
# cost of the full cache taking a few real seconds longer to fill —
# invisible for a background cache nothing blocks on.
MAX_BACKFILL_FETCHES_PER_CALL = 2
BACKFILL_RETRY_SECONDS = 4
# Throttles backfill attempts to at most once per REFRESH_SECONDS once
# an attempt comes back completely empty-handed (a real failure, e.g.
# EC's own service having a bad moment) — avoids hammering EC's
# GetCapabilities/GetMap every few seconds in that case. Only applies
# once nothing new was found; while genuinely still making progress
# toward FRAME_HISTORY_SIZE, the much shorter BACKFILL_RETRY_SECONDS
# governs instead (see _backfill_stalled).
_backfill_attempted_at: dict[str, float] = {"rain": 0.0, "snow": 0.0}
_backfill_stalled: dict[str, bool] = {"rain": False, "snow": False}


def _record_frame(kind: str, raw: bytes, dims: tuple[datetime, datetime] | None) -> None:
    if dims is None:
        return  # can't stamp this frame with a real timestamp right now — skip recording it, try again next rerun
    frame_time = dims[0]
    history = _frame_history[kind]
    if history and history[-1][0] == frame_time:
        return  # already recorded this exact real frame
    history.append((frame_time, raw))
    history.sort(key=lambda item: item[0])
    del history[: -FRAME_HISTORY_SIZE]


def _ensure_frame_history(kind: str, layer: str, dims: tuple[datetime, datetime] | None) -> None:
    """Backfills _frame_history straight from EC's own real historical
    frames (see _fetch_radar_bytes_at) the first time this kind needs
    it, instead of waiting the better part of an hour for
    FRAME_HISTORY_SIZE frames to accumulate one real refresh at a time.
    Fetches at most MAX_BACKFILL_FETCHES_PER_CALL new frames per call,
    accumulating across however many reruns it takes to fill the gap
    rather than blocking any single one for the whole thing (see
    MAX_BACKFILL_FETCHES_PER_CALL's own comment for why).

    Takes `dims` from the caller (see _fetch_radar_bytes) rather than
    fetching it itself — _record_frame right before this already needs
    the exact same value, and even a cache-hit second call turned out
    to be worth avoiding on the cold-start path (see
    MAX_BACKFILL_FETCHES_PER_CALL's own comment on why that path is
    sensitive to any extra call at all)."""
    history = _frame_history[kind]
    if len(history) >= FRAME_HISTORY_SIZE:
        return
    now_ts = time.time()
    cooldown = REFRESH_SECONDS if _backfill_stalled[kind] else BACKFILL_RETRY_SECONDS
    if now_ts - _backfill_attempted_at[kind] < cooldown:
        return
    _backfill_attempted_at[kind] = now_ts

    if dims is None:
        _backfill_stalled[kind] = True
        return
    default_time, start_time = dims

    have = {t for t, _ in history}
    fetched_count = 0
    for i in range(1, FRAME_HISTORY_SIZE):
        if fetched_count >= MAX_BACKFILL_FETCHES_PER_CALL:
            break
        frame_time = default_time - timedelta(seconds=REFRESH_SECONDS * i)
        if frame_time < start_time or frame_time in have:
            continue
        raw = _fetch_radar_bytes_at(layer, frame_time)
        if raw is not None:
            history.append((frame_time, raw))
            have.add(frame_time)
            fetched_count += 1
    _backfill_stalled[kind] = fetched_count == 0
    history.sort(key=lambda item: item[0])
    del history[: -FRAME_HISTORY_SIZE]


def _fetch_radar_bytes(layer: str) -> bytes | None:
    kind = "snow" if layer == SNOW_LAYER else "rain"
    cache_bust = int(time.time() // REFRESH_SECONDS)
    try:
        result = _fetch_radar_bytes_raw(layer, cache_bust)
    except Exception:
        return _last_good_bytes.get(layer)
    _last_good_bytes[layer] = result

    dims = _fetch_time_dimension(layer)
    _record_frame(kind, result, dims)
    _ensure_frame_history(kind, layer, dims)
    return result


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
# out single-pixel noise from the motion-tracking union below without
# imposing the full MIN_SIGNIFICANT_CELLS size bar on it.
MIN_REAL_CELLS = 3


def _blob_centroid(alpha_mask: np.ndarray, cells: list[tuple[int, int]], cx: int, cy: int) -> tuple[float, float]:
    """Mean lat/lon over this blob's own occupied pixels — a far
    steadier position to track across frames than any single edge
    pixel, which shifts around as a storm's leading edge changes shape
    frame to frame even when its bulk hasn't actually moved much. Used
    by storm_motion below, where that steadiness is the whole point."""
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
    """This one frame's centroid (see _blob_centroid) of the UNION of
    every significant-sized blob (same MIN_SIGNIFICANT_CELLS bar the
    badges used to use), or every real-sized blob if none are
    significant — the whole nearby precipitation mass treated as one
    bulk system, not any single internal cell picked out of it.

    Confirmed live this distinction matters a lot for a large, sprawling
    multi-cell complex: picking just the LARGEST individual blob each
    frame measured bearing/speed off whichever cell happened to be
    biggest at that instant — different cells within the same complex
    at different times — producing a physically implausible ~230 km/h
    "speed" from jumping between them. The union's centroid instead
    tracks the bulk motion of the whole mass, which stayed smooth and
    physically reasonable (~65 km/h) on the same real data. For a
    single isolated storm cell this reduces to that one blob's own
    centroid anyway, so it doesn't change anything in the simpler
    case."""
    cx, cy = IMAGE_WIDTH // 2, IMAGE_HEIGHT // 2
    arr = np.array(img)
    alpha_mask = arr[:, :, 3] > ALPHA_THRESHOLD
    real_blobs = [b for b in _cluster_blobs(alpha_mask) if len(b) >= MIN_REAL_CELLS]
    if not real_blobs:
        return None
    significant = [b for b in real_blobs if len(b) >= MIN_SIGNIFICANT_CELLS]
    pool = significant or real_blobs
    merged_cells = [cell for blob in pool for cell in blob]
    return _blob_centroid(alpha_mask, merged_cells, cx, cy)


def _angle_diff_deg(a: float, b: float) -> float:
    """Smallest signed difference a-b between two compass bearings,
    wrapped to (-180, 180] — a naive subtraction is wrong near the
    0/360 seam (e.g. 350 vs 10 should read as 20 degrees apart, not
    340)."""
    return (a - b + 180) % 360 - 180


def storm_motion(kind: str) -> dict | None:
    """{"bearing_deg", "speed_kmh", "sample_count", "max_angular_error_deg"}
    measured directly from the real cached radar frames (see
    _frame_history, FRAME_HISTORY_SIZE) — the dominant tracked blob's
    own centroid in the oldest cached frame vs. the newest, over the
    real elapsed time between their own EC-reported valid times (not an
    assumed uniform cadence), a genuine measured displacement rather
    than a guess. Session request: "use this [the cached frames] to
    actually gauge storm direction instead of guessing." Purely
    descriptive of already-observed movement — see storm_motion_label,
    the only consumer — not a prediction of where the storm is headed.

    max_angular_error_deg checks every IN-BETWEEN consecutive frame
    pair too (not just the oldest-vs-newest endpoints that bearing_deg
    itself comes from) and reports the single largest disagreement
    between any one segment's own bearing and the overall bearing — 0
    for a storm tracking in a dead straight line, large for one that's
    curving, splitting, or being tracked erratically.

    None if fewer than 2 cached frames have a trackable blob at all
    (early in a fresh deploy/restart or right after switching kind,
    before _ensure_frame_history's backfill has completed), the two
    usable samples are less than MIN_TREND_GAP_MINUTES apart, or the
    measured displacement is under STATIONARY_THRESHOLD_KM (not moving
    meaningfully enough to trust a bearing from it)."""
    points = []
    for frame_time, raw in _frame_history[kind]:
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            continue
        centroid = _track_blob_for_motion(img)
        if centroid is not None:
            points.append((frame_time, centroid[0], centroid[1]))
    if len(points) < 2:
        return None

    old_t, old_lat, old_lon = points[0]
    new_t, new_lat, new_lon = points[-1]
    gap_minutes = (new_t - old_t).total_seconds() / 60
    if gap_minutes < MIN_TREND_GAP_MINUTES:
        return None
    moved_km = _distance_km(old_lat, old_lon, new_lat, new_lon)
    if moved_km < STATIONARY_THRESHOLD_KM:
        return None
    bearing_deg_ = _bearing_deg(old_lat, old_lon, new_lat, new_lon)

    max_angular_error_deg = 0.0
    for i in range(len(points) - 1):
        _, lat1, lon1 = points[i]
        _, lat2, lon2 = points[i + 1]
        if _distance_km(lat1, lon1, lat2, lon2) < STATIONARY_THRESHOLD_KM:
            continue
        segment_bearing = _bearing_deg(lat1, lon1, lat2, lon2)
        max_angular_error_deg = max(max_angular_error_deg, abs(_angle_diff_deg(segment_bearing, bearing_deg_)))

    return {
        "bearing_deg": bearing_deg_,
        "speed_kmh": moved_km / (gap_minutes / 60),
        "sample_count": len(points),
        "max_angular_error_deg": max_angular_error_deg,
    }


def storm_motion_label(kind: str = "rain") -> str | None:
    """A plain "Moving NE at 32 km/h" readout of the dominant tracked
    system's real measured motion (see storm_motion) — purely
    descriptive of already-observed movement, not a prediction of
    whether or when it'll reach the user's own location; reading the
    radar map itself alongside this is how that call gets made now.
    None whenever storm_motion itself has nothing to report yet."""
    motion = storm_motion(kind)
    if motion is None:
        return None
    return f"Moving {compass_abbr(motion['bearing_deg'])} at {motion['speed_kmh']:.0f} km/h"


def nearby_city_markers() -> list[dict]:
    """Neutral reference points for real nearby towns (see config.
    RADAR_NEARBY_CITIES), as 0-100 percentage positions matching how
    the fixed location marker is already positioned — so it's obvious
    where precipitation on the map actually is relative to real places,
    not just relative to Corbeil's own marker. Purely local pixel math,
    no fetch — any city that happens to fall outside the image's own
    bbox is silently dropped rather than shown clipped at the edge, so
    RADAR_NEARBY_CITIES doesn't need to stay hand-tuned to
    BBOX_MARGIN_DEGREES_LAT/LON."""
    markers = []
    for city in RADAR_NEARBY_CITIES:
        px, py = _latlon_to_pixel(city["lat"], city["lon"])
        if 0 <= px < IMAGE_WIDTH and 0 <= py < IMAGE_HEIGHT:
            markers.append({"label": city["label"], "x_pct": px / IMAGE_WIDTH * 100, "y_pct": py / IMAGE_HEIGHT * 100})
    return markers
