"""Nearby lightning strikes via Xweather's free-tier lightning API —
session request: "I just want there to be... a breaking news alert
when there's lightning within... ten kilometers on my location."

Xweather (formerly AerisWeather) was picked over Blitzortung.org's own
free community feed after checking both live: Blitzortung only offers
this as a live push feed (a raw websocket to their own servers, which
their own terms say a real app shouldn't hit directly, or a third-
party MQTT relay) — either way this app's first-ever persistent
background connection, just for one feature. Xweather's free tier
(15,000 calls/month, no card) is a plain request/response REST
endpoint instead, which fits the exact same "fetch, cache with a TTL,
re-poll next rerun" shape every other data source in this app already
uses — no new architecture needed.

XWEATHER_CLIENT_ID/XWEATHER_CLIENT_SECRET identify this app to Xweather
(https://www.xweather.com — free account, register an "app" there to
get both, then add them to .streamlit/secrets.toml the same way every
other paired client_id/secret in this app already is). Degrades to
"nothing" (same as every other unconfigured integration here) when
either is missing, rather than erroring.
"""

import time
from datetime import datetime

import requests
import streamlit as st

import data_health
import ntfy_client
import persisted_state
from config import WEATHER_LAT, WEATHER_LON

LIGHTNING_URL = "https://data.api.xweather.com/lightning/closest"
RADIUS_KM = 10
# Xweather's own standard-tier limit — "closest" only ever looks back 5
# minutes on the free tier (a longer window needs their paid Enterprise
# add-on), so there's no real freshness gained by polling faster than
# that window itself refreshes. At this cadence, ONE process running
# continuously costs 12 calls/hour * 24 * 30 = 8,640/month — see
# _SHARED_CACHE_KEY's own comment for why the real number used to run
# well past that.
CACHE_TTL_SECONDS = 5 * 60

# Session report: "we hit the rate limit on xweather... re-evaluate how
# to save credits." Root cause wasn't this TTL (already the fastest
# cadence worth polling at, see above) — it was that the real HTTP call
# lived behind a bare st.cache_data, which is per-PROCESS memory: it
# resets to empty on every process restart, not just every
# CACHE_TTL_SECONDS. This app auto-deploys on every git push (confirmed
# live), and this project alone pushes real commits often enough that
# a bare in-memory cache could plausibly restart-and-refetch far more
# often than its own 5-minute TTL ever intended — a redeploy 30 seconds
# after a real fetch used to mean an immediate second real fetch,
# regardless of how fresh the first one still was. Checked here,
# inside the same st.cache_data-gated function (so this Upstash read
# is itself already throttled to once per CACHE_TTL_SECONDS per
# process, not every 5s rerun) — a real Xweather call now only fires if
# the SHARED cache is also actually stale, which survives a restart.
# (Checked live whether local dev-preview testing was ALSO
# double-dipping into this same shared cache, since persisted_state.py
# documents that as the intended multi-instance behavior — it isn't:
# this machine's own .streamlit/secrets.toml has no Upstash credentials
# configured at all, so local runs fall back to a private local JSON
# file, confirmed by checking that file directly. If a second Upstash-
# configured instance (a real second kiosk, or a dev box later given
# real Upstash credentials) ever runs alongside production, this same
# fix means it would share the cache too — just not verified as an
# actual contributor to the rate limit that was hit, only the
# redeploy-reset mechanism above was.)
_SHARED_CACHE_KEY = "xweather_lightning_closest"


def _configured() -> bool:
    return bool(st.secrets.get("XWEATHER_CLIENT_ID")) and bool(st.secrets.get("XWEATHER_CLIENT_SECRET"))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_closest_raw() -> dict | None:
    cached = persisted_state.load(_SHARED_CACHE_KEY, None)
    if isinstance(cached, dict) and "at" in cached and time.time() - cached["at"] < CACHE_TTL_SECONDS:
        data_health.record_success("lightning")
        return cached.get("value")
    resp = requests.get(
        LIGHTNING_URL,
        params={
            "client_id": st.secrets.get("XWEATHER_CLIENT_ID"),
            "client_secret": st.secrets.get("XWEATHER_CLIENT_SECRET"),
            # Session request: "check those" — confirmed live against a
            # real Xweather account (once XWEATHER_CLIENT_ID/SECRET were
            # actually added) that separate lat/lon params get a real
            # "no_location: A location was not provided" error back —
            # Xweather's "closest" action wants a single combined point
            # instead, same "p" parameter precip_nowcast_client.py's own
            # request already used correctly. Verified this exact change
            # against the live API before shipping it: 200, success,
            # response returned.
            "p": f"{WEATHER_LAT},{WEATHER_LON}",
            "radius": f"{RADIUS_KM}km",
        },
        timeout=10,
    )
    resp.raise_for_status()
    value = resp.json()
    persisted_state.save(_SHARED_CACHE_KEY, {"at": time.time(), "value": value})
    data_health.record_success("lightning")
    return value


