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

from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

import commute_history
import fetch_throttle
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN, TIMEZONE

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
# Session report: "is there any quicker route? or is this the
# quickest?" — checked the real live TomTom response and found a real
# bug: the reference route (magnitudeOfDelay: 3, a real but ordinary
# JAM) was genuinely the FASTEST of all 3 routes TomTom returned
# (27.9min vs 31.4/33.0min for the two alternatives), but _fetch_route_
# raw's own alternative-switch logic (below) only ever compared the
# ALTERNATIVES against each other, never against the reference itself
# — so it was picking the fastest of the two WORSE options instead of
# the genuinely fastest of all three, costing several real minutes.
# UNDEFINED_MAGNITUDE (4) is specifically what a genuine impassable
# closure's own section looks like (see SEVERE_MAGNITUDE's own comment
# above — TomTom can't express "how much slower than normal" as a
# real fraction for a road that literally can't be driven, so it comes
# back "undefined" instead of a real major/moderate/minor grade) —
# THAT specific case is the one where the reference route's own
# reported time is genuinely fictional (TomTom excludes the closure's
# real cost from routes[0]'s own summary by design, the original "24
# minutes, tomtom is lying to me" bug), so it's the only case that
# still needs to be excluded from the "pick whichever is actually
# fastest" comparison below. A magnitude-3 "major" jam, even a bad one,
# still has its real delay correctly included in the reference route's
# own numbers — nothing fictional about it, so there's no reason to
# blind the comparison to it.
UNDEFINED_MAGNITUDE = 4
# 5 min still only burns ~288 calls/day (11.5% of the free-tier quota)
# even running unattended 24/7 — 15 min was needlessly conservative and
# let the shown time lag real conditions by up to a quarter hour.
CACHE_TTL_SECONDS = 5 * 60
# Session request: a predictive call using TomTom's departAt parameter
# (IQ Routes historical speed profiles for a specific future time — the
# recurring 8-8:30am bus jam this was built to catch is baked into that
# profile whether or not it's actually happened yet today), run
# alongside the existing live/right-now call — see route()'s own
# depart_at param and commute_reminder._hybrid_route for how the two
# get compared. Rounded to this bucket before being sent AND before
# being used as a cache key: depart_at is normally a computed estimate
# that drifts by seconds on every rerun (today's rough leave_by
# recalculated fresh each time) — an unrounded value would cache-miss
# on nearly every call, burning a real TomTom request every ~5s instead
# of every CACHE_TTL_SECONDS like every other call here (see gemini_
# client.generate's own docstring for the same "bucket, don't use a raw
# timestamp as a cache key" discipline this mirrors).
DEPART_AT_BUCKET_MINUTES = 5
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


def _reference_time_trustworthy(route_data: dict) -> bool:
    """False only when the reference route's own reported time can't
    be trusted as a real drivable estimate — a genuine impassable
    closure (see UNDEFINED_MAGNITUDE's own comment above): TomTom
    excludes a closure's real time cost from the route's own summary
    by design, so its number is a genuinely fictional, too-low figure
    whenever one is active — not something a "pick whichever route is
    actually fastest" comparison should ever trust. True for
    everything else, ordinary traffic however severe included — an
    ordinary jam's real delay IS genuinely included in the reference's
    own reported time (confirmed against a real live magnitude-3 JAM:
    the reference route was still the genuinely fastest of 3 real
    routes TomTom returned), so there's nothing fictional to guard
    against there."""
    sections = [s for s in route_data.get("sections", []) if s.get("sectionType") == "TRAFFIC"]
    for s in sections:
        if s.get("simpleCategory") == "ROAD_CLOSURE":
            return False
        if (s.get("magnitudeOfDelay") or 0) >= UNDEFINED_MAGNITUDE:
            return False
    return True


