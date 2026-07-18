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
import scenery
from config import AQI_EXTREME, GOVEE_LIGHT, GOVEE_PLUG

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
# The room used to sit on market color all day, every day, even on a dead-
# flat 0.2% afternoon — every real move got the same green/red treatment
# as a genuinely notable one. Market color is now reserved for a move
# actually worth glancing at; anything under this reverts to mirroring
# the environment instead (see condition_light_color below). A full
# percentage point on a broad index is a real, headline-worthy single-
# session move, not routine noise.
#
# Two thresholds, not one — a plain single cutoff meant a move sitting
# right at 1.0% (real, happens on an actively choppy session) could
# flip the light between market and environment color on every tick
# that nudged it a hair either side, each flip a real API call. Once a
# move is significant, it has to fall back below the (lower) RELEASE
# threshold before the light reverts — standard hysteresis, tracked
# per-session in govee_market_significant below.
MARKET_SIGNIFICANT_MOVE = 1.0
MARKET_SIGNIFICANT_RELEASE = 0.7
FLASH_RED = (255, 0, 0)
FLASH_WHITE = (255, 255, 255)
FLASH_BRIGHTNESS = 100
# A physical, ambient signal for real wildfire smoke — the room itself
# tells you the air's bad without needing to look at the screen.
# Deliberately not pulsing like the breaking-news flash: this is an
# ongoing condition, not a sudden event, so it shouldn't compete for
# attention the same way. Same AQI_EXTREME cutoff the hero-row badge
# already uses for its own most-intense color, so the light only
# overrides market color for genuinely bad air, not routine haze.
SMOKE_COLOR = (255, 140, 20)

# The screen's own sky (scenery.py's _SKY_STOPS) already blends to a warm
# amber/peach glow during the sunrise/sunset transition — the room light
# used to stay on plain market color straight through that, on a
# completely separate track from what's actually on screen. These are
# the exact horizon-glow stops from scenery._SKY_STOPS (the warmest tone
# in each gradient), converted to RGB, so the room genuinely matches
# what's rendered rather than approximating it with a new color.
SUNRISE_COLOR = (253, 217, 160)  # scenery._SKY_STOPS["sunrise"][3], #fdd9a0
SUNSET_COLOR = (248, 194, 122)  # scenery._SKY_STOPS["sunset"][3], #f8c27a

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
    market_intraday_pct: float | None, category: str | None, now: datetime, sunset: datetime | None
) -> tuple[tuple[int, int, int], int]:
    """Market color only for a move actually worth noticing
    (MARKET_SIGNIFICANT_MOVE); otherwise the light just mirrors whatever
    condition is actually on screen (scenery.condition_light_color),
    same as the sunrise/sunset override already does for that specific
    window. `category` is None only if the weather fetch itself failed —
    condition_light_color's own "cloudy" fallback covers that case, same
    as scenery.py's own rendering does.

    Whether today's move counts as "significant" is itself hysteresis-
    gated (see MARKET_SIGNIFICANT_RELEASE above) rather than a flat
    >=MARKET_SIGNIFICANT_MOVE check, so a move sitting right at the
    threshold on a choppy session doesn't flip the light back and forth
    every time it nudges a hair either side."""
    was_significant = st.session_state.get("govee_market_significant", False)
    threshold = MARKET_SIGNIFICANT_RELEASE if was_significant else MARKET_SIGNIFICANT_MOVE
    is_significant = market_intraday_pct is not None and abs(market_intraday_pct) >= threshold
    st.session_state["govee_market_significant"] = is_significant

    if is_significant:
        color = MARKET_UP_COLOR if market_intraday_pct > 0 else MARKET_DOWN_COLOR
    else:
        color = scenery.condition_light_color(category)
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
    # Gated on the actual API result (same pattern as _apply_power below)
    # — a failed call (rate limit, WiFi hiccup, momentary Govee outage,
    # all real events on a 24/7 kiosk) used to get cached as "applied"
    # regardless, so the early-return guard above would then suppress
    # every future retry for that value: the physical light would
    # silently diverge from what the dashboard believes it's showing
    # and never self-correct until the next *different* desired color
    # came along. Not updating govee_last_call_ts on failure is
    # deliberate too, matching _apply_power — retry sooner than
    # min_gap once something's actually wrong, not wait out a normal
    # cooldown for a call that never went through.
    if govee_client.set_color(GOVEE_LIGHT, color):
        st.session_state["govee_light_color_applied"] = color
        st.session_state["govee_last_call_ts"] = time.time()


