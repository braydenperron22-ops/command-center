"""Live weather radar imagery — the same raw signal (real-time
precipitation reflectivity, not a forecast model) that minute-by-minute
nowcasting apps like Apple Weather/Dark Sky are actually built on top
of. Their edge is a proprietary storm-tracking algorithm layered over
that signal, which isn't something to reasonably reimplement here — but
seeing the live radar directly is most of the real value on its own,
and it's public data.

Environment Canada's own 1km North American radar composite (rain and
snow separately, updated every 6 minutes) is served as a standard OGC
WMS map layer via MSC GeoMet — this just builds the image URL; there's
no server-side fetch or JSON to parse, since the browser (not our own
backend) requests the image directly, the same way any <img> tag works.
No fetch_throttle needed for the same reason: that system only guards
our own outbound API calls during script execution.
"""

import time

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


def radar_image_url(kind: str = "rain") -> str:
    layer = SNOW_LAYER if kind == "snow" else RAIN_LAYER
    bbox = (
        f"{WEATHER_LAT - BBOX_MARGIN_DEGREES},{WEATHER_LON - BBOX_MARGIN_DEGREES},"
        f"{WEATHER_LAT + BBOX_MARGIN_DEGREES},{WEATHER_LON + BBOX_MARGIN_DEGREES}"
    )
    # Rounded to REFRESH_SECONDS rather than a raw timestamp — busts the
    # browser's image cache exactly when a new radar frame is actually
    # available, not on every single page rerun (which would force a
    # full-size image refetch every 5s for no reason).
    cache_bust = int(time.time() // REFRESH_SECONDS)
    return (
        f"{WMS_URL}?service=WMS&version=1.3.0&request=GetMap&layers={layer}"
        f"&format=image/png&transparent=true&width={IMAGE_SIZE}&height={IMAGE_SIZE}"
        f"&crs=EPSG:4326&bbox={bbox}&_t={cache_bust}"
    )
