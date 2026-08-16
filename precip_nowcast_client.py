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

NOT YET LIVE-VERIFIED against a real Xweather account — built from
their documented request shape (client_id/client_secret + p=lat,lon +
filter=minutelyprecip on the conditions endpoint), same as radar_
client.py originally was before its own live test. Needs a real check
once XWEATHER_CLIENT_ID/SECRET are actually in secrets.toml.
"""

from datetime import datetime

import requests
import streamlit as st

from config import WEATHER_LAT, WEATHER_LON

CONDITIONS_URL = "https://data.api.xweather.com/conditions/closest"
CACHE_TTL_SECONDS = 10 * 60


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


def rain_starting_in_minutes(forecast: list[dict], threshold_mm: float = 0.1) -> int | None:
    """How many minutes from now the first real precipitation begins,
    or None if either nothing's forecast in the window or it's already
    raining right now (minute 0 already over threshold — "starting"
    doesn't apply to something already happening)."""
    if not forecast or forecast[0]["precip_rate_mm"] >= threshold_mm:
        return None
    hit = next((p for p in forecast if p["precip_rate_mm"] >= threshold_mm), None)
    return hit["minute"] if hit else None


def rain_ending_in_minutes(forecast: list[dict], threshold_mm: float = 0.1) -> int | None:
    """How many minutes from now precipitation already happening right
    now (minute 0 over threshold) is forecast to drop back below it,
    or None if it isn't raining right now, or it's forecast to keep
    raining for the entire window."""
    if not forecast or forecast[0]["precip_rate_mm"] < threshold_mm:
        return None
    hit = next((p for p in forecast if p["precip_rate_mm"] < threshold_mm), None)
    return hit["minute"] if hit else None