def _apply_brightness_immediate(value: int, min_gap: float = MIN_CALL_GAP_SECONDS) -> None:
    """Snaps brightness straight to `value` — used for the breaking-news
    flash (which needs to grab attention right now, not creep into view)
    and the very first apply of a session (nothing to creep FROM yet).
    Resets the creep clock too, so _creep_brightness's next step starts
    fresh from wherever this just landed rather than firing again
    immediately. Gated on the API result — see _apply_color's comment
    on why an unconditional write here was a real bug."""
    if st.session_state.get("govee_light_brightness_applied") == value:
        return
    if time.time() - st.session_state.get("govee_last_call_ts", 0) < min_gap:
        return
    if govee_client.set_brightness(GOVEE_LIGHT, value):
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
    # Gated on the API result — see _apply_color's comment; a failed
    # step used to be recorded as if it landed, permanently offsetting
    # every subsequent step in this creep from where the light actually
    # is.
    if govee_client.set_brightness(GOVEE_LIGHT, next_value):
        st.session_state["govee_light_brightness_applied"] = next_value
        st.session_state["govee_brightness_step_ts"] = time.time()


def sync_lights(
    phase: str,
    market_intraday_pct: float | None,
    breaking_alert_elapsed: float | None,
    now: datetime,
    sunset: datetime | None,
    aqi: float | None = None,
    category: str | None = None,
) -> None:
    """Call once per rerun. Light follows the exact same sunset/sunrise
    pattern as the plug — off at night, no exceptions. Every override
    below (breaking news, smoke, sunrise/sunset tint) respects that
    gate, since the point of night is an uninterrupted rest period.
    During the day it stays on and reactive: market color only for a
    genuinely significant move (see MARKET_SIGNIFICANT_MOVE), otherwise
    mirroring whatever condition is actually on screen (see
    scenery.condition_light_color) — brightness ramping per the
    morning/evening curve above either way (1 up to 100, the evening
    side timed backward from real `sunset` so it lands on the floor
    right as the light powers off). Or an alternating red/white pulse,
    at full unramped brightness since a breaking alert should still
    grab attention, while `breaking_alert_elapsed` is not None (the
    seconds elapsed since a fresh breaking alert started showing — the
    caller already tracks each alert's shown_at for the toast bar, so
    this reuses that instead of tracking its own copy; None means no
    active breaking alert). A genuinely extreme AQI (real wildfire
    smoke, not routine haze) overrides everything below it with
    SMOKE_COLOR instead — checked after the breaking-news flash (which
    still wins, being the more urgent/immediate of the two). During the
    sunrise/sunset transition (the same `phase` scenery.py's own sky
    gradient uses), the light tints to that gradient's own warm
    horizon-glow color — checked after the flash/smoke overrides (both
    still win, being genuinely urgent) but before the market/environment
    base state, so the room actually matches the screen during that
    window rather than sitting on a separate, unrelated track. Color
    always applies instantly; brightness creeps toward its target
    instead (see _creep_brightness) except during a flash, which needs
    to be immediately attention-grabbing rather than easing into view.

    Used to also wake for severe weather and incoming rain, bypassing
    night/off — session feedback: waking the room for weather overnight
    was the wrong call, full stop. The screen still does its own,
    separate thing for weather overnight (see app.py's night_dim
    override) — this module no longer reacts to weather at all."""
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
    if aqi is not None and aqi >= AQI_EXTREME:
        _apply_color(SMOKE_COLOR)
        _creep_brightness(_brightness_envelope(now, DAY_BRIGHTNESS, sunset))
        return
    if phase in ("sunrise", "sunset"):
        _apply_color(SUNRISE_COLOR if phase == "sunrise" else SUNSET_COLOR)
        _creep_brightness(_brightness_envelope(now, DAY_BRIGHTNESS, sunset))
        return
    color, brightness = _desired_base_state(market_intraday_pct, category, now, sunset)
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
