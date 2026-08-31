"""Real, structured Ontario road-condition data (surface state,
visibility, drifting) and highway closures from the province's own 511
Ontario feeds — MTO's official reported conditions, not this app's own
temp+precip inference (see road_conditions.py's own ice_risk, which
stays as the same-day fallback for whenever 511 has nothing specific
to report for the exact roads that actually matter here).

Session request, after a gap-analysis pass against the whole codebase:
"I want five one one to track all types of road conditions, not just
freezing rain... whether they're wet, whether there's closures... the
entire suite... as well as if there's any closures along my commutes."

Two genuinely different 511 endpoints, both real, both free/no-key
(confirmed live — same no-auth pattern local_news_client.py's own
/event fetch already established):

- /roadconditions (v3): province-wide, one entry per highway SEGMENT,
  not a point — real fields are LocationDescription, Condition (a
  list — "No Report" the vast majority of the time, since this was
  checked live in August with zero active winter weather anywhere in
  the province), Visibility, Drifting, RoadwayName, and an
  EncodedPolyline (Google's polyline algorithm — MTO's own docs don't
  expose per-segment lat/lon any other way). Matched to the commute by
  decoding that polyline and distance-checking its points against
  COMMUTE_ORIGIN/COMMUTE_DESTINATION, same NEARBY_RADIUS_KM
  local_news_client.py's own event filter already uses — confirmed
  live against the real "NER - North Bay - 10" region entries
  (Highway 11, 17, 17B, 63) that their decoded points land exactly
  where they should on a real map.

- /event (v2) — the same endpoint local_news_client.py already
  fetches for its own incident/roadwork tile, given its own separate
  cache here (that module's own _fetch_road_events is a private,
  uncached helper living inside a different function's cache
  boundary, not meant to be called from outside it) and filtered
  specifically to IsFullClosure == True regardless of EventType,
  since a real closure can appear tagged as either "roadwork" or
  "accidentsAndIncidents." Events carry real Latitude/Longitude
  directly, so no polyline decode is needed for this half.

Condition/Visibility/Drifting are read as a DENYLIST of known-benign
values ("no report", "bare and dry", visibility "good", drifting
"no") rather than an allowlist of hazard strings — checked live in
August, when nothing hazardous is actually being reported anywhere in
the province, so there was no way to directly observe MTO's own real
hazard vocabulary ("snow packed," "bare and wet road" per their own
docs, but not confirmable further than that right now). A denylist
means whatever real string MTO actually uses for a genuine hazard
still surfaces correctly once winter conditions are real, rather than
silently being dropped for not matching a guessed allowlist."""

from datetime import datetime

import requests
import streamlit as st

import fetch_throttle
import groq_client
import persisted_state
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN

CONDITIONS_URL = "https://511on.ca/api/v3/get/roadconditions"
EVENTS_URL = "https://511on.ca/api/v2/get/event"

# Matches local_news_client.NEARBY_RADIUS_KM exactly — same "near
# either end of the commute, not just home" reasoning, same distance.
NEARBY_RADIUS_KM = 25

# Winter road conditions don't change minute to minute — matches this
# app's other periodic-weather-class cadences (radar_client.py's own
# 3-minute TTL is for a genuinely animated nowcast; this is closer to
# ec_forecast's 15-minute class).
CACHE_TTL_SECONDS = 15 * 60

_BENIGN_CONDITIONS = {"no report", "bare and dry", "bare", "dry"}
_BENIGN_VISIBILITY = {"good"}
_BENIGN_DRIFTING = {"no"}


def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Google's polyline algorithm — MTO's own /roadconditions
    response encodes each segment's real route geometry this way (no
    other way to get per-segment coordinates out of this endpoint).
    Standard delta-encoded, base64-ish varint algorithm, same one
    Google Maps/many mapping APIs share — not Ontario-specific."""
    points = []
    index = lat = lng = 0
    length = len(encoded)
    while index < length:
        result = shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else (result >> 1)
        lat += dlat
        result = shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else (result >> 1)
        lng += dlng
        points.append((lat / 1e5, lng / 1e5))
    return points


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Same haversine formula as local_news_client._distance_km — kept
    as its own copy rather than importing that module's private
    helper across an unrelated cache boundary; this is a plain,
    generic 7-line formula, not worth the cross-module coupling for."""
    from math import asin, cos, radians, sin, sqrt

    earth_radius_km = 6371
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def _near_commute(lat: float, lon: float) -> bool:
    return (
        _distance_km(lat, lon, COMMUTE_ORIGIN["lat"], COMMUTE_ORIGIN["lon"]) <= NEARBY_RADIUS_KM
        or _distance_km(lat, lon, COMMUTE_DESTINATION["lat"], COMMUTE_DESTINATION["lon"]) <= NEARBY_RADIUS_KM
    )


