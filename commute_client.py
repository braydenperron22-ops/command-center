"""Drive time between COMMUTE_ORIGIN and a destination, traffic-aware
via TomTom's Routing API (free tier: 2,500 requests/day, no credit
card) — this app checks at most once per CACHE_TTL_SECONDS, so even
the kiosk running unattended 24/7 stays a tiny fraction of that.
Destination defaults to COMMUTE_DESTINATION but callers (see
commute_reminder.todays_destination) can route somewhere else entirely
— today's shift's own calendar location, if it has one.

Replaces an earlier OSRM-based version: OSRM's public server routes
the static road network only (speed limits/road class), no live
conditions, so it could never actually answer "how bad is traffic
right now" — the entire point of this tile.
"""

import requests
import streamlit as st

import commute_history
import fetch_throttle
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN

ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute/{lat1},{lon1}:{lat2},{lon2}/json"
GEOCODE_URL = "https://api.tomtom.com/search/2/geocode/{query}.json"
# TomTom's documented category taxonomy for traffic sections — mapped
# to something readable in place of the bare code.
#
# Checked against a real incident 2026-08-31 (a genuine Highway 17
# full closure, confirmed independently via road_conditions_511.py) —
# this taxonomy DIDN'T match: both of the route's real TRAFFIC sections
# came back "simpleCategory": "OTHER", not "ROAD_CLOSURE" or "ACCIDENT"
# the way a closure was assumed to be tagged when this was first
# written untested. "OTHER" being silently dropped meant a genuinely
# severe section (one at effectiveSpeedInKmh: 7 — barely moving, both
# at magnitudeOfDelay: 4) showed up on screen as "no delay" — see
# _incident_label's own fallback below for the fix, which checks the
# real magnitude/speed fields instead of trusting the category alone
# for an "OTHER"-tagged section.
INCIDENT_CATEGORY_LABELS = {
    "JAM": "heavy traffic",
    "ROAD_WORKS": "road work",
    "ROAD_CLOSURE": "road closed",
    "ACCIDENT": "accident",
    "DANGEROUS_CONDITIONS": "dangerous conditions",
    "LANE_RESTRICTION": "lane restriction",
    "NARROW_LANES": "narrow lanes",
    "OTHER": None,  # only "too vague" when it ALSO shows no real severity — see _incident_label
}
# TomTom's magnitudeOfDelay: 0 unknown, 1 minor, 2 moderate, 3 major,
# 4 undefined — "undefined" is specifically what a section representing
# an impassable closure looks like (there's no meaningful "how much
# slower than normal" fraction for a road that can't be driven at all,
# so TomTom can't grade it 1-3). Confirmed live: both of the real
# closure's sections above were magnitude 4. >= SEVERE_MAGNITUDE
# catches major (3) too, not just the undefined case.
SEVERE_MAGNITUDE = 3
# Well below any real highway/arterial free-flow speed — confirmed
# live at 7 km/h on the actual closure's own worst section.
SEVERE_SPEED_KMH = 20
# 5 min still only burns ~288 calls/day (11.5% of the free-tier quota)
# even running unattended 24/7 — 15 min was needlessly conservative and
# let the shown time lag real conditions by up to a quarter hour.
CACHE_TTL_SECONDS = 5 * 60
# Addresses don't move — cache geocoding results for a long time rather
# than re-spending a request on the same event location every time it
# comes up. Long enough to cover a recurring shift's whole run without
# needing a re-lookup, short enough that a typo'd address fixed in the
# calendar doesn't stay wrong for a similarly long time.
GEOCODE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

_last_good_route: dict | None = None


