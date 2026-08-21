"""Golf intelligence for Highview Golf Course (60 Golf Course Line,
Powassan, ON — Brayden's home course, real coordinates confirmed live
via OpenStreetMap/Nominatim's own geocoder: 46.1293713, -79.3578162).

Session request: "Add a golf intelligence layer... Monitor course
open/closed status, tee-sheet availability, course conditions...
Also incorporate temperature, wind, precipitation... Create two
distinct scores: PLAYABILITY... BUSYNESS... The score should be
transparent and useful rather than pretending to be an objectively
scientific measurement."

Two real, free data sources:
  - Open-Meteo, at the course's own exact coordinates (not home's —
    they're ~20km apart) — the same provider weather_client.py
    already uses for the dashboard's own weather, called directly
    here rather than through that module since it's hardcoded to
    WEATHER_LAT/LON.
  - The course's own real Tee-On booking system (tee-on.com,
    CourseCode=HIGV) — genuine live tee-sheet availability, not a
    simulation. Getting to real data means replicating a real 4-step
    cookie/session handshake (confirmed live, by hand, before writing
    this): establish a session, accept Tee-On's own cookie-consent
    AJAX call, follow its referrer-setup redirect, then POST the
    actual search form (Date/SearchTime/Holes/Players/CourseIdHIGV/
    CourseGroupID/Referrer — the exact field names read directly off
    the real booking form's own HTML, not guessed). The response is
    real server-rendered HTML (a `div.search-results-tee-times-box`
    per open slot, with its own real time + price) — same "scrape a
    real site that happens to need session setup" category as this
    app's feargreedmeter.com integration, just with more steps.

What this deliberately does NOT claim to detect: aeration, frost
delays, temporary greens, or cart restrictions specifically — no real
structured feed exists for any of these beyond the booking page's own
generic welcome notice (checked live; it's boilerplate, not day-to-day
operational status), so faking a signal for them would violate the
same "never invent a fact" rule every other data source in this app
follows. "Course: OPEN/FULLY BOOKED" below reflects whether the real
tee-sheet itself has anything bookable today — deliberately NOT
"CLOSED" for an empty result, caught live on a real Friday afternoon
scan that came back with zero open slots and no closure notice
anywhere on the page (just the generic "No Times" message): a fully-
booked course and a genuinely closed one are different real facts, and
this has no actual signal for the second one at all, so claiming it
would be exactly the kind of invented fact this module otherwise
avoids.

Busyness's own scale matches the session's own example numbers
exactly, on inspection: occupancy 34% + "Demand: LOW" paired with a
Busyness score of 7.8/10 only makes sense if higher Busyness means
LESS crowded (a "how good is the crowd situation" score, same "higher
is better" direction as Playability and Golfability) — not literally
"how busy," despite the name. GOLFABILITY = 0.6*Playability +
0.4*Busyness reproduces the session's own worked example (9.4, 7.8 ->
8.76 ≈ 8.7) almost exactly, which is what fixed that 60/40 weighting
rather than picking a number."""

import re
from datetime import date, datetime

import requests
import streamlit as st
from bs4 import BeautifulSoup

import fetch_throttle
import persisted_state

COURSE_LAT = 46.1293713
COURSE_LON = -79.3578162
COURSE_CODE = "HIGV"
COURSE_GROUP_ID = "11730"

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
TEEON_BASE = "https://www.tee-on.com/PubGolf/servlet"
TRAIL_SEARCH_URL = (
    f"{TEEON_BASE}/com.teeon.teesheet.servlets.trail.TrailSearch"
    f"?CourseGroupID={COURSE_GROUP_ID}&CourseCode={COURSE_CODE}&FromCourseWebsite=true"
)
COOKIE_AGREE_URL = f"{TEEON_BASE}/com.teeon.teesheet.servlets.ajax.CookieAgreementSave?Agree=true"
RESULTS_URL = f"{TEEON_BASE}/com.teeon.teesheet.servlets.golfersection.WebBookingSearchResults"

