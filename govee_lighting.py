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
from datetime import datetime, timedelta

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

DAY_BRIGHTNESS = 100  # peak brightness while the light is on — one tier, no market-hours step
MARKET_UP_COLOR = (0, 255, 0)
MARKET_DOWN_COLOR = (255, 0, 0)
MARKET_NEUTRAL_COLOR = (255, 255, 255)
MARKET_FLAT_BAND = 0.1  # +/- percent treated as flat, avoids flicker right at 0
FLASH_RED = (255, 0, 0)
FLASH_WHITE = (255, 255, 255)
FLASH_BRIGHTNESS = 100

# Gentle wake-up/wind-down curve, layered under the sunset/sunrise on/off
# gate below — the light already powers on as early as real sunrise, well
# before anyone's awake in summer, and previously jumped straight to
# DAY_BRIGHTNESS the instant it did. Morning ramps up from a fixed clock
# time (sunrise varies too much by season to anchor to). Evening instead
# counts back from real sunset — the same value that already powers the
# light off — by exactly EVENING_RAMP_MINUTES, so BRIGHTNESS_STEP_SIZE's
# 1-point-per-minute creep has *exactly* enough time to glide all the way
# from DAY_BRIGHTNESS down to MIN_DAY_BRIGHTNESS right as the light cuts
# off, instead of getting cut short partway down or finishing early and
# sitting at the floor for a while before sunset actually arrives.
MORNING_RAMP_START_HOUR = 7  # 7:00am
MORNING_RAMP_MINUTES = 60
MIN_DAY_BRIGHTNESS = 1  # floor outside the ramp windows — dim, not off (off is phase == "night"); 1 is Govee's actual minimum

# Brightness never jumps straight to a new target — it creeps there in
# 1-point steps, at most once a minute. This is what actually makes the
# morning/evening ramp above feel smooth in practice, and DAY_BRIGHTNESS -
# MIN_DAY_BRIGHTNESS steps at BRIGHTNESS_STEP_SIZE/step is exactly how long
# a full climb or descent physically takes — the evening ramp above is
# timed to match.
BRIGHTNESS_STEP_INTERVAL_SECONDS = 60
BRIGHTNESS_STEP_SIZE = 1
EVENING_RAMP_MINUTES = (DAY_BRIGHTNESS - MIN_DAY_BRIGHTNESS) // BRIGHTNESS_STEP_SIZE  # 99, at current constants
# Fallback anchor only used if real sunset isn't available (weather fetch
# failed) — keeps the evening ramp working, just not sunset-synced.
FALLBACK_EVENING_RAMP_END_HOUR = 21  # 9:30pm
FALLBACK_EVENING_RAMP_END_MINUTE = 30


def _brightness_envelope(now: datetime, base_brightness: int, sunset: datetime | None) -> int:
    morning_start = now.replace(hour=MORNING_RAMP_START_HOUR, minute=0, second=0, microsecond=0)
    morning_end = morning_start + timedelta(minutes=MORNING_RAMP_MINUTES)
    evening_end = sunset if sunset is not None else now.replace(
        hour=FALLBACK_EVENING_RAMP_END_HOUR, minute=FALLBACK_EVENING_RAMP_END_MINUTE, second=0, microsecond=0
    )
    evening_start = evening_end - timedelta(minutes=EVENING_RAMP_MINUTES)

    if now < morning_start or now >= evening_end:
        return MIN_DAY_BRIGHTNESS
    if now < morning_end:
        t = (now - morning_start).total_seconds() / (morning_end - morning_start).total_seconds()
    elif now >= evening_start:
        t = (evening_end - now).total_seconds() / (evening_end - evening_start).total_seconds()
    else:
        return base_brightness
    return round(MIN_DAY_BRIGHTNESS + (base_brightness - MIN_DAY_BRIGHTNESS) * t)


def _desired_base_state(
    market_intraday_pct: float | None, now: datetime, sunset: datetime | None
) -> tuple[tuple[int, int, int], int]:
    if market_intraday_pct is None or abs(market_intraday_pct) < MARKET_FLAT_BAND:
        color = MARKET_NEUTRAL_COLOR
    elif market_intraday_pct > 0:
        color = MARKET_UP_COLOR
    else:
        color = MARKET_DOWN_COLOR
    return color, _brightness_envelope(now, DAY_BRIGHTNESS, sunset)


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
            # Force a fresh color/brightness send next time it powers back
            # on (snapping to the correct values, not creeping into them
            # from scratch), rather than trusting whatever it powers on with.
            st.session_state["govee_light_color_applied"] = None
            st.session_state["govee_light_brightness_applied"] = None
        return True
    return False


def _apply_color(color: tuple[int, int, int], min_gap: float = MIN_CALL_GAP_SECONDS) -> None:
    if st.session_state.get("govee_light_color_applied") == color:
        return
    if time.time() - st.session_state.get("govee_last_call_ts", 0) < min_gap:
        return
    govee_client.set_color(GOVEE_LIGHT, color)
    st.session_state["govee_light_color_applied"] = color
    st.session_state["govee_last_call_ts"] = time.time()


