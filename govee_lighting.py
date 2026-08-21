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
import market_yf_client
import scenery
from config import AQI_EXTREME, GOVEE_LIGHT, GOVEE_PLUG

MIN_CALL_GAP_SECONDS = 10
# Session request: "how can we make the turn off plug system more
# dynamic" -> "the grace period one." sync_plug's `want_on` used to cut
# power the instant ANY of its conditions (game/leave-timer/storm/
# daylight window) flipped false, with only game_live getting its own
# bespoke softening (sports_alerts.plug_should_stay_on's own postgame
# hold, TAKEOVER_POSTGAME_MINUTES — 15 minutes, tuned specifically for
# "give someone time to read the recap," not a general-purpose buffer).
# leave_timer_active, storm_active, and the plain daylight-window
# boundary had no grace at all — any of those ending mid-rerun snapped
# the plug straight off. This applies one general hold at the sync_plug
# level instead, after whichever specific condition contributed, so all
# four get the same softened landing without teaching each individual
# signal its own copy of "wait a bit before actually committing to
# off." Deliberately shorter than the postgame-specific hold above (5
# min vs. 15) — this is "don't cut power the instant something ends,"
# not "give a whole recap time to be read."
PLUG_OFF_GRACE_SECONDS = 5 * 60
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
#
# Session request: "evaluate the system as a whole... where we can
# plug formulas in that really shine a light on important data" — a
# flat 1.0% meant the exact same thing on a dead-calm session and a
# genuinely turbulent one. _significance_thresholds below now derives
# this pair from market_yf_client.expected_daily_move_pct (the same
# VIX/16 priced-in daily move the Markets page/ticker/morning brief
# already use), keeping the same 0.7/1.0 = 70% release ratio this
# hysteresis was already tuned around. These two constants stay as the
# fallback for whenever VIX itself is unreachable — same graceful-
# degradation convention as every other live source in this app.
MARKET_SIGNIFICANT_MOVE = 1.0
MARKET_SIGNIFICANT_RELEASE = 0.7
# The exact ratio the two constants above were already tuned to —
# preserved when deriving the pair from a live VIX-based enter
# threshold instead, so the hysteresis behaves the same either way.
_MARKET_RELEASE_RATIO = MARKET_SIGNIFICANT_RELEASE / MARKET_SIGNIFICANT_MOVE


def _significance_thresholds() -> tuple[float, float]:
    """(enter, release) threshold pair for whether today's market move
    counts as "significant" — VIX/16 when VIX is reachable, the original
    flat MARKET_SIGNIFICANT_MOVE/RELEASE pair otherwise."""
    expected = market_yf_client.expected_daily_move_pct()
    if expected is None:
        return MARKET_SIGNIFICANT_MOVE, MARKET_SIGNIFICANT_RELEASE
    return expected, expected * _MARKET_RELEASE_RATIO
FLASH_RED = (255, 0, 0)
FLASH_WHITE = (255, 255, 255)
FLASH_BRIGHTNESS = 100
# Storm-proximity light (session request: "red govee flashes for when
# the storm is approaching... solid red at like 30% for when its
# here... same thing for when the storm is leaving," driven by
# weather_alerts_bar.current_storm_phase/ec_storm_timing's own EC-
# sourced expected start/end times). "Here" is deliberately steady, not
# pulsing — same reasoning as SMOKE_COLOR below: an ongoing condition,
# not a sudden event, shouldn't compete for attention the same way an
# approaching/leaving flash (reusing FLASH_RED/FLASH_WHITE — the same
# alternating pulse breaking news already uses) is supposed to. Dim,
# not full brightness, once the storm has actually arrived — this is
# meant to be read at a glance without lighting up the whole room
# during what's often already a dark, stormy evening.
STORM_HERE_BRIGHTNESS = 30
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

# Game-mode night lighting (sync_lights' own jumbotron_active branch) —
# session feedback: "make it a more dim warmer neutral colour so its
# easier on the eyes." A plain warm white rather than whatever
# condition color happened to be on screen. Was 30 — session report:
# "my govy lights are stuck between lower brightness and higher
# brightness... quite disorienting to watch the game... make idle
# lights during a game literally like one percent brightness." Real
# root cause was sync_lights checking this branch too late (after the
# sunrise/sunset tint and market/condition base state, both of which
# ramp/change on their own) — see the reordering below — but the
# brightness itself is also just genuinely lower now, floor-dark for
# watching a bright screen in an otherwise dark room.
GAME_MODE_COLOR = (255, 209, 163)
GAME_MODE_BRIGHTNESS = 1

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

