"""Open-Meteo access for the North Bay, ON current conditions + solar
times, plus (session request: "I think Open-Meteo is a little more
accurate... I wanna start using it as our main provider... is there a
way to make Open-Meteo bulletproof") the hourly and 7-day forecasts —
previously EC-only (see ec_forecast.py's own docstring for why EC was
chosen there in the first place: its official numbers beat Open-Meteo's
generic global blend for one specific real thunderstorm morning). Both
readings stay real options rather than picking one and deleting the
other — hourly_forecast()/daily_forecast() below try Open-Meteo first
and fall back to ec_forecast's own equivalent on any failure, same
"two independent free providers" resilience shape fetch_weather()
itself already has for current conditions. The one piece deliberately
NOT switched: next_precip_at's own rain-probability reading below stays
EC-sourced specifically, because that's the one exact case with a real,
observed instance of Open-Meteo being wrong (see fetch_weather()'s own
comment) — everything else here didn't have that history against it.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from astral import LocationInfo
from astral.sun import sun

import data_health
import ec_forecast
import fetch_throttle
import scenery
from config import TIMEZONE, WEATHER_LAT, WEATHER_LON
from icons import label_for

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo has no civil-twilight variable (only the sunrise/sunset disk
# crossing), so first/last light are computed locally instead — astral's
# `sun()` gives dawn/dusk at the standard 6° civil-twilight depression by
# default, no API call needed. Cross-checked against a real forecast (July
# 2026, North Bay): computed dawn/dusk landed within a minute of the
# figures actually observed for that day.
_LOCATION = LocationInfo(latitude=WEATHER_LAT, longitude=WEATHER_LON, timezone=TIMEZONE)


def _first_last_light(day: date) -> tuple[datetime, datetime]:
    s = sun(_LOCATION.observer, date=day, tzinfo=ZoneInfo(TIMEZONE))
    return s["dawn"].replace(tzinfo=None), s["dusk"].replace(tzinfo=None)

# This is called unconditionally at the very top of app.py, before any
# page renders — an uncaught exception here used to take down the entire
# app (background, clock, every page), not just the weather widget. Falls
# back to the last successfully fetched reading rather than raising.
_last_good_weather: dict | None = None

# Confirmed live: Open-Meteo can fail to respond to this app's host for
# 20+ minutes straight (health checks on the app itself stayed green the
# whole time, and Open-Meteo answered instantly from every other vantage
# point tried — so not a global outage, just unreachable from here) with
# nothing cached yet to fall back on right after a fresh redeploy resets
# _last_good_weather. EC's own live station reading is a real second
# source rather than showing nothing — already a dependency of this app
# (ec_forecast.py, used elsewhere on the Weather/Hourly pages), not a new
# vendor. Its own condition wording already collapses to the same six
# scenery.condition_category buckets Open-Meteo's numeric code does (see
# ec_forecast._classify_category), so this just picks one representative
# code per bucket rather than needing a real WMO code from EC (which it
# doesn't expose).
_EC_CATEGORY_TO_WMO_CODE = {
    "clear": 0, "cloudy": 2, "fog": 45, "rain": 61, "snow": 71, "storm": 95,
}


def _fallback_from_ec() -> dict | None:
    """Same dict shape fetch_weather() normally returns, built from EC's
    live station reading instead of Open-Meteo. UV index and the day's
    forecast high/low aren't in EC's current-conditions reading, so
    those stay None — every caller already treats them as optional
    (weather.get(...)), same as a normal reading that simply doesn't
    have them yet. Sunrise/sunset/twilight come from astral either way
    (no API call in either path), so those are exactly as accurate as
    the normal path's."""
    cc = ec_forecast.current_conditions()
    if cc is None:
        return None
    now_local = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    s = sun(_LOCATION.observer, date=now_local.date(), tzinfo=ZoneInfo(TIMEZONE))
    sunrise, sunset = s["sunrise"].replace(tzinfo=None), s["sunset"].replace(tzinfo=None)
    first_light, last_light = s["dawn"].replace(tzinfo=None), s["dusk"].replace(tzinfo=None)
    precip = ec_forecast.next_precip_at(now_local)
    return {
        "temp_c": cc["temp_c"],
        "feels_like_c": None,
        "weather_code": _EC_CATEGORY_TO_WMO_CODE.get(cc["category"], 2),
        "uv_index": None,
        "sunrise": sunrise,
        "sunset": sunset,
        "first_light": first_light,
        "last_light": last_light,
        "rain_at": precip[0] if precip else None,
        "precip_kind": precip[1] if precip else None,
        "precip_chance": precip[2] if precip else None,
        "forecast_high_c": None,
        "forecast_low_c": None,
    }


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _fetch_weather_raw() -> dict | None:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "current": "temperature_2m,apparent_temperature,weather_code,uv_index",
        "daily": "sunrise,sunset,temperature_2m_max,temperature_2m_min",
        "temperature_unit": "celsius",
        "timezone": TIMEZONE,
        "forecast_days": 2,
    }
    fetch_throttle.wait_turn()
    resp = requests.get(WEATHER_URL, params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    current = body.get("current", {})
    daily = body.get("daily", {})
    if "temperature_2m" not in current or not daily.get("sunrise"):
        return None

    # Open-Meteo returns these already in the requested local timezone
    # (naive, no offset), which matches the naive Toronto-pinned clock
    # used elsewhere in the app.
    sunrise = datetime.fromisoformat(daily["sunrise"][0])
    sunset = datetime.fromisoformat(daily["sunset"][0])
    first_light, last_light = _first_last_light(sunrise.date())
    # Environment Canada's own forecast, not Open-Meteo's — see
    # ec_forecast.py for why (EC's official numbers disagreed with
    # Open-Meteo's generic global blend for this exact location).
    precip = ec_forecast.next_precip_at(datetime.fromisoformat(current["time"]))

    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []

    return {
        "temp_c": current["temperature_2m"],
        "feels_like_c": current.get("apparent_temperature"),
        "weather_code": current.get("weather_code", 0),
        "uv_index": current.get("uv_index"),
        "sunrise": sunrise,
        "sunset": sunset,
        "first_light": first_light,
        "last_light": last_light,
        "rain_at": precip[0] if precip else None,
        "precip_kind": precip[1] if precip else None,
        "precip_chance": precip[2] if precip else None,
        "forecast_high_c": highs[0] if highs else None,
        "forecast_low_c": lows[0] if lows else None,
    }


def fetch_weather() -> dict | None:
    global _last_good_weather
    try:
        result = _fetch_weather_raw()
    except (requests.RequestException, ValueError, KeyError):
        result = None
    if result is not None:
        _last_good_weather = result
        data_health.record_success("weather")
        return result
    if _last_good_weather is not None:
        return _last_good_weather
    # Nothing live and nothing cached yet — see _fallback_from_ec. Not
    # stored into _last_good_weather: that name means "last known-good
    # Open-Meteo reading" elsewhere (morning_briefing and others treat
    # it as such), and every rerun should keep trying the real fetch via
    # its own cache_data TTL rather than resting on an EC-sourced
    # approximation once it exists.
    try:
        result = _fallback_from_ec()
    except Exception:
        return None
    if result is not None:
        data_health.record_success("weather")
    return result


_WIND_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _compass_abbr(degrees: float) -> str:
    """Open-Meteo gives wind direction as a plain compass bearing (e.g.
    237), not a pre-abbreviated string the way EC's own feed does — this
    is the whole conversion, a fixed 16-point rose."""
    return _WIND_COMPASS[round(degrees / 22.5) % 16]


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _fetch_hourly_raw() -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(
        WEATHER_URL,
        params={
            "latitude": WEATHER_LAT, "longitude": WEATHER_LON,
            "hourly": "temperature_2m,weather_code,precipitation_probability,wind_speed_10m,wind_direction_10m",
            "temperature_unit": "celsius", "wind_speed_unit": "kmh",
            "timezone": TIMEZONE, "forecast_days": 2,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def hourly_forecast() -> list[dict]:
    """Same shape ec_forecast.hourly_forecast() returns ({"at", "temp_c",
    "condition", "category", "precip_chance", "wind_speed", "wind_dir"},
    soonest first) — session request: "I wanna start using [Open-Meteo]
    as our main provider... is there a way to make [it] bulletproof."
    Open-Meteo's own hourly array always starts at today's midnight
    (confirmed live), not "now," so this filters down to the current
    hour onward itself rather than assuming the caller wants the whole
    48-hour block. Falls back to ec_forecast's own hourly reading on any
    failure — a second, independent, equally free/keyless provider
    behind this one, not a single point of failure for this page."""
    try:
        data = _fetch_hourly_raw()
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            raise ValueError("no hourly data in Open-Meteo response")
        now_hour = datetime.now(ZoneInfo(TIMEZONE)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
        result = []
        for i, t in enumerate(times):
            at = datetime.fromisoformat(t)
            if at < now_hour:
                continue
            code = hourly["weather_code"][i]
            result.append({
                "at": at,
                "temp_c": hourly["temperature_2m"][i],
                "condition": label_for(code),
                "category": scenery.condition_category(code),
                "precip_chance": hourly["precipitation_probability"][i],
                "wind_speed": round(hourly["wind_speed_10m"][i]),
                "wind_dir": _compass_abbr(hourly["wind_direction_10m"][i]),
            })
        if not result:
            raise ValueError("Open-Meteo hourly data was entirely in the past")
        return result
    except Exception:
        return ec_forecast.hourly_forecast()


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _fetch_daily_raw() -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(
        WEATHER_URL,
        params={
            "latitude": WEATHER_LAT, "longitude": WEATHER_LON,
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,wind_speed_10m_max,"
                "wind_direction_10m_dominant,uv_index_max"
            ),
            "temperature_unit": "celsius", "wind_speed_unit": "kmh",
            "timezone": TIMEZONE, "forecast_days": 7,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _normalize_ec_daily(ec_days: list[dict]) -> list[dict]:
    """Flattens ec_forecast.daily_forecast()'s own day/night-paired shape
    down to the same one-reading-per-day shape the Open-Meteo path above
    produces — so pages_weather.py has exactly one render path to
    maintain regardless of which provider actually answered, rather than
    needing to know both providers' native shapes. Prefers the day
    period's own detail (a lone leading night period, night is None,
    falls back to night's own detail instead — see ec_forecast.
    daily_forecast's own docstring on when that happens). precip_chance
    is the higher of day/night's own reading when both are present (the
    same "worth mentioning at all today" question a flat single-value
    card is actually asking), not an average that could hide a real
    night-only shower behind a dry day."""
    result = []
    for d in ec_days:
        primary = d["day"] or d["night"] or {}
        secondary = d["night"] if d["day"] else None
        chances = [x["precip_chance"] for x in (primary, secondary) if x and x.get("precip_chance") is not None]
        result.append({
            "name": d["name"],
            "high": d["high"],
            "low": d["low"],
            "category": d["category"],
            "condition": primary.get("summary") or "",
            "precip_chance": max(chances) if chances else None,
            "wind": primary.get("wind") or "",
            "uv_index": primary.get("uv_index"),
        })
    return result


def daily_forecast() -> list[dict]:
    """Up to 7 days ahead — {"name", "high", "low", "category",
    "condition", "precip_chance", "wind", "uv_index"} per day, today
    first. Deliberately one reading per day, not ec_forecast.
    daily_forecast()'s own day/night pair — Open-Meteo's daily endpoint
    doesn't carry that finer split at all (a genuine difference in what
    each provider publishes, not a gap in this parsing). Falls back to
    ec_forecast's own daily_forecast() on any failure, same "second
    independent provider" resilience hourly_forecast() above has —
    _normalize_ec_daily flattens that fallback down to this exact same
    shape so pages_weather.py only ever has one card layout to render,
    regardless of which provider actually answered."""
    try:
        data = _fetch_daily_raw()
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        if not times:
            raise ValueError("no daily data in Open-Meteo response")
        today = datetime.now(ZoneInfo(TIMEZONE)).date()
        result = []
        for i, t in enumerate(times):
            day = date.fromisoformat(t)
            code = daily["weather_code"][i]
            name = "Today" if day == today else day.strftime("%A")
            wind_speed = round(daily["wind_speed_10m_max"][i])
            wind_dir = _compass_abbr(daily["wind_direction_10m_dominant"][i])
            uv = daily["uv_index_max"][i]
            result.append({
                "name": name,
                "high": round(daily["temperature_2m_max"][i]),
                "low": round(daily["temperature_2m_min"][i]),
                "category": scenery.condition_category(code),
                "condition": label_for(code),
                "precip_chance": daily["precipitation_probability_max"][i],
                "wind": f"{wind_dir} {wind_speed} km/h",
                "uv_index": round(uv) if uv is not None else None,
            })
        return result
    except Exception:
        return _normalize_ec_daily(ec_forecast.daily_forecast())