def _incident_label(route_data: dict) -> str | None:
    """A short "why" for the delay (e.g. "accident") from the route's
    traffic sections, or None if there's nothing notable — TomTom only
    seems to include `sections` at all when there's something to
    report, so an empty/missing list here just means a clean route,
    not a parsing failure.

    A named category (JAM/ROAD_CLOSURE/etc — see INCIDENT_CATEGORY_
    LABELS) always wins when TomTom actually provides one. A section
    tagged "OTHER" — or any category not in that map — still gets a
    generic "slow traffic" label if its own magnitude/speed fields
    show something real (see SEVERE_MAGNITUDE/SEVERE_SPEED_KMH above),
    rather than being silently dropped just for lacking a named
    category — confirmed live this is exactly what a real closure's
    own traffic section looks like from TomTom's side."""
    sections = [s for s in route_data.get("sections", []) if s.get("sectionType") == "TRAFFIC"]
    labels = set()
    has_unnamed_severe = False
    for s in sections:
        label = INCIDENT_CATEGORY_LABELS.get(s.get("simpleCategory"))
        if label:
            labels.add(label)
            continue
        magnitude = s.get("magnitudeOfDelay") or 0
        speed = s.get("effectiveSpeedInKmh")
        if magnitude >= SEVERE_MAGNITUDE or (speed is not None and speed <= SEVERE_SPEED_KMH):
            has_unnamed_severe = True
    if has_unnamed_severe:
        labels.add("slow traffic")
    if not labels:
        return None
    return ", ".join(sorted(labels))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_route_raw(api_key: str, dest_lat: float, dest_lon: float, record_history: bool) -> dict:
    url = ROUTE_URL.format(
        lat1=COMMUTE_ORIGIN["lat"], lon1=COMMUTE_ORIGIN["lon"],
        lat2=dest_lat, lon2=dest_lon,
    )
    fetch_throttle.wait_turn()
    # maxAlternatives/alternativeType=anyRoute — session report: "you
    # legit cannot get through, it's a closure. tomtom is flat out
    # lying to me about getting to work in 24 mins." Confirmed against
    # TomTom's own documentation: the reference route (routes[0], all
    # this used to ever request) is BY DESIGN routed straight through a
    # ROAD_CLOSURE incident, with that incident's own time cost
    # explicitly excluded from the reference route's own summary stats
    # — not a bug on TomTom's side, a deliberate reference-route
    # convention that makes its number fiction whenever a real closure
    # is active. alternativeType="betterRoute" (the mode that would
    # give a clean "planningReason": "Blockage" flag) needs an existing
    # route to reconstruct against and 400s on a fresh calculateRoute
    # call — confirmed live — so "anyRoute" is what's actually usable
    # here; the severity check below (reusing _incident_label) is what
    # decides whether an alternative is actually needed.
    resp = requests.get(
        url,
        params={"key": api_key, "traffic": "true", "sectionType": "traffic", "maxAlternatives": 2, "alternativeType": "anyRoute"},
        timeout=15,
    )
    resp.raise_for_status()
    routes = resp.json()["routes"]
    reference = routes[0]
    # A real severe section on the reference route (see SEVERE_
    # MAGNITUDE/SEVERE_SPEED_KMH — this is exactly what a genuine
    # closure's own TomTom section looks like, confirmed live against
    # the real Highway 17 closure) means the reference route's own
    # duration/delay can't be trusted as actually drivable. Switch to
    # whichever real alternative is fastest — still a real, genuinely
    # calculated route, not an invented number. `incident` itself stays
    # sourced from the reference route either way, since that's what's
    # actually explaining why the number changed.
    incident = _incident_label(reference)
    chosen = reference
    if incident and len(routes) > 1:
        chosen = min(routes[1:], key=lambda r: r["summary"]["travelTimeInSeconds"])
    summary = chosen["summary"]
    # Inside the cached function, not in route() below — st.cache_data
    # only re-executes this body on an actual cache miss, so this
    # naturally records one point per real TomTom call (~every 15 min),
    # not once per rerun. Only for the default destination: mixing in
    # durations to whatever one-off location a shift happened to have
    # would make the "X min in the last 30 min" trend compare two
    # different routes against each other.
    if record_history:
        commute_history.record(summary["travelTimeInSeconds"])
    # Session request: "every single road that is in any of my
    # commutes" — real point-by-point geometry of the actual route
    # being taken (already `chosen`, so this reflects any active
    # severe-section reroute above too), for road_conditions_511.py to
    # match real MTO events against the real driven path instead of a
    # blunt radius around either endpoint. Confirmed live: a real
    # ~24km route returns 250 real lat/lon points.
    points = [(p["latitude"], p["longitude"]) for p in chosen.get("legs", [{}])[0].get("points", [])]
    return {
        "duration_seconds": summary["travelTimeInSeconds"],
        "delay_seconds": summary["trafficDelayInSeconds"],
        "distance_km": summary["lengthInMeters"] / 1000,
        "incident": incident,
        "points": points,
    }


def route(destination: dict | None = None) -> dict | None:
    """`destination` is {"lat", "lon"} (a "label" key, if present, is
    ignored here) — None routes to the default COMMUTE_DESTINATION.
    The last-good fallback only applies to that default: a stale route
    to some other day's one-off event location would be actively
    misleading rather than merely outdated."""
    global _last_good_route
    api_key = st.secrets.get("TOMTOM_API_KEY")
    if not api_key:
        return None
    is_default = destination is None
    dest = destination or COMMUTE_DESTINATION
    try:
        result = _fetch_route_raw(api_key, dest["lat"], dest["lon"], is_default)
    except Exception:
        return _last_good_route if is_default else None
    if is_default:
        _last_good_route = result
    return result


@st.cache_data(ttl=GEOCODE_CACHE_TTL_SECONDS, show_spinner=False)
def _geocode_raw(address: str, api_key: str) -> dict | None:
    url = GEOCODE_URL.format(query=requests.utils.quote(address))
    fetch_throttle.wait_turn()
    resp = requests.get(url, params={"key": api_key, "limit": 1}, timeout=10)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    pos = results[0]["position"]
    return {"lat": pos["lat"], "lon": pos["lon"]}


def geocode(address: str) -> dict | None:
    """{"lat", "lon"} for a free-text address/place name, or None if
    it's blank, geocoding is unavailable, or nothing matched."""
    api_key = st.secrets.get("TOMTOM_API_KEY")
    if not api_key or not address.strip():
        return None
    try:
        return _geocode_raw(address, api_key)
    except Exception:
        return None