# "What did we last tell the physical light/plug to do" — module-level,
# not st.session_state. Session report: "my gov lights are completely
# off... they're kinda just all over the place tonight," while the Jays
# game was genuinely live. Root cause: this kiosk isn't the only
# session ever connected (a phone checking the score, a second tab —
# see toast_queue.py's own docstring for the same shape of problem with
# breaking-news alerts) and every one of the state vars below lived in
# st.session_state, so each connected session kept its own independent
# belief about the light's current color/brightness/power and about
# `_jumbotron_active` (itself derived partly from that session's own
# page/query-param routing). Two sessions disagreeing even slightly
# meant two independent callers issuing conflicting commands to the
# same physical bulb throughout the night. One shared copy here means
# every session agrees on what was last sent and only the one that's
# actually due sends anything.
_light_powered_on: bool | None = None
_light_color_applied: tuple[int, int, int] | None = None
_light_brightness_applied: int | None = None
# Session report: "the lights arent flashing to 100% for any game
# alerts." Root cause — one shared _light_last_call_ts used to gate
# power/color/brightness alike, even though they're three independent
# Govee API calls. sync_lights's flash path calls _apply_color right
# before _apply_brightness_immediate, so the color call's own success
# stamped this shared timestamp microseconds before the brightness
# call checked it against min_gap — always reading as "just called,"
# so the brightness call was silently skipped almost every single
# rerun of a flash. Split into one timestamp per endpoint so a color
# call can no longer block the very next brightness call (or vice
# versa) in the same invocation.
_light_power_last_call_ts: float = 0.0
_light_color_last_call_ts: float = 0.0
_light_brightness_last_call_ts: float = 0.0
_brightness_step_ts: float = 0.0
_market_significant: bool = False
_plug_applied: bool | None = None
_plug_last_call_ts: float = 0.0
_plug_last_true_at: float | None = None


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
    """Market color only for a move actually worth noticing (see
    _significance_thresholds — VIX/16 when reachable, otherwise the
    flat MARKET_SIGNIFICANT_MOVE fallback); otherwise the light just
    mirrors whatever condition is actually on screen (scenery.
    condition_light_color), same as the sunrise/sunset override
    already does for that specific window. `category` is None only if
    the weather fetch itself failed — condition_light_color's own
    "cloudy" fallback covers that case, same as scenery.py's own
    rendering does.

    Whether today's move counts as "significant" is itself hysteresis-
    gated (see _significance_thresholds' release ratio) rather than a
    flat >=enter-threshold check, so a move sitting right at the
    threshold on a choppy session doesn't flip the light back and forth
    every time it nudges a hair either side."""
    global _market_significant
    enter_threshold, release_threshold = _significance_thresholds()
    threshold = release_threshold if _market_significant else enter_threshold
    is_significant = market_intraday_pct is not None and abs(market_intraday_pct) >= threshold
    _market_significant = is_significant

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
    global _light_powered_on, _light_power_last_call_ts, _light_color_applied, _light_brightness_applied
    if _light_powered_on == on:
        return True
    if time.time() - _light_power_last_call_ts < MIN_CALL_GAP_SECONDS:
        return False
    if govee_client.set_power(GOVEE_LIGHT, on):
        _light_powered_on = on
        _light_power_last_call_ts = time.time()
        if not on:
            # Force a fresh color/brightness send next time it powers back
            # on (snapping to the correct values, not creeping into them
            # from scratch), rather than trusting whatever it powers on with.
            _light_color_applied = None
            _light_brightness_applied = None
        return True
    return False


def _apply_color(color: tuple[int, int, int], min_gap: float = MIN_CALL_GAP_SECONDS) -> None:
    global _light_color_applied, _light_color_last_call_ts
    if _light_color_applied == color:
        return
    if time.time() - _light_color_last_call_ts < min_gap:
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
        _light_color_applied = color
        _light_color_last_call_ts = time.time()


def _apply_brightness_immediate(value: int, min_gap: float = MIN_CALL_GAP_SECONDS) -> None:
    """Snaps brightness straight to `value` — used for the breaking-news
    flash (which needs to grab attention right now, not creep into view)
    and the very first apply of a session (nothing to creep FROM yet).
    Resets the creep clock too, so _creep_brightness's next step starts
    fresh from wherever this just landed rather than firing again
    immediately. Gated on the API result — see _apply_color's comment
    on why an unconditional write here was a real bug."""
    global _light_brightness_applied, _light_brightness_last_call_ts, _brightness_step_ts
    if _light_brightness_applied == value:
        return
    if time.time() - _light_brightness_last_call_ts < min_gap:
        return
    if govee_client.set_brightness(GOVEE_LIGHT, value):
        _light_brightness_applied = value
        _brightness_step_ts = time.time()
        _light_brightness_last_call_ts = time.time()