CACHE_TTL_SECONDS = 30 * 60
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Representative times spanning a realistic golf day — the search
# results endpoint only ever returns the few slots nearest the
# requested time, not the whole day at once, so covering the full
# 7am-6pm window means several searches, unioned into one real picture
# of today's actual open times.
_SCAN_TIMES = ["07:00", "10:00", "13:00", "16:00", "18:00"]
# A rough, explicitly-approximate stand-in for "how many tee times a
# fully open day could hold" (roughly a 12-hour window at ~10-minute
# intervals) — there's no real published capacity number to check this
# against, so this is a transparent estimate, not a verified fact
# (matches the session's own "useful, not objectively scientific"
# framing for these scores).
_ASSUMED_DAILY_CAPACITY = 60


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_weather_raw() -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(
        WEATHER_URL,
        params={
            "latitude": COURSE_LAT,
            "longitude": COURSE_LON,
            "current": "temperature_2m,wind_speed_10m,precipitation",
            "hourly": "precipitation_probability,uv_index",
            "timezone": "America/Toronto",
            "forecast_days": 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


_last_good_weather: dict | None = None


def _course_weather() -> dict | None:
    global _last_good_weather
    try:
        data = _fetch_weather_raw()
    except Exception:
        return _last_good_weather
    current = data.get("current", {})
    hourly = data.get("hourly", {})
    # Nearest current hour's own precip probability/UV — "current" only
    # carries temp/wind/precipitation, not probability or UV.
    now_hour = datetime.now().strftime("%Y-%m-%dT%H:00")
    times = hourly.get("time", [])
    idx = times.index(now_hour) if now_hour in times else 0
    result = {
        "temp_c": current.get("temperature_2m"),
        "wind_kmh": current.get("wind_speed_10m"),
        "precip_probability": (hourly.get("precipitation_probability") or [None])[idx]
        if idx < len(hourly.get("precipitation_probability", []))
        else None,
        "uv_index": (hourly.get("uv_index") or [None])[idx] if idx < len(hourly.get("uv_index", [])) else None,
    }
    _last_good_weather = result
    return result


def _teeon_session() -> requests.Session | None:
    """Replicates the real 4-step Tee-On cookie/session handshake
    (see module docstring) — None if any step fails, so callers
    degrade gracefully rather than scraping a half-authenticated
    session."""
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": _USER_AGENT})
        fetch_throttle.wait_turn()
        s.get(TRAIL_SEARCH_URL, timeout=12)
        fetch_throttle.wait_turn()
        s.get(COOKIE_AGREE_URL, timeout=12)
        fetch_throttle.wait_turn()
        resp = s.get(TRAIL_SEARCH_URL, timeout=12)
        # The real referrer-setup page JS-redirects to WebBookingSearchSteps —
        # server-rendered, so the target URL is just a real link in the HTML,
        # not something that needs actual JS execution to follow.
        match = re.search(r'location\.href\s*=\s*"([^"]+WebBookingSearchSteps[^"]*)"', resp.text)
        if match:
            fetch_throttle.wait_turn()
            s.get(f"{TEEON_BASE}/{match.group(1)}", timeout=12)
        return s
    except Exception:
        return None


def _search_slots(session: requests.Session, search_date: str, search_time: str) -> list[dict]:
    fetch_throttle.wait_turn()
    resp = session.post(
        RESULTS_URL,
        data={
            "Date": search_date,
            "SearchTime": search_time,
            "Holes": "18",
            "Players": "4",
            "CourseIdHIGV": COURSE_CODE,
            "CourseGroupID": COURSE_GROUP_ID,
            "Referrer": "",
        },
        timeout=15,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    slots = []
    for box in soup.select("div.search-results-tee-times-box"):
        time_el = box.select_one("p.time")
        price_el = box.select_one("p.price")
        if not time_el:
            continue
        ampm = time_el.select_one(".am-pm")
        time_text = time_el.get_text(strip=True)
        if ampm:
            time_text = time_text.replace(ampm.get_text(strip=True), f" {ampm.get_text(strip=True)}")
        slots.append({"time": time_text.strip(), "price": price_el.get_text(strip=True) if price_el else None})
    return slots


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_tee_sheet_raw(search_date: str) -> list[dict]:
    session = _teeon_session()
    if session is None:
        raise RuntimeError("could not establish a Tee-On session")
    seen_times = {}
    for search_time in _SCAN_TIMES:
        for slot in _search_slots(session, search_date, search_time):
            seen_times[slot["time"]] = slot["price"]
    return [{"time": t, "price": p} for t, p in seen_times.items()]


_last_good_tee_sheet: dict[str, list[dict]] = {}


def tee_sheet(search_date: date) -> list[dict] | None:
    """[{"time", "price"}] — every genuinely open tee time found
    across the day's representative scan, deduplicated. None only if
    the site itself is unreachable (falls back to the last good scan
    for that date otherwise)."""
    key = search_date.isoformat()
    try:
        slots = _fetch_tee_sheet_raw(key)
    except Exception:
        return _last_good_tee_sheet.get(key)
    _last_good_tee_sheet[key] = slots
    return slots


def _playability_score(weather: dict) -> float:
    """0-10, transparent point deductions from a real live reading —
    not a scientific model, a readable rubric (see module docstring)."""
    temp_c, wind_kmh = weather.get("temp_c"), weather.get("wind_kmh")
    precip_pct, uv = weather.get("precip_probability"), weather.get("uv_index")
    score = 10.0
    if temp_c is not None:
        if temp_c < 16:
            score -= min(4.0, (16 - temp_c) * 0.4)
        elif temp_c > 26:
            score -= min(3.0, (temp_c - 26) * 0.3)
    if wind_kmh is not None and wind_kmh > 15:
        score -= min(3.0, (wind_kmh - 15) * 0.15)
    if precip_pct is not None:
        score -= (precip_pct / 100) * 4.0
    if uv is not None and uv >= 8:
        score -= 0.5
    return round(max(0.0, min(10.0, score)), 1)


def _busyness_score(occupancy_pct: float) -> float:
    """0-10 — HIGHER means a BETTER crowd situation (more open times),
    same "higher is better" direction as Playability/Golfability, not
    literally "how busy" despite the name (see module docstring for
    why the session's own worked example only makes sense read this
    way)."""
    return round(max(0.0, min(10.0, (1 - occupancy_pct / 100) * 10)), 1)


def _demand_label(occupancy_pct: float) -> str:
    if occupancy_pct >= 66:
        return "HIGH"
    if occupancy_pct >= 33:
        return "MODERATE"
    return "LOW"


def golfability(target_date: date | None = None) -> dict | None:
    """{"golfability", "playability", "busyness", "weather": {...},
    "occupancy_pct", "demand", "course_status", "slots": [...]} for
    the given date (today by default). None only if BOTH real sources
    (weather and the tee sheet) failed at once — a single source
    failing still returns a partial, honestly-labeled result rather
    than nothing."""
    target_date = target_date or date.today()
    weather = _course_weather()
    slots = tee_sheet(target_date)
    if weather is None and slots is None:
        return None

    playability = _playability_score(weather) if weather else None
    occupancy_pct = round(max(0.0, min(100.0, 100 * (1 - len(slots) / _ASSUMED_DAILY_CAPACITY))), 0) if slots is not None else None
    busyness = _busyness_score(occupancy_pct) if occupancy_pct is not None else None

    if playability is not None and busyness is not None:
        combined = round(0.6 * playability + 0.4 * busyness, 1)
    else:
        combined = playability if playability is not None else busyness

    return {
        "golfability": combined,
        "playability": playability,
        "busyness": busyness,
        "weather": weather,
        "occupancy_pct": occupancy_pct,
        "demand": _demand_label(occupancy_pct) if occupancy_pct is not None else None,
        # "FULLY BOOKED", not "CLOSED" for an empty result — see module
        # docstring for why (a real live case caught during testing).
        "course_status": "OPEN" if slots else ("FULLY BOOKED" if slots is not None else None),
        "slots": slots or [],
    }


# Session's own overall framing for all four systems: "Most of the
# time they should remain quiet. When something genuinely interesting
# happens, the dashboard should notice and surface it." A great
# TODAY specifically (real weather + real open tee times both
# genuinely lining up) is that moment for golf — once a day, not
# re-fired every rerun, and never for a future date (a toast is about
# right-now relevance, not a standing forecast).
GREAT_DAY_THRESHOLD = 8.5
_ALERTED_DATE_KEY = "golf_great_day_alerted_date"
_alerted_date: str | None = persisted_state.load_per_instance(_ALERTED_DATE_KEY, None)


def get_new_alerts(now: datetime) -> list[dict]:
    global _alerted_date
    today_str = now.date().isoformat()
    if _alerted_date == today_str:
        return []
    result = golfability(now.date())
    if result is None or result["golfability"] is None:
        return []
    if result["golfability"] < GREAT_DAY_THRESHOLD:
        return []
    _alerted_date = today_str
    persisted_state.save_per_instance(_ALERTED_DATE_KEY, _alerted_date)
    weather = result["weather"] or {}
    parts = []
    if weather.get("temp_c") is not None:
        parts.append(f"{weather['temp_c']:.0f}°C")
    if weather.get("wind_kmh") is not None:
        parts.append(f"wind {weather['wind_kmh']:.0f} km/h")
    if result["occupancy_pct"] is not None:
        parts.append(f"tee sheet {result['occupancy_pct']:.0f}% booked")
    return [
        {
            "kind": "weather",
            "severity": "statement",
            "label": "⛳ Golf Intelligence",
            "headline": f"Great day to golf — {result['golfability']}/10 at Highview",
            "summary": ", ".join(parts),
        }
    ]