def _closest_strike_within_radius() -> dict | None:
    """The raw strike record for the closest hit within RADIUS_KM, or
    None — no strike that close in the last 5 minutes, the feed isn't
    configured/reachable, or Xweather's own envelope reports failure.
    Shared by nearby_strike() and get_new_alerts() so both read off the
    exact same cached fetch rather than risking two independent calls
    ever disagreeing with each other mid-rerun."""
    if not _configured():
        return None
    try:
        raw = _fetch_closest_raw()
    except Exception:
        return None
    if not raw or not raw.get("success"):
        return None
    strikes = raw.get("response") or []
    if not strikes:
        return None
    strike = strikes[0]
    distance_km = (strike.get("relativeTo") or {}).get("distanceKM")
    if distance_km is None or distance_km > RADIUS_KM:
        return None
    return strike


def nearby_strike() -> dict | None:
    """{"distance_km", "bearing", "type", "age_seconds"} for the
    closest strike within RADIUS_KM right now, or None. "type" is
    Xweather's own "cg" (cloud-to-ground) or "ic" (intra-cloud, doesn't
    reach the ground) — not filtered out here since a viewer glancing
    at "how close is the storm" cares about proximity regardless of
    which kind, but available for a caller that wants to distinguish."""
    strike = _closest_strike_within_radius()
    if strike is None:
        return None
    relative = strike.get("relativeTo") or {}
    ob = strike.get("ob") or {}
    return {
        "distance_km": relative.get("distanceKM"),
        "bearing": relative.get("bearingENG"),
        "type": (ob.get("pulse") or {}).get("type"),
        "age_seconds": ob.get("age"),
    }


# Persisted (not a plain module-level set) so a redeploy/restart can't
# re-toast a strike this process already showed — same reasoning and
# shape as weather_alerts_bar._seen_alert_keys. Per-instance, same as
# every other toast dedup in this app ("every terminal gets its own
# alert").
MAX_SEEN_STRIKES = 50
_seen_strike_ids: dict = dict(persisted_state.load_per_instance("lightning_seen_strikes", {}))


def get_new_alerts(now: datetime) -> list[dict]:
    """New-strike toasts, same generic {"kind", "severity", "label",
    "headline", ...} shape the toast queue's every other source already
    uses (see weather_alerts_bar.get_new_alerts/news.get_new_alerts).
    "kind": "weather" deliberately — app.py's own _alert_priority ranks
    weather above even commute ("arguably the most important part of
    the dashboard"), and a strike within RADIUS_KM happening right now
    is exactly that kind of genuinely urgent, not a routine headline.
    Reuses weather_alerts_bar.render_alert_bar as-is (app.py's toast
    dispatch is by "kind", not by which module produced the alert) —
    no new render function or CSS needed, the standard "warning"-tier
    red bar already fits.

    Deduped by the strike's own id so the same strike doesn't re-toast
    every rerun for the ~5 minutes Xweather's standard tier keeps
    returning it as "closest.\""""
    strike = _closest_strike_within_radius()
    if strike is None:
        return []
    strike_id = strike.get("id")
    if not strike_id or strike_id in _seen_strike_ids:
        return []
    _seen_strike_ids[strike_id] = True
    if len(_seen_strike_ids) > MAX_SEEN_STRIKES:
        _seen_strike_ids.pop(next(iter(_seen_strike_ids)))
    persisted_state.save_per_instance("lightning_seen_strikes", _seen_strike_ids)

    relative = strike.get("relativeTo") or {}
    distance_km = relative.get("distanceKM")
    bearing = relative.get("bearingENG")
    where = f" {bearing} of you" if bearing else ""
    headline = f"Lightning strike {distance_km:.1f} km{where}"
    # Session request: "make it so that literally all of the important
    # things get an alert." "high" not "urgent" — a real strike this
    # close is genuinely worth knowing, but an active storm can produce
    # several distinct strikes within RADIUS_KM in quick succession, and
    # this toast is already deliberately silent on-screen (no chime/
    # voice, see "silent" below) for that same "don't be naggy about a
    # repeatable event" reason — the phone push should read the same way.
    ntfy_client.send(title="Lightning", message=headline, priority="high", tags="warning")
    return [
        {
            "kind": "weather",
            "severity": "warning",
            "label": "Lightning",
            "headline": headline,
            # Session request: "make it so it doesn't speak... not
            # audible" — no "summary" (nothing to synthesize/read aloud)
            # and "silent": True (weather_alerts_bar.render_alert_bar's
            # own data-silent attribute) so app.py's kioskCheckToastChime
            # skips the chime bell too, not just the voice. The toast
            # still slides in and shows visually exactly like any other.
            "silent": True,
        }
    ]