def _segment_near_commute(encoded_polyline) -> bool:
    """True if ANY point along a /roadconditions segment's real route
    geometry comes within NEARBY_RADIUS_KM of either end of the
    commute. encoded_polyline arrives as a one-element list in every
    real response seen live (["<encoded string>"]) — indexed
    defensively rather than assumed, in case MTO ever returns a bare
    string or a genuinely multi-element list for a segment with a
    real gap in it."""
    if not encoded_polyline:
        return False
    raw = encoded_polyline[0] if isinstance(encoded_polyline, list) else encoded_polyline
    if not raw:
        return False
    # A full scan, not a sampled one — a real segment can be 500+
    # points and one real close point anywhere along it is what
    # matters, not most of them. This only runs once per
    # CACHE_TTL_SECONDS (15 min), not per rerun, so a few hundred
    # cheap haversine checks across ~550 province-wide segments is
    # nowhere near worth trading correctness for.
    points = _decode_polyline(raw)
    return any(_near_commute(lat, lon) for lat, lon in points)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_conditions_raw() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(CONDITIONS_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_events_raw() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(EVENTS_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()


_last_good_conditions: list[dict] = []

# Session request: "do wet roads get the same treatment as... freezing
# rain, or no?" Honest answer at the time: no distinction at all, every
# non-benign condition rendered identically. Same gradient technique
# app.py's own UV/AQI/wildfire badges already use (_lerp_hex, a calm
# color sliding toward an urgent one) rather than a fixed lookup table
# of exact MTO strings — this module's own docstring already explains
# why: checked live in August with zero active winter conditions
# anywhere in the province, so MTO's real hazard vocabulary couldn't be
# directly observed to build an exhaustive exact-match table against.
# Keyword search is robust to whatever exact wording MTO actually uses
# ("Snow Packed," "Packed Snow," "Snowpack" all contain "pack" or
# "snow" regardless of exact phrasing) in a way a fixed table isn't.
# Order matters: severe keywords checked first so a real "snow packed"
# (which also contains "snow") lands on the severe tier, not the
# moderate one a plain "snow" match alone would suggest.
_SEVERE_KEYWORDS = ("ice", "icy", "pack", "black ice")
_MODERATE_KEYWORDS = ("snow", "slush", "drift")
# Anything non-benign but not matching either — most likely just
# "wet" — still gets flagged, never invisible, just at the calm end of
# the gradient rather than the same red as a real ice hazard.
_MILD_SEVERITY = 0.15
_MODERATE_SEVERITY = 0.55
_SEVERE_SEVERITY = 1.0
# Reduced visibility or real drifting snow compounds whatever the
# condition text alone suggests — same "either alone isn't as risky as
# both together" logic road_conditions.ice_risk's own docstring
# already establishes for temp+precip.
_VISIBILITY_BUMP = 0.2
_DRIFTING_FLOOR = 0.7


def _condition_severity(condition_text: str, visibility: str | None, drifting: bool) -> float:
    """0.0-1.0 — how severe a real, non-benign road condition reads,
    for app.py's own badge gradient. Never exactly 0 once something
    non-benign is present at all (see _MILD_SEVERITY) — a genuinely
    benign day never reaches this function in the first place
    (conditions_near_commute already filters those out entirely)."""
    text = condition_text.lower()
    severity = _MILD_SEVERITY
    if any(k in text for k in _SEVERE_KEYWORDS):
        severity = _SEVERE_SEVERITY
    elif any(k in text for k in _MODERATE_KEYWORDS):
        severity = _MODERATE_SEVERITY
    if drifting:
        severity = max(severity, _DRIFTING_FLOOR)
    if visibility:
        severity = min(1.0, severity + _VISIBILITY_BUMP)
    return severity
_last_good_closures: list[dict] = []


def conditions_near_commute() -> list[dict]:
    """[{"roadway", "location", "condition", "visibility", "drifting",
    "severity"}] for every real /roadconditions segment near the
    commute that's reporting something other than a known-benign state
    — [] on a genuinely quiet day (the real common case) or a fetch
    failure (falls back to the last good read, same graceful-
    degradation rule every other live source in this app already
    follows). "severity" (see _condition_severity) is 0.0-1.0, for
    app.py's own badge gradient — a wet road and an ice-covered one no
    longer render identically."""
    global _last_good_conditions
    try:
        raw = _fetch_conditions_raw()
    except Exception:
        return _last_good_conditions
    out = []
    for e in raw or []:
        if not _segment_near_commute(e.get("EncodedPolyline")):
            continue
        conditions = [c for c in (e.get("Condition") or []) if c and c.strip().lower() not in _BENIGN_CONDITIONS]
        visibility = e.get("Visibility")
        visibility = visibility if visibility and visibility.strip().lower() not in _BENIGN_VISIBILITY else None
        drifting_raw = e.get("Drifting")
        drifting = bool(drifting_raw and drifting_raw.strip().lower() not in _BENIGN_DRIFTING and drifting_raw.strip().lower() == "yes")
        if not conditions and not visibility and not drifting:
            continue
        condition_text = "; ".join(conditions)
        out.append(
            {
                "roadway": e.get("RoadwayName") or "",
                "location": e.get("LocationDescription") or "",
                "condition": condition_text,
                "visibility": visibility,
                "drifting": drifting,
                "severity": _condition_severity(condition_text, visibility, drifting),
            }
        )
    _last_good_conditions = out
    return out


def _real_closures(raw: list[dict]) -> list[dict]:
    """Shared filter both closures_near_commute and get_new_alerts use
    — a real, currently-active full closure (IsFullClosure == True,
    regardless of EventType — a real closure shows up tagged as either
    "roadwork" or "accidentsAndIncidents") within NEARBY_RADIUS_KM of
    either end of the commute. Keeps the ID field (get_new_alerts'
    own dedup key) rather than reshaping it away, unlike
    closures_near_commute's own public {"roadway", "description"}
    shape."""
    out = []
    for e in raw or []:
        if not e.get("IsFullClosure"):
            continue
        lat, lon = e.get("Latitude"), e.get("Longitude")
        if lat is None or lon is None or not _near_commute(lat, lon):
            continue
        description = (e.get("Description") or "").strip()
        if not description or not e.get("ID"):
            continue
        out.append(e)
    return out


def closures_near_commute() -> list[dict]:
    """[{"roadway", "description"}] for every real, currently-active
    full closure near the commute — [] on a quiet day or a fetch
    failure."""
    global _last_good_closures
    try:
        raw = _fetch_events_raw()
    except Exception:
        return _last_good_closures
    out = [{"roadway": e.get("RoadwayName") or "", "description": e["Description"].strip()} for e in _real_closures(raw)]
    _last_good_closures = out
    return out


# Per-instance (session precedent: "every single toast we get... make
# sure every terminal gets its own alert") — a real closure should
# toast on every kiosk, not just whichever instance's rerun happened to
# see it first. Baseline-gated the same "mark everything seen, don't
# dump a backlog the moment this feature ships" way news.py/
# email_client.py both already are — a closure already active before
# this existed isn't a new event.
#
# Keys are always str(ID), never the raw int — real bug, caught while
# building the status-update feature below: persisted_state round-
# trips through JSON, and JSON object keys are always strings, so an
# entry added this process's lifetime as an int key (e["ID"] straight
# off the API) would silently stop matching itself after a restart
# reloads it back as a string key — the exact same closure would then
# read as "unseen" again and re-toast. Confirmed by tracing the actual
# json.dumps/json.loads round trip in persisted_state.py.
_seen_closure_ids: dict = dict(persisted_state.load_per_instance("road_closure_seen_ids", {}))
_closure_baseline_done: bool = persisted_state.load_per_instance("road_closure_baseline_done", False)
MAX_SEEN_CLOSURES = 200


def _friendly_closure_headline(description: str) -> str:
    """A short, natural-sounding rewrite of MTO's own raw closure
    description — session request: "same conversational style that we
    have from our weather... severe weather alerts." Same shape as
    weather_alerts_bar._friendly_headline (own module, not a cross-
    import — each toast source here owns its own presentation, same
    convention every other source in this app already follows).
    Cached by groq_client.generate's own exact-prompt-text caching, so
    this only pays for a real call once per genuinely new closure, not
    every rerun. Falls back to the raw description unchanged on any AI
    outage — a real closure worded plainly beats no toast at all."""
    rewritten = groq_client.generate(
        "Rewrite this Ontario 511 road closure description as one short, casual sentence a person would "
        "actually say out loud to a friend — not a formal traffic bulletin, not a paragraph. Keep the real "
        "road, direction, location, and reason if one's given. Under 12 words. Reply with only the sentence, "
        "nothing else.\n\n" + description,
        temperature=0.6,
        max_output_tokens=80,
        account="primary",
        reasoning_effort="low",
    )
    return rewritten or description


def _spoken_closure_summary(description: str) -> str:
    """AI rewrite into a flowing sentence or two for Piper to read
    aloud — same shape as weather_alerts_bar._spoken_summary, scaled
    down: MTO's own Description field is already a compact one-liner
    (not a full multi-section bulletin the way EC's report page is),
    so there's no boilerplate to strip, just tone to smooth over.
    Falls back to the raw description unchanged on any AI outage, same
    reasoning as _friendly_closure_headline above."""
    rewritten = groq_client.generate(
        "Rewrite this Ontario 511 road closure description as a single smooth, natural-sounding sentence or "
        "two meant to be read aloud by a text-to-speech voice. Keep every real fact — which road, which "
        "direction, the exact location, and the reason if one's given. Don't add anything that isn't in the "
        "original text, and don't editorialize.\n\n" + description,
        temperature=0.3,
        max_output_tokens=150,
        account="primary",
        reasoning_effort="low",
    )
    return rewritten or description


def get_new_alerts(now: datetime) -> list[dict]:
    """A real toast the moment a genuinely NEW full closure appears
    near the commute — [] if unreachable or nothing new. "kind":
    "weather" deliberately, same reasoning as lightning_client.
    get_new_alerts's own docstring — reuses weather_alerts_bar.
    render_alert_bar as-is, riding the same top-priority toast lane,
    same styling, same voice treatment, at zero new CSS/JS cost.
    "warning" severity, not "statement" — a closure directly blocking
    the actual commute is a real hazard, not just background info.

    Session request: "same conversational style that we have from our
    weather... severe weather alerts" — headline/summary are now AI-
    rewritten (see _friendly_closure_headline/_spoken_closure_summary
    above) and both open with a deterministic "This is a road closure"
    lead-in, same "built in code, not left to the AI prompt" reasoning
    as weather_alerts_bar's own type prefix (same session, same day) —
    a should from a prompt isn't the same guarantee as code always
    prepending it. No Warning/Watch/Advisory/Statement-style variation
    here (511 doesn't have EC's tier vocabulary for this), so the
    lead-in is fixed rather than computed. The repeating "still in effect" half
    of "same style... every time it is updated" lives in
    get_status_updates below, not here — this function only ever fires
    once, for a genuinely new closure."""
    global _seen_closure_ids, _closure_baseline_done
    try:
        raw = _fetch_events_raw()
    except Exception:
        return []
    closures = _real_closures(raw)

    # Checked BEFORE the "nothing active" early-return below, not
    # after — the real common case is zero closures active near the
    # commute at any given moment (confirmed live), so gating this on
    # closures being non-empty would mean the baseline never actually
    # completes until the first real closure happens to exist, and
    # THAT one would then get wrongly swallowed as "baseline" instead
    # of correctly toasting as the new event it actually is. One-time,
    # on the first call ever, regardless of what's active right then.
    if not _closure_baseline_done:
        for e in closures:
            _seen_closure_ids[str(e["ID"])] = True
        _closure_baseline_done = True
        persisted_state.save_per_instance("road_closure_seen_ids", _seen_closure_ids)
        persisted_state.save_per_instance("road_closure_baseline_done", True)
        return []

    if not closures:
        return []

    alerts = []
    for e in closures:
        closure_id = str(e["ID"])
        if closure_id in _seen_closure_ids:
            continue
        _seen_closure_ids[closure_id] = True
        if len(_seen_closure_ids) > MAX_SEEN_CLOSURES:
            _seen_closure_ids.pop(next(iter(_seen_closure_ids)))
        description = e["Description"].strip()
        headline = f"Road Closure: {_friendly_closure_headline(description)}"
        alerts.append(
            {
                "kind": "weather",
                "severity": "warning",
                "label": "Road Closure",
                "headline": headline,
                "summary": f"This is a road closure. {_spoken_closure_summary(description)}",
            }
        )
    if alerts:
        persisted_state.save_per_instance("road_closure_seen_ids", _seen_closure_ids)
    return alerts


# Session request: "I want an update every fifteen minutes. Basically
# saying this alert is still in effect, but then mute it overnight."
STATUS_UPDATE_INTERVAL_SECONDS = 15 * 60
# Same 9:30pm-4:30am window night_mode.py's own screen uses (see
# app.py's own _night_mode_day_start/_night_mode_day_end) — duplicated
# here rather than imported since this only needs the two hour/minute
# boundaries, not any of night_mode's own render state. Only gates the
# REPEATING "still in effect" ping below — a brand-new closure still
# announces itself regardless of hour via get_new_alerts above, same
# "a genuinely new hazard doesn't get silenced by the clock" rule every
# other weather-kind toast in this app already follows; it's the
# repeating reminder about something already known that's muted, not
# the first notice.
def _muted_overnight(now: datetime) -> bool:
    start = now.replace(hour=21, minute=30, second=0, microsecond=0)
    end = now.replace(hour=4, minute=30, second=0, microsecond=0)
    return now >= start or now < end


_last_status_update_at: dict = dict(persisted_state.load_per_instance("road_closure_status_at", {}))


def get_status_updates(now: datetime) -> list[dict]:
    """A repeating "still in effect" ping every STATUS_UPDATE_INTERVAL_
    SECONDS for as long as a real closure stays active near the
    commute, muted overnight. Deterministic text, no AI call — there's
    nothing new to say every 15 minutes beyond "still going," same
    "don't over-rewrite a repeating ping" restraint weather_alerts_bar.
    get_storm_proximity_alerts's own milestone toasts already
    established (that session's own "it repeats itself every time
    there's an update, which is fine" — the repetition itself is fine,
    a fresh AI paragraph every 15 minutes for the same fact wouldn't
    be).

    The first time this function ever sees a given closure, it seeds
    _last_status_update_at for it WITHOUT firing — get_new_alerts
    above already announced it; this function's own first real ping
    should land a genuine 15 minutes later, not immediately alongside
    the "just detected" toast on the very same tick."""
    global _last_status_update_at
    if _muted_overnight(now):
        return []
    try:
        raw = _fetch_events_raw()
    except Exception:
        return []
    closures = _real_closures(raw)
    if not closures:
        return []

    now_ts = now.timestamp()
    alerts = []
    changed = False
    for e in closures:
        closure_id = str(e["ID"])
        last_at = _last_status_update_at.get(closure_id)
        if last_at is None:
            _last_status_update_at[closure_id] = now_ts
            changed = True
            continue
        if (now_ts - last_at) < STATUS_UPDATE_INTERVAL_SECONDS:
            continue
        _last_status_update_at[closure_id] = now_ts
        changed = True
        description = e["Description"].strip()
        roadway = e.get("RoadwayName")
        headline = f"Road Closure updated: Hwy {roadway} still closed" if roadway else "Road Closure updated: still closed"
        alerts.append(
            {
                "kind": "weather",
                "severity": "warning",
                "label": "Road Closure",
                "headline": headline,
                "summary": f"This road closure has been updated. It's still in effect. {description}",
            }
        )
    if changed:
        if len(_last_status_update_at) > MAX_SEEN_CLOSURES:
            _last_status_update_at.pop(next(iter(_last_status_update_at)))
        persisted_state.save_per_instance("road_closure_status_at", _last_status_update_at)
    return alerts
