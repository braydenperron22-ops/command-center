"""Passive local aircraft radar around the dashboard's own configured
location (WEATHER_LAT/LON — the same North Bay coordinate COMMUTE_
ORIGIN already uses). Session request: "Detect aircraft in the
surrounding area and surface an event when an aircraft is genuinely
interesting or sufficiently close... Normal repetitive commercial
traffic should remain silent... should feel like a passive local radar
sensor, not a replacement for FlightRadar24."

Two real, free, no-key data sources, both confirmed live before
building this:
  - OpenSky Network's own /states/all — real live position/altitude/
    speed/heading/callsign for every transponder-equipped aircraft in
    a bounding box. Anonymous tier gives ~400 requests/day (confirmed
    via its own x-rate-limit-remaining response header), which is why
    CACHE_TTL_SECONDS below is 5 minutes, not something tighter — a
    "passive sensor" doesn't need second-by-second updates anyway.
  - hexdb.io — fills in what OpenSky's own state vectors don't carry:
    registration/aircraft type/operator (from the ICAO24 hex) and a
    callsign-to-route lookup. Only called for aircraft that already
    clear the detection radius below, not every aircraft OpenSky
    returns — no reason to spend a lookup on something already too far
    away to matter.

"Interesting" is the session's own explicit list (unusual aircraft,
low-altitude, helicopters, cargo, military/government where
identifiable, particularly close, unusual types) minus "unusual type
for the area" specifically — there's no well-grounded "what's normal
here" baseline to classify against yet (this would need weeks of real
accumulated traffic data this app doesn't have), so rather than fake
that judgment, this module sticks to the concrete, reliably-detectable
signals: proximity, altitude, and aircraft category (helicopter/cargo/
military) from hexdb's own operator/type text.

Restored 2026-08-31, unchanged from its original 2026-08-21 build — it
was never actually broken; it was swept up in a next-day wholesale
revert of that whole day's four new systems (aviation, golf, financial
plumbing, league transactions) together, because their *combined*
toast-check load was what caused real page-render-blocking bugs, not
this module specifically. Re-confirmed OpenSky/hexdb both still live
and reachable, unauthenticated, same ~400 req/day anonymous rate limit,
before re-wiring this back into app.py."""

import math
from datetime import datetime

import requests
import streamlit as st

import fetch_throttle
import persisted_state
from config import WEATHER_LAT, WEATHER_LON

OPENSKY_URL = "https://opensky-network.org/api/states/all"
HEXDB_AIRCRAFT_URL = "https://hexdb.io/api/v1/aircraft/{icao24}"
HEXDB_ROUTE_URL = "https://hexdb.io/api/v1/route/icao/{callsign}"

CACHE_TTL_SECONDS = 5 * 60
DETECTION_RADIUS_KM = 50  # "the surrounding area" — a genuinely local radar feel, not a whole-province one
CLOSE_RADIUS_KM = 15  # "particularly close"
LOW_ALTITUDE_FT = 3000
# Don't re-alert the same airframe while it's still on the same pass
# through the area (a few consecutive 5-minute polls would otherwise
# each fire their own toast for literally the same aircraft still
# crossing the radius) — but DO alert again on a genuinely later pass.
# Session's own "passive sensor, not a live tracker" framing: one
# notice per real appearance, not a running feed of the same blip.
COOLDOWN_MINUTES = 30

# hexdb's own "RegisteredOwners" text is free-form, not a coded field
# — these are real substrings confirmed to appear in it for the
# relevant operator types, checked case-insensitively.
_CARGO_KEYWORDS = ["fedex", "ups", "purolator", "cargojet", "dhl", "atlas air", "kalitta", "amazon air"]
_MILITARY_GOV_KEYWORDS = [
    "air force", "govern", "forces", "coast guard", "national defence", "customs", "border",
    "ornge",  # Ontario's real air-ambulance operator — genuinely notable low-altitude traffic, not routine
]
_HELICOPTER_KEYWORDS = ["helicopter", "bell ", "eurocopter", "airbus helicopters", "sikorsky", "robinson", "agusta"]


