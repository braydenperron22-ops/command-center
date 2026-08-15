"""Animated radar via RainViewer — session request: "get another
source... provides animated radar because I don't know, I don't
really like Environment Canada's radar at all," followed by "reinstate
the radar page. Use RainViewer."

Checked live before switching sources: RainViewer's own Canadian
coverage is Environment Canada's own radar network, re-served (see
rainviewer.com/sources.html) — there's no genuinely more ACCURATE
source available for this location, just a nicer-looking, better-
animated presentation of the exact same underlying observations. Free,
no API key or registration at all (unlike lightning_client.py's
Xweather) — a separate service with its own free terms, so this
doesn't compete with that budget either.

Frames are handed back as real, directly browser-fetched image URLs
(RainViewer's own lat/lon-centered tile endpoint) — never proxied
through this app's own server or embedded as a data: URI. This app's
own prior Radar page (see git log: 100fddd and its ancestors) already
found that mistake the hard way — a server-embedded base64 GIF resent
on every 5s rerun was multi-megabyte and visibly laggy. A plain
<img src="https://..."> lets the browser fetch/cache each frame once,
completely outside Streamlit's own rerun cycle — pages_radar.py's own
frame-cycling animation just toggles which already-loaded image is
visible, it never re-fetches anything itself.
"""

import requests
import streamlit as st

from config import WEATHER_LAT, WEATHER_LON

MAPS_JSON_URL = "https://api.rainviewer.com/public/weather-maps.json"
# RainViewer's own real-world cadence is 10-minute intervals — no
# freshness gained by polling faster than that.
CACHE_TTL_SECONDS = 3 * 60

TILE_SIZE = 512  # the larger of RainViewer's two fixed sizes (256/512)
# RainViewer's own max is 7 (tightest). One step back for a wider,
# more useful "watch it approach" view of the region around Corbeil
# rather than the tightest possible crop — same reasoning the old EC
# radar page's own wide bbox already established, just expressed as a
# zoom level instead of a bbox margin.
ZOOM = 6
COLOR_SCHEME = 2  # RainViewer's own "Universal Blue" default scheme
SMOOTH = 1
SHOW_SNOW = 1
# ~2 hours of real history at RainViewer's 10-minute cadence — matches
# the old EC radar loop's own "last several real pulls" framing.
FRAME_COUNT = 12


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_maps_json() -> dict | None:
    resp = requests.get(MAPS_JSON_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def frame_urls() -> list[str]:
    """The most recent FRAME_COUNT real radar frames, oldest first, as
    real RainViewer CDN URLs already centered exactly on WEATHER_LAT/
    WEATHER_LON (RainViewer's own lat/lon tile endpoint, not raw x/y/z
    slippy-tile math) — [] if the feed is unreachable or genuinely
    empty. Always dead-centered on the same point regardless of frame,
    so pages_radar.py's "you are here" marker never needs its own per-
    frame pixel math — same principle the old EC radar page's own
    symmetric bbox already established, just via RainViewer's endpoint
    shape instead."""
    try:
        data = _fetch_maps_json()
    except Exception:
        return []
    if not data:
        return []
    host = data.get("host")
    past = (data.get("radar") or {}).get("past") or []
    if not host or not past:
        return []
    recent = past[-FRAME_COUNT:]
    options = f"{SMOOTH}_{SHOW_SNOW}"
    return [
        f"{host}{frame['path']}/{TILE_SIZE}/{ZOOM}/{WEATHER_LAT}/{WEATHER_LON}/{COLOR_SCHEME}/{options}.png"
        for frame in recent
        if frame.get("path")
    ]