def _round_depart_at(depart_at: datetime) -> datetime:
    """Floor `depart_at` to DEPART_AT_BUCKET_MINUTES — see that
    constant's own comment for why this matters for caching, not just
    tidiness."""
    minute = (depart_at.minute // DEPART_AT_BUCKET_MINUTES) * DEPART_AT_BUCKET_MINUTES
    return depart_at.replace(minute=minute, second=0, microsecond=0)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_route_raw(
    api_key: str, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float,
    record_history: bool, depart_at_iso: str | None = None,
) -> dict:
    url = ROUTE_URL.format(
        lat1=origin_lat, lon1=origin_lon,
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
    #
    # depart_at_iso — session request: "query TomTom using a dynamic
    # future departure time... this ensures it utilizes TomTom's
    # historical speed profiles (IQ Routes) to automatically bake in the
    # recurring morning bus jam." Omitted entirely (TomTom's own default
    # is "now") for the plain live call; set to a real ISO8601 timestamp
    # (already bucketed by the caller — see route()) for the predictive
    # one.
    params = {"key": api_key, "traffic": "true", "sectionType": "traffic", "maxAlternatives": 2, "alternativeType": "anyRoute"}
    if depart_at_iso:
        params["departAt"] = depart_at_iso
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    routes = resp.json()["routes"]
    reference = routes[0]
    # A real severe section on the reference route (see SEVERE_
    # MAGNITUDE/SEVERE_SPEED_KMH — this is exactly what a genuine
    # closure's own TomTom section looks like, confirmed live against
    # the real Highway 17 closure) means the reference route's own
    # duration/delay MIGHT not be trustworthy — see _reference_time_
    # trustworthy for exactly which case that actually is (a genuine
    # closure specifically, not ordinary severe traffic). Switch to
    # whichever real alternative is fastest — still a real, genuinely
    # calculated route, not an invented number. `incident` itself stays
    # sourced from the reference route either way, since that's what's
    # actually explaining why the number changed.
    #
    # Session report, live: "is there any quicker route? or is this
    # the quickest?" — this used to compare the alternatives ONLY
    # against each other (routes[1:]), never against the reference
    # itself, so an ordinary jam on the reference (real, correctly-
    # priced-in delay, nothing fictional about it — see _reference_
    # time_trustworthy) could still end up picking a genuinely SLOWER
    # alternative just because an incident was detected at all. Real,
    # confirmed live: the reference was the fastest of 3 real TomTom
    # routes (27.9min) while this bug had it running the 31.4min
    # alternative instead. The reference only gets excluded from the
    # comparison now when its own time is actually untrustworthy (a
    # genuine closure) — every other case picks the real fastest of
    # ALL the routes TomTom returned, reference included.
    incident = _incident_label(reference)
    chosen = reference
    if incident and len(routes) > 1:
        pool = routes if _reference_time_trustworthy(reference) else routes[1:]
        chosen = min(pool, key=lambda r: r["summary"]["travelTimeInSeconds"])
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
        # Session report: "it's still delayed from my regular route
        # tho. so compute it from my normal routes time to the
        # detour." The reference route's own time IS genuinely "what
        # this route normally takes" — that's the real reason its own
        # number was fiction as a DRIVE-TIME quote earlier (TomTom
        # excludes a real closure's cost from it by design), but that
        # exact same property makes it the right baseline for THIS
        # question. Equal to duration_seconds whenever no alternative
        # was needed (chosen is reference) — callers can always safely
        # take (duration_seconds - reference_duration_seconds) as the
        # real extra cost of today's detour, zero on an ordinary day.
        "reference_duration_seconds": reference["summary"]["travelTimeInSeconds"],
    }


def route(destination: dict | None = None, depart_at: datetime | None = None, origin: dict | None = None) -> dict | None:
    """`destination` is {"lat", "lon"} (a "label" key, if present, is
    ignored here) — None routes to the default COMMUTE_DESTINATION.
    The last-good fallback only applies to the plain live default call
    (destination, depart_at, AND origin all None): a stale route to
    some other day's one-off event location, or a stale route standing
    in for a genuinely failed PREDICTIVE call, would be actively
    misleading rather than merely outdated — a failed predictive call
    should just come back None and let the caller (see commute_
    reminder._hybrid_route) fall back to the live route it already has,
    not get silently backfilled with some other route entirely.

    `depart_at` — session request: a predictive call using TomTom's own
    IQ Routes historical speed profiles for a specific future departure
    time, instead of always querying for "right now." Naive or aware,
    always reinterpreted as being in TIMEZONE (same "arrives already in
    the local zone" convention every other datetime in this app uses)
    and floored to DEPART_AT_BUCKET_MINUTES before being sent — see
    that constant's own comment for why the rounding isn't optional.
    Never recorded into commute_history even for the default
    destination: that log is real OBSERVED conditions, not a
    hypothetical future prediction.

    `origin` — session request: "the estimated commute time home...
    using the same guardrails and process that we use for the commute
    there." None routes FROM the default COMMUTE_ORIGIN (home), same
    as this always did; a caller building the reverse trip (work ->
    home) passes {"lat", "lon"} for the actual starting point instead
    — same hybrid predictive+live machinery, same incident detection,
    same everything, just not hardcoded to always start from home
    anymore. Distinct origin/destination pairs get their own cache
    entries for free (both are now real @st.cache_data parameters)."""
    global _last_good_route
    api_key = st.secrets.get("TOMTOM_API_KEY")
    if not api_key:
        return None
    is_default = destination is None and origin is None
    dest = destination or COMMUTE_DESTINATION
    org = origin or COMMUTE_ORIGIN
    depart_at_iso = None
    if depart_at is not None:
        localized = depart_at if depart_at.tzinfo else depart_at.replace(tzinfo=ZoneInfo(TIMEZONE))
        depart_at_iso = _round_depart_at(localized).isoformat(timespec="seconds")
    record_history = is_default and depart_at is None
    try:
        result = _fetch_route_raw(api_key, org["lat"], org["lon"], dest["lat"], dest["lon"], record_history, depart_at_iso)
    except Exception:
        return _last_good_route if (is_default and depart_at is None) else None
    if is_default and depart_at is None:
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
