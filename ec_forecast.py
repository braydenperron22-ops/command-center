"""Environment Canada's own official forecast — the "Rain/Snow in Xh"
nowcast badge (hourly probability of precipitation) and the Weather
page's 7-day outlook both come from here. Swapped in after Open-Meteo's
generic global model blend disagreed with both EC's official forecast
and what was actually observed (Open-Meteo showed ~25% for a morning EC
had at 60% with thunderstorm risk). EC's own numbers are the
authoritative source for a Canadian location, and using EC's hourly +
daily data together keeps them internally consistent with each other,
unlike mixing providers.

Accessed via MSC GeoMet's OGC API (api.weather.gc.ca) — a single JSON
request keyed by a small bounding box around the site, mirroring the
same citypage_weather data that drives weather.gc.ca itself (both the
hourly and the 7-day forecast come back in that one response), without
needing to crawl the raw MSC datamart's date/hour directory structure
(which has no stable "latest" filename — every file is timestamped and
only discoverable by listing directories) to get the same information.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

import fetch_throttle
from config import RAIN_LOOKAHEAD_HOURS, RAIN_PROBABILITY_THRESHOLD, TIMEZONE

_PERCENT_CHANCE_RE = re.compile(r"(\d+)\s*percent chance")

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
# condition text itself.
_SNOW_TERMS = ("snow", "flurr", "ice pellet", "hail")
_STORM_TERMS = ("thunderstorm", "storm")
_RAIN_TERMS = ("rain", "shower", "drizzle")
_FOG_TERMS = ("fog", "mist")
_CLEAR_TERMS = ("sunny", "clear")

_last_good_properties: dict | None = None


def _classify_precip(condition_text: str) -> str:
    text = condition_text.lower()
    return "snow" if any(term in text for term in _SNOW_TERMS) else "rain"


def _classify_category(condition_text: str) -> str:
    """Same six buckets scenery.condition_category uses (for icons.
    icon_for), read from EC's own condition wording instead of a WMO
    code — EC doesn't expose one."""
    text = condition_text.lower()
    if any(term in text for term in _STORM_TERMS):
        return "storm"
    if any(term in text for term in _SNOW_TERMS):
        return "snow"
    if any(term in text for term in _RAIN_TERMS):
        return "rain"
    if any(term in text for term in _FOG_TERMS):
        return "fog"
    if any(term in text for term in _CLEAR_TERMS):
        return "clear"
    return "cloudy"


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_properties_raw() -> dict | None:
    bbox = (
        EC_STATION_LON - BBOX_MARGIN_DEGREES, EC_STATION_LAT - BBOX_MARGIN_DEGREES,
        EC_STATION_LON + BBOX_MARGIN_DEGREES, EC_STATION_LAT + BBOX_MARGIN_DEGREES,
    )
    fetch_throttle.wait_turn()
    resp = requests.get(GEOMET_URL, params={"bbox": ",".join(str(v) for v in bbox), "f": "json"}, timeout=10)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    return features[0]["properties"] if features else None


def _fetch_properties() -> dict | None:
    global _last_good_properties
    try:
        result = _fetch_properties_raw()
    except Exception:
        return _last_good_properties
    if result is not None:
        _last_good_properties = result
    return result if result is not None else _last_good_properties


