"""Environment Canada's own official forecast (probability of
precipitation, hour by hour) for the "Rain/Snow in Xh" nowcast badge —
swapped in after Open-Meteo's generic global model blend disagreed with
both EC's official forecast and what was actually observed (Open-Meteo
showed ~25% for a morning EC had at 60% with thunderstorm risk). EC's
own numbers are the authoritative source for a Canadian location, and
using EC's hourly + text-summary data together keeps them internally
consistent with each other, unlike mixing providers.

Accessed via MSC GeoMet's OGC API (api.weather.gc.ca) — a single JSON
request keyed by a small bounding box around the site, mirroring the
same citypage_weather data that drives weather.gc.ca itself, without
needing to crawl the raw MSC datamart's date/hour directory structure
(which has no stable "latest" filename — every file is timestamped and
only discoverable by listing directories) to get the same information.
"""

from datetime import datetime

import requests
import streamlit as st

import fetch_throttle
from config import RAIN_LOOKAHEAD_HOURS, RAIN_PROBABILITY_THRESHOLD, TIMEZONE
from zoneinfo import ZoneInfo

GEOMET_URL = "https://api.weather.gc.ca/collections/citypageweather-realtime/items"
# EC's own North Bay station (site code s0000765, from their public
# site_list_en.geojson) — deliberately NOT config.py's WEATHER_LAT/
# WEATHER_LON. Those pin the precise "Corbeil" point Open-Meteo forecasts
# for, ~13km from EC's actual station; a tight bbox around the Corbeil
# point missed EC's station entirely and silently returned zero features.
EC_STATION_LAT = 46.31
EC_STATION_LON = -79.46
# A small box around the station rather than an exact-match filter —
# the collection has no documented site-code query field, but every
# site is a single point, so a tight box around it returns exactly one
# feature.
BBOX_MARGIN_DEGREES = 0.1
CACHE_TTL_SECONDS = 15 * 60

# EC's iconCode is its own numbering scheme, not the WMO codes
# scenery.py already classifies — simplest reliable read is the
# condition text itself, which always says "snow"/"flurries"/"ice
# pellets" for winter precip and "rain"/"showers"/"drizzle" for the
# rest (thunderstorms count as rain here, same as scenery.py's WMO
# ranges do).
_SNOW_TERMS = ("snow", "flurr", "ice pellet", "hail")

_last_good_hourly: list[dict] | None = None


def _classify(condition_text: str) -> str:
    text = condition_text.lower()
    return "snow" if any(term in text for term in _SNOW_TERMS) else "rain"


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_hourly_raw() -> list[dict]:
    bbox = (
        EC_STATION_LON - BBOX_MARGIN_DEGREES, EC_STATION_LAT - BBOX_MARGIN_DEGREES,
        EC_STATION_LON + BBOX_MARGIN_DEGREES, EC_STATION_LAT + BBOX_MARGIN_DEGREES,
    )
    fetch_throttle.wait_turn()
    resp = requests.get(GEOMET_URL, params={"bbox": ",".join(str(v) for v in bbox), "f": "json"}, timeout=10)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return []
    forecasts = features[0]["properties"]["hourlyForecastGroup"]["hourlyForecasts"]
    hourly = []
    for f in forecasts:
        lop = f.get("lop", {}).get("value", {}).get("en")
        condition = f.get("condition", {}).get("en", "")
        timestamp = f.get("timestamp")
        if lop is None or not timestamp:
            continue
        at_utc = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        at_local = at_utc.astimezone(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
        hourly.append({"at": at_local, "probability": lop, "kind": _classify(condition)})
    return hourly


def _fetch_hourly() -> list[dict]:
    global _last_good_hourly
    try:
        result = _fetch_hourly_raw()
    except Exception:
        return _last_good_hourly or []
    if result:
        _last_good_hourly = result
    return result or (_last_good_hourly or [])


def next_precip_at(now: datetime) -> tuple[datetime, str] | None:
    """(timestamp, "rain" or "snow") for the next hour EC's own forecast
    gives a real chance of precipitation within the lookahead window —
    same shape/contract as weather_client's old Open-Meteo-based
    version, so app.py's badge logic didn't need to change, just its
    data source."""
    for reading in _fetch_hourly():
        hours_away = (reading["at"] - now).total_seconds() / 3600
        if hours_away < 0 or hours_away > RAIN_LOOKAHEAD_HOURS:
            continue
        if reading["probability"] >= RAIN_PROBABILITY_THRESHOLD:
            return reading["at"], reading["kind"]
    return None
