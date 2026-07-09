"""Reactive policy for the bedroom Govee light + plug: what state they
SHOULD be in given the same phase/market/news signals already driving the
dashboard's own visuals. app.py calls sync_lights()/sync_plug() once per
rerun; everything here decides whether that actually needs an API call.

Govee's API has real per-day rate limits and this script reruns every
second (clock tick), so desired state is recomputed locally (free) each
rerun, but an HTTP call only fires when that desired state has actually
changed AND enough time has passed since the last call — otherwise a
value that flaps near a threshold (e.g. the market sitting right at 0%)
could burn the daily quota in minutes.
"""

import time

import streamlit as st

import govee_client
from config import GOVEE_LIGHT, GOVEE_PLUG

MIN_CALL_GAP_SECONDS = 10
# The breaking-news pulse alternates color roughly once per second (capped
# by the dashboard's own 1-second rerun cadence anyway), which the standard
# 10s gap would mostly swallow — but breaking alerts are rare (classify()
# only flags a handful of headlines a day), so a few extra calls during one
# short pulse is negligible against the daily quota the 10s gap protects.
FLASH_CALL_GAP_SECONDS = 1
FLASH_SECONDS = 4  # how long a breaking-news pulse holds before reverting

DAY_BRIGHTNESS = 45
MARKET_UP_COLOR = (0, 255, 0)
MARKET_DOWN_COLOR = (255, 0, 0)
MARKET_NEUTRAL_COLOR = (255, 255, 255)
MARKET_FLAT_BAND = 0.1  # +/- percent treated as flat, avoids flicker right at 0
FLASH_RED = (255, 0, 0)
FLASH_WHITE = (255, 255, 255)
FLASH_BRIGHTNESS = 100


def _desired_base_state(market_intraday_pct: float | None) -> tuple[tuple[int, int, int], int]:
    if market_intraday_pct is None or abs(market_intraday_pct) < MARKET_FLAT_BAND:
        return MARKET_NEUTRAL_COLOR, DAY_BRIGHTNESS
    if market_intraday_pct > 0:
        return MARKET_UP_COLOR, DAY_BRIGHTNESS
    return MARKET_DOWN_COLOR, DAY_BRIGHTNESS


def _apply_power(on: bool) -> bool:
    """Returns True once the light's power state is confirmed on/off —
    either just sent, or already matching cache. sync_lights only moves
    on to color/brightness once this is True, so a still-throttled power
    call can't be raced by a color call that assumes power is already up."""
    if st.session_state.get("govee_light_powered_on") == on:
        return True
    if time.time() - st.session_state.get("govee_last_call_ts", 0) < MIN_CALL_GAP_SECONDS:
        return False
    if govee_client.set_power(GOVEE_LIGHT, on):
        st.session_state["govee_light_powered_on"] = on
        st.session_state["govee_last_call_ts"] = time.time()
        if not on:
            # Force a fresh color/brightness send next time it powers
            # back on, rather than trusting whatever it powers on with.
            st.session_state["govee_light_applied"] = None
        return True
    return False


def _apply_light(color: tuple[int, int, int], brightness: int, min_gap: float = MIN_CALL_GAP_SECONDS) -> None:
    desired = (color, brightness)
    if st.session_state.get("govee_light_applied") == desired:
        return
    if time.time() - st.session_state.get("govee_last_call_ts", 0) < min_gap:
        return
    govee_client.set_color(GOVEE_LIGHT, color)
    govee_client.set_brightness(GOVEE_LIGHT, brightness)
    st.session_state["govee_light_applied"] = desired
    st.session_state["govee_last_call_ts"] = time.time()


def sync_lights(phase: str, market_intraday_pct: float | None, breaking_alert_elapsed: float | None) -> None:
    """Call once per rerun. Light follows the exact same sunset/sunrise
    pattern as the plug — off at night, no exceptions (including no
    breaking-news flash overnight, since the point is an uninterrupted
    rest period). During the day it stays on and reactive: market-direction
    color normally, or an alternating red/white pulse while
    `breaking_alert_elapsed` is not None (the seconds elapsed since a fresh
    breaking alert started showing — the caller already tracks each
    alert's shown_at for the toast bar, so this reuses that instead of
    tracking its own copy; None means no active breaking alert)."""
    if not st.secrets.get("GOVEE_API_KEY"):
        return
    if phase == "night":
        _apply_power(False)
        return
    if not _apply_power(True):
        return
    if breaking_alert_elapsed is not None:
        color = FLASH_RED if int(breaking_alert_elapsed) % 2 == 0 else FLASH_WHITE
        _apply_light(color, FLASH_BRIGHTNESS, min_gap=FLASH_CALL_GAP_SECONDS)
        return
    color, brightness = _desired_base_state(market_intraday_pct)
    _apply_light(color, brightness)


def sync_plug(phase: str) -> None:
    """Off at sunset, on at sunrise — `phase` is the same day/night value
    already derived from real sunrise/sunset for the dashboard's own
    night-dim, so the plug follows the exact same transition."""
    if not st.secrets.get("GOVEE_API_KEY"):
        return
    want_on = phase != "night"
    if st.session_state.get("govee_plug_applied") == want_on:
        return
    if time.time() - st.session_state.get("govee_plug_last_call_ts", 0) < MIN_CALL_GAP_SECONDS:
        return
    if govee_client.set_power(GOVEE_PLUG, want_on):
        st.session_state["govee_plug_applied"] = want_on
        st.session_state["govee_plug_last_call_ts"] = time.time()
