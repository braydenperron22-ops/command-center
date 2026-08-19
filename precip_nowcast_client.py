"""Minute-by-minute precipitation nowcast via Xweather — session
request: "does RainViewer have a future forecast... similar to Apple?"
(no — their nowcast was discontinued Jan 1 2026, see radar_client.py's
own docstring) followed by "look into other sources" and "xweather,
but make sure not to go over the rate limit."

Reuses the exact same XWEATHER_CLIENT_ID/XWEATHER_CLIENT_SECRET
lightning_client.py already needs — one Xweather account, one shared
15,000-calls/month free-tier budget, so the two modules' own cadences
have to be sized together, not independently:
  lightning_client.py: 5-minute cache -> 8,640 calls/month
  this module:        10-minute cache -> 4,320 calls/month
  combined:                              12,960 calls/month
— comfortably under 15,000 with ~2,000/month of real headroom left for
API hiccups, local testing, and whatever else ends up on this same
account later. A shorter TTL here would read fresher, but the
underlying nowcast model itself doesn't update on a sub-10-minute
cadence anyway (matches RainViewer's own old past-radar refresh rate,
and Pirate Weather's HRRR-derived nowcast — see the session's own
research — steps in 15-minute increments), so there's no real signal
being traded away, only budget being spent for no reason.

Session report, once XWEATHER_CLIENT_ID/SECRET were actually added to
secrets.toml: "the rain nowcast feature... isn't populating when rain
is coming... check those." Root cause was simpler than a parsing bug —
the two secrets had genuinely never been added, so _configured() was
False and this had never once reached the real API. Verified live
once the real credentials were in place: a real 200/success response,
61 real minute-by-minute periods parsed correctly through
minutely_forecast() end to end.
"""

from datetime import datetime, timedelta

import requests
import streamlit as st

import persisted_state
from config import WEATHER_LAT, WEATHER_LON

CONDITIONS_URL = "https://data.api.xweather.com/conditions/closest"
CACHE_TTL_SECONDS = 10 * 60
DEFAULT_THRESHOLD_MM = 0.1


