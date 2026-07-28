"""Storm-proximity phase (approaching / here / leaving) for the current
severe weather alert affecting this region, from Environment Canada's
own expected start/end times.

Session request: "I wanna have red govee flashes for when the storm is
approaching and toast alerts for when the storm gets closer every like
5-10 mins... same thing for when the storm is leaving... occasional
toasts for when its approaching, and then solid red at like 30% for
when its here." Clarified: "this is based on you pulling the expected
start and end time from environment canadas alerts."

ec_alerts.py's own ATOM feed (weather.gc.ca/rss/battleboard) doesn't
carry timing fields at all — just an issue timestamp in plain text
("Issued: 9:33 PM EDT..."). Pulled instead from MSC GeoMet's
weather-alerts OGC API (api.weather.gc.ca), a separate, richer EC
product: structured JSON, filterable directly by region name via a
query param (feature_name_en — confirmed live to be the exact same
"North Bay - Powassan - Mattawa" string ec_alerts.py's own feed already
displays for this region, no geocode translation needed), carrying
validity_datetime (when EC expects the hazard to actually begin here)
and event_end_datetime (when EC expects it to have passed) — genuinely
distinct from the warning PRODUCT's own expiration_datetime, which runs
later than the event itself is actually expected to last (confirmed
live against a real severe thunderstorm warning: expiration_datetime
3 hours out, event_end_datetime only 2).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st

import fetch_throttle
from config import EC_ALERT_REGION_NAME, TIMEZONE

ALERTS_URL = "https://api.weather.gc.ca/collections/weather-alerts/items"
# Matches ec_alerts.py's own cadence — this feeds the same real-time
# proximity/light logic, no reason for a different refresh rate.
CACHE_TTL_SECONDS = 3 * 60

_last_good_feature: dict | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_raw() -> dict | None:
    fetch_throttle.wait_turn()
    resp = requests.get(ALERTS_URL, params={"f": "json", "feature_name_en": EC_ALERT_REGION_NAME}, timeout=10)
    resp.raise_for_status()
    features = resp.json().get("features") or []
    return features[0]["properties"] if features else None


def _fetch() -> dict | None:
    """None whenever nothing's active for this region right now — same
    _last_good_X fallback pattern every other client in this app uses
    for a transient failure specifically (a genuinely empty result, not
    a fetch error, is trusted as-is: an alert that really just ended
    shouldn't keep the storm-phase treatment stuck on using stale
    data)."""
    global _last_good_feature
    try:
        result = _fetch_raw()
    except Exception:
        return _last_good_feature
    _last_good_feature = result
    return result


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


# How long past event_end_datetime the "leaving" phase holds before this
# reverts to nothing at all. EC's own expected-end time is a real
# estimate, not a hard cutoff, and the warning PRODUCT itself
# (expiration_datetime) routinely runs well past it — this is a
# deliberately short, fixed tail rather than trusting either extreme (an
# unmoving multi-hour hold on the product's own lapse, or snapping off
# the instant the estimate says so, before the tail of the storm has
# actually cleared).
LEAVING_TAIL_MINUTES = 30

# Only these severities (weather_alerts_bar._severity's own tiers) get
# the storm-proximity Govee/toast treatment — a routine Special Weather
# Statement or a Watch isn't "a storm bearing down," full stop, even
# though ec_alerts.py's own alert selection still shows it in the
# persistent banner/one-shot toast for its own sake.
STORM_SEVERITIES = ("extreme", "warning")

# Session follow-up: "make sure this whole crazy thing only triggers for
# actually serious events not heat warnings and shit." STORM_SEVERITIES
# above already excludes most of those (weather_alerts_bar._severity
# puts a Warning-tier heat/cold/frost/fog/rainfall/snowfall/air-quality
# alert into "warning-moderate", not "warning") — but that classification
# exists for a different purpose (banner coloring), and a wind/blizzard/
# winter-storm/ice-storm/flood Warning would still pass it. This is a
# second, independent gate by hazard TYPE specifically, kept self-
# contained here rather than importing weather_alerts_bar's own hazard
# lists, so a future change to that unrelated classification can't
# silently widen (or narrow) what wakes the room and flashes the lights.
# Deliberately narrow — genuinely violent, fast-arriving weather with a
# real "front" EC's own validity/end timing meaningfully describes, the
# same category this feature was built and tested against (a real
# severe thunderstorm warning).
STORM_HAZARD_TERMS = ("thunderstorm", "tornado", "hurricane", "tropical storm", "tsunami")


def storm_phase(now: datetime, title: str, severity: str) -> dict | None:
    """{"phase": "approaching"|"here"|"leaving", "minutes": float,
    "target": datetime} for the region's current alert, using EC's own
    expected start/end times — None whenever there's genuinely nothing
    active for this region, the feature's own timing fields are missing
    (rare, but real — not every alert type populates them), `severity`
    isn't storm-grade (see STORM_SEVERITIES), or `title`'s hazard isn't
    in STORM_HAZARD_TERMS (see that constant's own comment — a second,
    independent narrowing by hazard type, not just tier). `minutes` is
    minutes until the NEXT phase transition (start, for "approaching";
    end, for "here"; the tail's own expiry, for "leaving") — floored at
    0 rather than going negative if a rerun lands a beat after the real
    transition instant; `target` is that same transition instant as an
    aware datetime, for a caller that wants to drive a real per-second
    countdown (see app.py's live-countdown ticker) rather than a value
    that's already stale by the time of the next 5s rerun. `now` may be
    naive (app.py's own convention — passed in already local to
    TIMEZONE with tzinfo stripped, same as every other caller in this
    app threading its own `now` through) or aware; a naive value is
    assumed to already be in TIMEZONE rather than compared as-is against
    EC's own aware UTC timestamps, which would raise TypeError —
    confirmed live this exact mismatch has bitten this app before (see
    groq_client._in_pause_window's own comment)."""
    if severity not in STORM_SEVERITIES:
        return None
    if not any(term in title.lower() for term in STORM_HAZARD_TERMS):
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo(TIMEZONE))
    feature = _fetch()
    if not feature:
        return None
    start = _parse_dt(feature.get("validity_datetime"))
    end = _parse_dt(feature.get("event_end_datetime"))
    if start is None or end is None:
        return None
    if now < start:
        return {"phase": "approaching", "minutes": max(0.0, (start - now).total_seconds() / 60), "target": start}
    if now < end:
        return {"phase": "here", "minutes": max(0.0, (end - now).total_seconds() / 60), "target": end}
    tail_end = end + timedelta(minutes=LEAVING_TAIL_MINUTES)
    if now < tail_end:
        return {"phase": "leaving", "minutes": max(0.0, (tail_end - now).total_seconds() / 60), "target": tail_end}
    return None