def _apply_brightness_immediate(value: int, min_gap: float = MIN_CALL_GAP_SECONDS) -> None:
    """Snaps brightness straight to `value` — used for the breaking-news
    flash (which needs to grab attention right now, not creep into view)
    and the very first apply of a session (nothing to creep FROM yet).
    Resets the creep clock too, so _creep_brightness's next step starts
    fresh from wherever this just landed rather than firing again
    immediately."""
    if st.session_state.get("govee_light_brightness_applied") == value:
        return
    if time.time() - st.session_state.get("govee_last_call_ts", 0) < min_gap:
        return
    govee_client.set_brightness(GOVEE_LIGHT, value)
    st.session_state["govee_light_brightness_applied"] = value
    st.session_state["govee_brightness_step_ts"] = time.time()
    st.session_state["govee_last_call_ts"] = time.time()


def _creep_brightness(target: int) -> None:
    """Nudges brightness one BRIGHTNESS_STEP_SIZE toward `target`, at most
    once every BRIGHTNESS_STEP_INTERVAL_SECONDS — never jumps straight
    there. First-ever call (nothing applied yet this session) snaps
    instead, so a fresh app start shows the correct brightness right
    away rather than creeping up from scratch for the next hour."""
    current = st.session_state.get("govee_light_brightness_applied")
    if current is None:
        _apply_brightness_immediate(target)
        return
    if current == target:
        return
    if time.time() - st.session_state.get("govee_brightness_step_ts", 0) < BRIGHTNESS_STEP_INTERVAL_SECONDS:
        return
    step = BRIGHTNESS_STEP_SIZE if target > current else -BRIGHTNESS_STEP_SIZE
    next_value = current + step
    if (step > 0 and next_value > target) or (step < 0 and next_value < target):
        next_value = target
    govee_client.set_brightness(GOVEE_LIGHT, next_value)
    st.session_state["govee_light_brightness_applied"] = next_value
    st.session_state["govee_brightness_step_ts"] = time.time()


def sync_lights(
    phase: str,
    market_intraday_pct: float | None,
    breaking_alert_elapsed: float | None,
    now: datetime,
    sunset: datetime | None,
) -> None:
    """Call once per rerun. Light follows the exact same sunset/sunrise
    pattern as the plug — off at night, no exceptions (including no
    breaking-news flash overnight, since the point is an uninterrupted
    rest period). During the day it stays on and reactive: market-direction
    color normally, brightness ramping per the morning/evening curve above
    (1 up to 100, the evening side timed backward from real `sunset` so it
    lands on the floor right as the light powers off) — or an alternating
    red/white pulse, at full unramped brightness since a breaking alert
    should still grab attention, while `breaking_alert_elapsed` is not None
    (the seconds elapsed since a fresh breaking alert started showing — the
    caller already tracks each alert's shown_at for the toast bar, so this
    reuses that instead of tracking its own copy; None means no active
    breaking alert). Color always applies instantly; brightness creeps
    toward its target instead (see _creep_brightness) except during a
    flash, which needs to be immediately attention-grabbing rather than
    easing into view."""
    if not st.secrets.get("GOVEE_API_KEY"):
        return
    if phase == "night":
        _apply_power(False)
        return
    if not _apply_power(True):
        return
    if breaking_alert_elapsed is not None:
        color = FLASH_RED if int(breaking_alert_elapsed) % 2 == 0 else FLASH_WHITE
        _apply_color(color, min_gap=FLASH_CALL_GAP_SECONDS)
        _apply_brightness_immediate(FLASH_BRIGHTNESS, min_gap=FLASH_CALL_GAP_SECONDS)
        return
    color, brightness = _desired_base_state(market_intraday_pct, now, sunset)
    _apply_color(color)
    _creep_brightness(brightness)


def sync_plug(now: datetime, first_light: datetime | None, last_light: datetime | None) -> None:
    """Off at last light, on at first light — deliberately real civil-
    twilight bounds (dawn/dusk, sun 6° below the horizon), not the same
    `phase` the dashboard's own visuals use, and not the sunrise/sunset
    disk-crossing times either: those still leave real usable light in
    the sky for a while after "sunset" and before "sunrise". scenery.
    phase_for also clamps "day" to never start before ~7:40am so the
    room doesn't visually brighten too early in midsummer, but that's a
    room-comfort choice specific to the sky/dimming — the monitor itself
    should just follow the actual daylight window, no floor."""
    if not st.secrets.get("GOVEE_API_KEY") or first_light is None or last_light is None:
        return
    want_on = first_light <= now < last_light
    if st.session_state.get("govee_plug_applied") == want_on:
        return
    if time.time() - st.session_state.get("govee_plug_last_call_ts", 0) < MIN_CALL_GAP_SECONDS:
        return
    if govee_client.set_power(GOVEE_PLUG, want_on):
        st.session_state["govee_plug_applied"] = want_on
        st.session_state["govee_plug_last_call_ts"] = time.time()