def _configured() -> bool:
    return bool(st.secrets.get("XWEATHER_CLIENT_ID")) and bool(st.secrets.get("XWEATHER_CLIENT_SECRET"))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_minutely_raw() -> dict | None:
    resp = requests.get(
        CONDITIONS_URL,
        params={
            "client_id": st.secrets.get("XWEATHER_CLIENT_ID"),
            "client_secret": st.secrets.get("XWEATHER_CLIENT_SECRET"),
            "p": f"{WEATHER_LAT},{WEATHER_LON}",
            "filter": "minutelyprecip",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def minutely_forecast() -> list[dict] | None:
    """[{"minute", "precip_rate_mm", "precip_type"}, ...] for the next
    ~60 minutes, oldest (now) first, or None if unconfigured/
    unreachable/empty. "minute" is 0-indexed minutes from now, not a
    real clock time — callers that need a clock time can derive it
    from datetime.now() themselves; nothing here needs to agree with
    that instant precisely enough to carry it as data."""
    if not _configured():
        return None
    try:
        raw = _fetch_minutely_raw()
    except Exception:
        return None
    if not raw or not raw.get("success"):
        return None
    response = raw.get("response") or []
    periods = (response[0] if isinstance(response, list) else response) or {}
    periods = (periods.get("periods") if isinstance(periods, dict) else None) or []
    if not periods:
        return None
    out = []
    for i, p in enumerate(periods):
        rate = p.get("precipRateMM")
        if rate is None:
            continue
        out.append({"minute": i, "precip_rate_mm": float(rate), "precip_type": p.get("precipType")})
    return out or None


def rain_starting_in_minutes(forecast: list[dict], threshold_mm: float = DEFAULT_THRESHOLD_MM) -> int | None:
    """How many minutes from now the first real precipitation begins,
    or None if either nothing's forecast in the window or it's already
    raining right now (minute 0 already over threshold — "starting"
    doesn't apply to something already happening)."""
    if not forecast or forecast[0]["precip_rate_mm"] >= threshold_mm:
        return None
    hit = next((p for p in forecast if p["precip_rate_mm"] >= threshold_mm), None)
    return hit["minute"] if hit else None


def rain_ending_in_minutes(forecast: list[dict], threshold_mm: float = DEFAULT_THRESHOLD_MM) -> int | None:
    """How many minutes from now precipitation already happening right
    now (minute 0 over threshold) is forecast to drop back below it,
    or None if it isn't raining right now, or it's forecast to keep
    raining for the entire window."""
    if not forecast or forecast[0]["precip_rate_mm"] < threshold_mm:
        return None
    hit = next((p for p in forecast if p["precip_rate_mm"] < threshold_mm), None)
    return hit["minute"] if hit else None


# Session request: "if you could aggregate it so that... if there's
# maybe not anything in the next ten minutes, but there's something
# further out, aggregate it to the current time plus how long it's
# expected to show up and then start that alert from there so that we
# don't have any excuses where it just wasn't in the proper window."
# 15 minutes: this module's own docstring already notes the underlying
# nowcast model steps in ~15-minute increments, so a genuinely real
# prediction shouldn't drift by more than that between two
# CACHE_TTL_SECONDS-apart polls.
_ALERT_BUCKET_MINUTES = 15


def _round_target_bucket(now: datetime, minutes_out: int) -> str:
    """A stable dedup identity for a predicted event `minutes_out`
    minutes from `now` — the real target clock time, rounded to the
    nearest _ALERT_BUCKET_MINUTES. Two polls 10 minutes apart
    predicting what's really the same rain system round to the same
    bucket even though "minutes from now" itself keeps shrinking
    between them (45 min out, then 35, then 25...) — this only
    re-alerts for a genuinely different prediction, not the same one
    refreshing."""
    target = now + timedelta(minutes=minutes_out)
    rounded_minutes = round(target.minute / _ALERT_BUCKET_MINUTES) * _ALERT_BUCKET_MINUTES
    rounded = target.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=rounded_minutes)
    return rounded.isoformat()


# Per-instance (session precedent: "every single toast we get... make
# sure every terminal gets its own alert") — a real rain onset should
# toast on every kiosk reading the same forecast, not just whichever
# instance's rerun happened to see it first.
_seen_starting_bucket: str | None = persisted_state.load_per_instance("precip_nowcast_seen_starting", None)
_was_raining: bool = persisted_state.load_per_instance("precip_nowcast_was_raining", False)


def get_new_alerts(now: datetime) -> list[dict]:
    """Two independent real signals, each toasting once per genuine
    event, [] if unconfigured/unreachable/nothing new:

    1. A heads-up the moment ANY future rain onset is found anywhere in
    the ~60-minute nowcast horizon, however far out — see
    _round_target_bucket's own comment for why this doesn't wait for a
    later refresh to catch it "in the window."

    2. The real moment it actually starts (or stops) raining — a plain
    "wasn't raining last check, is now" state transition, independent
    of whether the heads-up above ever fired, so a rain event that
    builds up differently than predicted (or one the heads-up simply
    missed) still gets a real toast the instant it's genuinely
    happening. rain_starting_in_minutes never actually returns 0 once
    it's really raining (see its own docstring — "starting" stops
    applying at that point), so this transition is the only way "it's
    raining now" ever gets a toast of its own.

    "kind": "weather" deliberately, same reasoning as lightning_client.
    get_new_alerts's own docstring — reuses weather_alerts_bar.
    render_alert_bar as-is (app.py's toast dispatch is by "kind", not
    which module produced it), so this rides the exact same top-
    priority lane, the same .weather-alert-bar-statement CSS (glow
    pulse and the fixed reveal-wipe z-index included, no new styling
    needed), and the same KIOSK_WEATHER_VOICE_SEL voice treatment —
    already listed there for every severity including "statement" — at
    zero extra wiring cost. "Rain has stopped" is the one silent
    variant: real news, but nothing actionable enough to earn a chime
    the way "rain's coming" or "it's raining now" do."""
    global _seen_starting_bucket, _was_raining
    forecast = minutely_forecast()
    if not forecast:
        return []

    alerts = []
    is_raining_now = forecast[0]["precip_rate_mm"] >= DEFAULT_THRESHOLD_MM

    starting = rain_starting_in_minutes(forecast)
    if starting is not None:
        bucket = _round_target_bucket(now, starting)
        if bucket != _seen_starting_bucket:
            _seen_starting_bucket = bucket
            persisted_state.save_per_instance("precip_nowcast_seen_starting", bucket)
            alerts.append(
                {
                    "kind": "weather",
                    "severity": "statement",
                    "label": "Rain",
                    "headline": f"Rain in {starting} min",
                    "summary": f"Rain expected in {starting} minutes.",
                }
            )
    elif _seen_starting_bucket is not None:
        # Nothing currently forecast to start — free to alert again for
        # a genuinely new future prediction once one actually reappears.
        _seen_starting_bucket = None
        persisted_state.save_per_instance("precip_nowcast_seen_starting", None)

    if is_raining_now != _was_raining:
        _was_raining = is_raining_now
        persisted_state.save_per_instance("precip_nowcast_was_raining", is_raining_now)
        if is_raining_now:
            alerts.append(
                {
                    "kind": "weather",
                    "severity": "statement",
                    "label": "Rain",
                    "headline": "Rain has started",
                    "summary": "It has started raining.",
                }
            )
        else:
            alerts.append({"kind": "weather", "severity": "statement", "label": "Rain", "headline": "Rain has stopped", "silent": True})

    return alerts