def _fetch_hourly() -> list[dict]:
    properties = _fetch_properties()
    if not properties:
        return []
    hourly = []
    for f in properties.get("hourlyForecastGroup", {}).get("hourlyForecasts", []):
        lop = f.get("lop", {}).get("value", {}).get("en")
        condition = f.get("condition", {}).get("en", "")
        timestamp = f.get("timestamp")
        if lop is None or not timestamp:
            continue
        at_utc = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        at_local = at_utc.astimezone(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
        hourly.append({"at": at_local, "probability": lop, "kind": _classify_precip(condition)})
    return hourly


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


def _temp_value(temps: list[dict], cls: str) -> int | None:
    for t in temps:
        if t.get("class", {}).get("en") == cls:
            return t["value"]["en"]
    return None


def _percent_chance(long_summary: str) -> int | None:
    """EC's structured `pop` field isn't exposed in this JSON collection
    (only the raw XML has it) — but the long textSummary always spells
    out "NN percent chance of ..." in prose when there's a real chance,
    so this reads it from there instead of a second data source."""
    match = _PERCENT_CHANCE_RE.search(long_summary)
    return int(match.group(1)) if match else None


def _period_detail(p: dict) -> dict:
    """Everything worth showing for one EC forecast period (day or
    night): short + long summary, precip chance, wind, UV. Shared by
    both halves of a daily_forecast() row."""
    long_summary = p.get("textSummary", {}).get("en", "")
    uv_index = p.get("uv", {}).get("index", {}).get("en")
    return {
        "summary": p.get("abbreviatedForecast", {}).get("textSummary", {}).get("en", ""),
        "precip_chance": _percent_chance(long_summary),
        "wind": p.get("winds", {}).get("textSummary", {}).get("en", ""),
        "uv_index": int(uv_index) if uv_index is not None else None,
    }


def daily_forecast() -> list[dict]:
    """Up to ~7 days ahead, EC's own forecast — one entry per calendar
    day: {"name", "high", "low", "category", "day": {...}, "night":
    {...}|None}, where each period dict is _period_detail's shape
    (summary/precip_chance/wind/uv_index). EC publishes separate day/
    night periods (e.g. "Tuesday" + "Tuesday night"); this pairs each
    day with its following night to get one row with both halves' real
    detail available, not just a single blended icon. The very first
    entry is just "Today" (whatever's left of it) and the very last one
    can be day-only if EC hasn't published that night's period yet."""
    properties = _fetch_properties()
    if not properties:
        return []
    periods = properties.get("forecastGroup", {}).get("forecasts", [])

    days = []
    i = 0
    while i < len(periods):
        p = periods[i]
        temps = p.get("temperatures", {}).get("temperature", [])
        name = p.get("period", {}).get("textForecastName", {}).get("en", "")
        is_night = _temp_value(temps, "low") is not None and _temp_value(temps, "high") is None

        if is_night:
            # A lone leading/orphaned night period with no day to pair
            # it with — still shown rather than silently dropped.
            detail = _period_detail(p)
            days.append({
                "name": name, "high": None, "low": _temp_value(temps, "low"),
                "category": _classify_category(detail["summary"]), "day": None, "night": detail,
            })
            i += 1
            continue

        high = _temp_value(temps, "high")
        low = None
        day_detail = _period_detail(p)
        night_detail = None
        next_p = periods[i + 1] if i + 1 < len(periods) else None
        if next_p:
            next_temps = next_p.get("temperatures", {}).get("temperature", [])
            if _temp_value(next_temps, "low") is not None:
                low = _temp_value(next_temps, "low")
                night_detail = _period_detail(next_p)
                i += 1  # consume the paired night period too

        days.append({
            "name": name, "high": high, "low": low,
            "category": _classify_category(day_detail["summary"]), "day": day_detail, "night": night_detail,
        })
        i += 1

    return days


def current_conditions() -> dict | None:
    """EC's own live station reading (North Bay Airport, not the
    Corbeil point weather_client/Open-Meteo reports for) — condition,
    humidity, wind, pressure, dewpoint. Distinct from the hero row's
    temperature, and worth showing on this page since it's specifically
    about EC's own numbers rather than the app's usual Open-Meteo feed."""
    properties = _fetch_properties()
    if not properties:
        return None
    cc = properties.get("currentConditions", {})
    temp = cc.get("temperature", {}).get("value", {}).get("en")
    if temp is None:
        return None
    condition = cc.get("condition", {}).get("en", "")
    return {
        "temp_c": temp,
        "condition": condition,
        "category": _classify_category(condition),
        "humidity": cc.get("relativeHumidity", {}).get("value", {}).get("en"),
        "wind_speed": cc.get("wind", {}).get("speed", {}).get("value", {}).get("en"),
        "wind_gust": cc.get("wind", {}).get("gust", {}).get("value", {}).get("en"),
        "wind_dir": cc.get("wind", {}).get("direction", {}).get("value", {}).get("en"),
        "pressure_kpa": cc.get("pressure", {}).get("value", {}).get("en"),
        "pressure_tendency": cc.get("pressure", {}).get("tendency", {}).get("en"),
        "dewpoint_c": cc.get("dewpoint", {}).get("value", {}).get("en"),
        "station": cc.get("station", {}).get("value", {}).get("en", ""),
    }