def _creep_brightness(target: int) -> None:
    """Nudges brightness one BRIGHTNESS_STEP_SIZE toward `target`, at most
    once every BRIGHTNESS_STEP_INTERVAL_SECONDS — never jumps straight
    there. First-ever call (nothing applied yet this session) snaps
    instead, so a fresh app start shows the correct brightness right
    away rather than creeping up from scratch for the next hour."""
    global _light_brightness_applied, _brightness_step_ts
    current = _light_brightness_applied
    if current is None:
        _apply_brightness_immediate(target)
        return
    if current == target:
        return
    if time.time() - _brightness_step_ts < BRIGHTNESS_STEP_INTERVAL_SECONDS:
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
        _light_brightness_applied = next_value
        _brightness_step_ts = time.time()


def sync_lights(
    phase: str,
    market_intraday_pct: float | None,
    breaking_alert_elapsed: float | None,
    now: datetime,
    sunset: datetime | None,
    aqi: float | None = None,
    category: str | None = None,
    score_flash: tuple[float, tuple[int, int, int]] | None = None,
    jumbotron_active: bool = False,
    storm_phase: str | None = None,
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
    active breaking alert). `storm_phase` ("approaching"/"here"/
    "leaving"/None — weather_alerts_bar.current_storm_phase) is checked
    BEFORE the night gate, not after (see the night-override paragraph
    below) — an alternating red/white pulse, same as breaking news, only
    for "approaching" (session correction, woken up by it at 2am: a
    full-brightness flash is only actually justified for a genuine
    incoming threat, not for a warning already trailing off); a steady
    FLASH_RED at STORM_HERE_BRIGHTNESS for both "here" and "leaving",
    not pulsing, since those are an ongoing/already-passing condition
    rather than a fresh event worth a jolt. A genuinely extreme AQI
    (real wildfire smoke, not routine haze) overrides everything below
    IT with SMOKE_COLOR instead. During the
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
    was the wrong call, full stop. That general rule still holds for
    routine weather, but a follow-up session request ("it should show
    at night") carved out an explicit exception for `storm_phase`
    specifically: a storm-grade EC alert (extreme/warning severity,
    see ec_storm_timing.STORM_SEVERITIES) now wakes the light overnight
    same as score_flash does, checked ahead of the night gate rather
    than after it. Breaking news is unaffected by this — it still fully
    respects night, no exception — this is scoped to storm_phase alone.
    The screen still does its own, separate thing for weather overnight
    (see app.py's night_dim override).

    `score_flash` is (elapsed, color) for a fresh Jays/Habs scoring-play
    alert (see sports_alerts.py) — session request: "a blue govee flash"
    for the Jays, red for the Habs. Same brief alternating pulse as the
    breaking-news flash, just the caller's own team color instead of
    red — and unlike every other override here, this one is checked
    BEFORE the night gate rather than after: session request, a
    scoring play should flash even overnight. It reverts to night's
    own power-off automatically once the alert ends (score_flash goes
    back to None the very next rerun — the caller only sets it while
    the alert's own elapsed stays under FLASH_SECONDS), so this doesn't
    keep the room lit all night, just for the flash itself. Breaking
    news still fully respects night (unchanged, no exception) — this
    is a scoped, deliberate exception for sports alerts specifically,
    not a general "wake for alerts" policy.

    `jumbotron_active` — session request: "same rule with the lights"
    (as app.py's own night_dim exemption for the screen, right after
    it: "make it so the screen does not dim in game mode"). Narrow
    scope, same as that one: only within the takeover's actual
    pregame/live/postgame window, not for the whole rest of the day
    just because a game is on today's schedule somewhere. app.py passes
    a page-INDEPENDENT flag here though (`_takeover is not None`, not
    its own page-gated `_jumbotron_active`) — this light is one shared
    real-world device, not tied to any one connected session's screen,
    so it needs to track "is the game actually live" the same way
    sync_plug's own `game_live` already does, not "is THIS particular
    session currently looking at the board." Session report: "my gov
    lights are completely off... all over the place" while a game was
    genuinely live, traced to exactly that mismatch — a phone checking
    the score from any other page believed jumbotron_active was False
    and kept pushing the shared light back to its normal state, fighting
    the kiosk's own session every few reruns. Bypasses the night
    power-off gate, but not into DAY_BRIGHTNESS or the market/condition
    color that'd normally apply — session feedback right after: "make
    it a more dim warmer neutral colour so its easier on the eyes."
    Settles on GAME_MODE_COLOR/GAME_MODE_BRIGHTNESS instead, a plain
    warm white dim enough to watch a bright screen by in an otherwise
    dark room.

    Checked ahead of the sunrise/sunset tint and the market/condition
    base state (both of which change on their own timer/values) —
    session report: "my govy lights are stuck between lower brightness
    and higher brightness... disorienting to watch the game... no
    other force except breaking news alerts, bluejays alerts, or other
    team alerts can impact the lights [during a game]... oh, severe
    weather too." score_flash/breaking_alert_elapsed/AQI-smoke above
    still take priority (that's the "severe weather too" exception),
    but nothing below this check can touch the light while a game's
    actually on screen — no longer gated on `phase == "night"` either,
    since the point is "a game is on," not "a game is on AND it's
    already dark."
    """
    if not st.secrets.get("GOVEE_API_KEY"):
        return
    if score_flash is not None:
        if not _apply_power(True):
            return
        flash_elapsed, flash_color = score_flash
        color = flash_color if int(flash_elapsed) % 2 == 0 else FLASH_WHITE
        _apply_color(color, min_gap=FLASH_CALL_GAP_SECONDS)
        _apply_brightness_immediate(FLASH_BRIGHTNESS, min_gap=FLASH_CALL_GAP_SECONDS)
        return
    # Storm proximity — session request: "red govee flashes for when the
    # storm is approaching... solid red at like 30% for when its
    # here... same thing for when the storm is leaving." Session
    # follow-up: "it should show at night" — explicitly overturning the
    # earlier "waking the room for weather overnight was the wrong
    # call" decision, but scoped to this specific case (a storm-grade EC
    # alert actually bearing down), not weather broadly. Checked ahead
    # of the night gate, same exception shape as score_flash above — its
    # own _apply_power(True) call is what actually wakes the light from
    # night's power-off.
    #
    # Session correction, at 2am, woken up by it: "the lights are
    # flashing random colors... going from red to white to red again...
    # its broken." Not a bug — this was the full-brightness alternating
    # pulse "leaving" originally shared with "approaching" — but living
    # with it live at night showed that pulse is only actually justified
    # for a genuine incoming threat (approaching) worth being startled
    # awake for. By the time a warning's in its trailing "leaving" tail
    # (already past EC's own expected event_end_datetime — see
    # ec_storm_timing.LEAVING_TAIL_MINUTES), the storm itself is
    # basically already over, and jolting the room with a full-
    # brightness flash for that is disruptive out of proportion to what
    # it's actually signaling. "leaving" now gets the exact same calm,
    # steady, dim treatment as "here" instead of "approaching"'s flash.
    if storm_phase == "approaching":
        if not _apply_power(True):
            return
        color = FLASH_RED if int(time.time()) % 2 == 0 else FLASH_WHITE
        _apply_color(color, min_gap=FLASH_CALL_GAP_SECONDS)
        _apply_brightness_immediate(FLASH_BRIGHTNESS, min_gap=FLASH_CALL_GAP_SECONDS)
        return
    if storm_phase in ("here", "leaving"):
        if not _apply_power(True):
            return
        _apply_color(FLASH_RED)
        _apply_brightness_immediate(STORM_HERE_BRIGHTNESS)
        return
    if phase == "night" and not jumbotron_active:
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
    # Session report: "my govy lights are stuck between lower
    # brightness and higher brightness... disorienting to watch the
    # game... make it so no other force except breaking news alerts,
    # bluejays alerts, or other team alerts can impact the lights." Was
    # checked below the sunrise/sunset tint and (implicitly, by falling
    # through) the market/condition base state — both of which change
    # on their own timers/values — so a game spanning the evening
    # transition, or any market wobble, could pull brightness back and
    # forth against the steady game-mode floor above it. Moved ahead of
    # both (score_flash/breaking_alert_elapsed/AQI-smoke above still
    # win first, matching the same request's own "oh, severe weather
    # too" exception), and dropped the `phase == "night"` requirement —
    # this is "a game is on," not "a game is on AND it's already dark."
    if jumbotron_active:
        _apply_color(GAME_MODE_COLOR)
        # Immediate, not _creep_brightness — session report: "I got an
        # alert, and now I'm being blinded by one hundred percent...
        # white." A score_flash snaps brightness straight to
        # FLASH_BRIGHTNESS (100) for punch, then goes back to None once
        # its own hold ends, falling through to here — but creeping is
        # paced for the day/night ramp's own slowly-moving envelope
        # (BRIGHTNESS_STEP_SIZE/minute), not for recovering from a
        # deliberate 100-point spike. GAME_MODE_BRIGHTNESS is a fixed
        # floor, not a moving target, so there's nothing to ease
        # into — every scoring play during a game would otherwise leave
        # the room stuck near full brightness for up to 99 minutes.
        _apply_brightness_immediate(GAME_MODE_BRIGHTNESS)
        return
    if phase in ("sunrise", "sunset"):
        _apply_color(SUNRISE_COLOR if phase == "sunrise" else SUNSET_COLOR)
        _creep_brightness(_brightness_envelope(now, DAY_BRIGHTNESS, sunset))
        return
    color, brightness = _desired_base_state(market_intraday_pct, category, now, sunset)
    _apply_color(color)
    _creep_brightness(brightness)


def sync_plug(
    now: datetime,
    first_light: datetime | None,
    last_light: datetime | None,
    game_live: bool = False,
    leave_timer_active: bool = False,
    storm_active: bool = False,
) -> None:
    """Off at last_light, on at first_light — despite the names, a
    fixed daily clock schedule now (4:30am on, 9:30pm off), not real
    civil-twilight bounds anymore. Session report: "I think we have it
    tied up to the sunset/sunrise thing right now... instead of having
    it turn off at a different time every day, make it go into dim
    night mode at nine PM and have it fully turn off at... nine
    thirty... and turn the monitor on at four thirty AM." Was real
    astronomical dawn/dusk before (sun 6° below the horizon), which
    meant the actual on/off instant drifted earlier/later with the
    season — the exact thing this fixed it away from. The parameter
    names/shape are unchanged on purpose (the caller, app.py, just
    passes fixed clock times where it used to pass real astronomical
    ones) — every override below still works exactly as it always did,
    completely untouched by this; only what decides the PLAIN window
    changed, not what's allowed to override it.

    `game_live` (see sports_alerts.plug_should_stay_on) keeps this plug
    — and so the monitor it powers — on regardless of that window while
    a Jays/Habs game is live or in its postgame recap (session request:
    "the smart plug can't turn off if there's a live game," later "the
    second the end of game recap happened the smart plug turned off...
    shouldn't have happened for at least 5 mins" — that specific gap
    already gets its own long, sport-tuned hold via the postgame phase,
    see plug_should_stay_on's own docstring).

    `leave_timer_active` (see commute_reminder.leave_headline_active) —
    same kind of override, for the same reason: an early shift's 2-hour
    leave countdown can start well before first_light in the darker
    months, and app.py already forces the SCREEN to full brightness
    while that countdown is up (see its own night_dim override) — but
    none of that matters if the monitor has no power yet. Session
    report: "my girlfriend worked at 6am this morning and I had to
    manually turn on the plug so she could see the leave in timer."

    `storm_active` (see sync_lights' own storm_phase param, which the
    caller derives this from — true for any of approaching/here/
    leaving) — session follow-up to the storm-proximity light feature,
    right after the lights themselves were made to wake overnight for
    a storm: "monitor should turn on too." Same kind of override as
    game_live/leave_timer_active: the monitor needs power for the
    storm's own toast alerts and the light's own red flash to actually
    be visible/legible, same reasoning as leave_timer_active existing
    for exactly that purpose already.

    None of the three overrides (or the plain daylight window itself)
    cut power the instant they stop being true anymore — see
    PLUG_OFF_GRACE_SECONDS's own comment ("how can we make the turn off
    plug system more dynamic" -> "the grace period one"): the plug
    stays on for a short buffer after the LAST moment any condition
    genuinely wanted it on, re-armed fresh every time one does, so a
    condition flickering true/false right at its own boundary (a storm
    phase clearing, a leave countdown ending, last_light passing) can't
    cause a premature cutoff either. Still reverts to fully off once
    that whole buffer genuinely elapses with nothing wanting it on."""
    global _plug_applied, _plug_last_call_ts, _plug_last_true_at
    if not st.secrets.get("GOVEE_API_KEY") or first_light is None or last_light is None:
        return
    raw_want_on = game_live or leave_timer_active or storm_active or (first_light <= now < last_light)
    now_ts = time.time()
    if raw_want_on:
        _plug_last_true_at = now_ts
        want_on = True
    else:
        want_on = _plug_last_true_at is not None and (now_ts - _plug_last_true_at) < PLUG_OFF_GRACE_SECONDS
    if _plug_applied == want_on:
        return
    if time.time() - _plug_last_call_ts < MIN_CALL_GAP_SECONDS:
        return
    if govee_client.set_power(GOVEE_PLUG, want_on):
        _plug_applied = want_on
        _plug_last_call_ts = time.time()