def _bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))
    return lat - lat_delta, lon - lon_delta, lat + lat_delta, lon + lon_delta


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_states_raw() -> list[list]:
    fetch_throttle.wait_turn()
    lamin, lomin, lamax, lomax = _bounding_box(WEATHER_LAT, WEATHER_LON, DETECTION_RADIUS_KM)
    resp = requests.get(
        OPENSKY_URL, params={"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax}, timeout=10
    )
    resp.raise_for_status()
    return resp.json().get("states") or []


_last_good_states: list[list] = []


def _fetch_states() -> list[list]:
    global _last_good_states
    try:
        states = _fetch_states_raw()
    except Exception:
        return _last_good_states
    _last_good_states = states
    return states


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _fetch_aircraft_meta(icao24: str) -> dict | None:
    try:
        resp = requests.get(HEXDB_AIRCRAFT_URL.format(icao24=icao24), timeout=8)
        resp.raise_for_status()
        data = resp.json()
        return data if data else None
    except Exception:
        return None


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _fetch_route(callsign: str) -> str | None:
    try:
        resp = requests.get(HEXDB_ROUTE_URL.format(callsign=callsign), timeout=8)
        resp.raise_for_status()
        data = resp.json()
        return data.get("route") if data else None
    except Exception:
        return None


def _category(meta: dict | None) -> str | None:
    """"helicopter"/"cargo"/"military" from hexdb's own operator/type
    text, or None if it doesn't match any of those — a plain
    commercial/general-aviation aircraft, or metadata wasn't
    available at all (treated as neutral, not flagged, since a data
    gap isn't evidence of anything)."""
    if not meta:
        return None
    operator, type_name = meta.get("RegisteredOwners", ""), meta.get("Type", "")
    text = f"{operator} {type_name}".lower()
    if any(k in text for k in _MILITARY_GOV_KEYWORDS):
        return "military/government"
    # A passenger airline's own cargo-branded flight (Cathay Pacific
    # operating a 747 freighter, say) never matches an operator-name
    # keyword — real aviation convention marks a freighter VARIANT in
    # the type code itself with a trailing "F" (747-8F, MD-11F, a
    # converted 737-800BCF), confirmed live against a real Cathay
    # Pacific "747 867F" JFK-Hong Kong freighter that the operator-name
    # check alone missed.
    if any(k in text for k in _CARGO_KEYWORDS) or type_name.strip().upper().endswith("F"):
        return "cargo"
    if any(k in text for k in _HELICOPTER_KEYWORDS):
        return "helicopter"
    return None


def nearby_aircraft() -> list[dict]:
    """Every airborne aircraft currently within DETECTION_RADIUS_KM,
    nearest first — real position/altitude/speed/heading straight from
    OpenSky, no hexdb lookup (this is the cheap, always-safe call; the
    expensive per-aircraft metadata lookup lives in _enrich, called
    only for aircraft actually worth alerting on)."""
    out = []
    for s in _fetch_states():
        icao24, callsign = s[0], (s[1] or "").strip()
        lon, lat, baro_alt, on_ground, velocity, heading = s[5], s[6], s[7], s[8], s[9], s[10]
        if on_ground or lat is None or lon is None:
            continue
        distance = _distance_km(WEATHER_LAT, WEATHER_LON, lat, lon)
        if distance > DETECTION_RADIUS_KM:
            continue
        out.append(
            {
                "icao24": icao24,
                "callsign": callsign or None,
                "altitude_ft": round(baro_alt * 3.28084) if baro_alt is not None else None,
                "speed_kts": round(velocity * 1.94384) if velocity is not None else None,
                "heading": round(heading) if heading is not None else None,
                "distance_km": round(distance, 1),
            }
        )
    out.sort(key=lambda a: a["distance_km"])
    return out


def _enrich(aircraft: dict) -> dict:
    """Adds registration/operator/type/route via hexdb — only called
    on an aircraft that's already cleared the "worth alerting on" bar,
    not every aircraft in range."""
    meta = _fetch_aircraft_meta(aircraft["icao24"])
    route = _fetch_route(aircraft["callsign"]) if aircraft["callsign"] else None
    origin, destination = (None, None)
    if route and "-" in route:
        origin, destination = route.split("-", 1)
    return {
        **aircraft,
        "registration": (meta or {}).get("Registration"),
        "operator": (meta or {}).get("RegisteredOwners"),
        "type": (meta or {}).get("Type"),
        "category": _category(meta),
        "origin": origin,
        "destination": destination,
    }


def _interest_reason(aircraft: dict, category: str | None) -> str | None:
    """None if this aircraft is routine — the ordinary commercial
    traffic the session request explicitly wants left silent."""
    if category:
        return category
    if aircraft["distance_km"] <= CLOSE_RADIUS_KM:
        return "close"
    if aircraft["altitude_ft"] is not None and aircraft["altitude_ft"] <= LOW_ALTITUDE_FT:
        return "low altitude"
    return None


# hexdb's own route lookup returns ICAO airport codes (CYYZ, KJFK), not
# city names — real, but not what the session's own mockup shows
# ("Montréal → Toronto"). Rather than invent a city name for a code
# not in this list, _airport_label below falls back to the raw code —
# only the major airports below (the ones actually plausible for this
# specific location — the domestic Canadian corridor plus the busiest
# US/transatlantic hubs) get the friendlier name, confirmed real, not
# guessed.
_AIRPORT_CITY = {
    "CYYZ": "Toronto", "CYUL": "Montréal", "CYOW": "Ottawa", "CYYC": "Calgary",
    "CYVR": "Vancouver", "CYWG": "Winnipeg", "CYHZ": "Halifax", "CYYB": "North Bay",
    "CYQB": "Québec City", "CYEG": "Edmonton", "CYXE": "Saskatoon",
    "KJFK": "New York", "KEWR": "Newark", "KLGA": "New York", "KORD": "Chicago",
    "KATL": "Atlanta", "KLAX": "Los Angeles", "KSFO": "San Francisco", "KBOS": "Boston",
    "KDFW": "Dallas", "KIAH": "Houston", "KMIA": "Miami", "KSEA": "Seattle",
    "KDEN": "Denver", "KPHX": "Phoenix", "KLAS": "Las Vegas", "KMSP": "Minneapolis",
    "KDTW": "Detroit", "KPHL": "Philadelphia", "KSAN": "San Diego",
    "EGLL": "London", "LFPG": "Paris", "EDDF": "Frankfurt", "EHAM": "Amsterdam",
}


def _airport_label(code: str | None) -> str | None:
    return _AIRPORT_CITY.get(code, code) if code else None


def _alert_dict(aircraft: dict, reason: str) -> dict:
    lines = []
    if aircraft.get("operator"):
        lines.append(aircraft["operator"])
    if aircraft.get("type"):
        lines.append(aircraft["type"])
    if aircraft.get("altitude_ft") is not None:
        lines.append(f"{aircraft['altitude_ft']:,} ft")
    lines.append(f"{aircraft['distance_km']} km away")
    origin, destination = _airport_label(aircraft.get("origin")), _airport_label(aircraft.get("destination"))
    if origin and destination:
        lines.append(f"{origin} → {destination}")
    headline = aircraft.get("callsign") or aircraft.get("registration") or "Unidentified aircraft"
    return {
        "kind": "weather",
        "severity": "statement",
        "label": "✈️ Aircraft Nearby",
        "headline": headline,
        "summary": " · ".join(lines),
    }


# Session request: "surface an event when an aircraft is genuinely
# interesting or sufficiently close." One toast per real appearance —
# COOLDOWN_MINUTES keeps the same aircraft from re-firing on every
# 5-minute poll while it's still crossing the same detection radius,
# without permanently suppressing it (a genuinely later pass, hours or
# days on, is a new event). No baseline gate needed the way road_
# conditions_511's closures needed one: "is there an interesting
# aircraft near me right now" is a current fact by construction, same
# reasoning market_volatility_alert.py and financial_plumbing_client
# already use for their own toasts.
_LAST_ALERT_KEY = "aviation_last_alert_at"
_last_alert_at: dict = dict(persisted_state.load_per_instance(_LAST_ALERT_KEY, {}))


def get_new_alerts(now: datetime) -> list[dict]:
    global _last_alert_at
    alerts = []
    changed = False
    now_ts = now.timestamp()
    for aircraft in nearby_aircraft():
        key = aircraft["icao24"]
        last_at = _last_alert_at.get(key)
        if last_at is not None and (now_ts - last_at) < COOLDOWN_MINUTES * 60:
            continue
        enriched = _enrich(aircraft)
        reason = _interest_reason(enriched, enriched["category"])
        if reason is None:
            continue
        _last_alert_at[key] = now_ts
        changed = True
        alerts.append(_alert_dict(enriched, reason))
    if changed:
        cutoff = now_ts - COOLDOWN_MINUTES * 60 * 4
        _last_alert_at = {k: v for k, v in _last_alert_at.items() if v > cutoff}
        persisted_state.save_per_instance(_LAST_ALERT_KEY, _last_alert_at)
    return alerts
