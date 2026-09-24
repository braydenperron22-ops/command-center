"""Entry point for LG TV sync — runs two things concurrently:

1. lg_tv_control.watch_state: a PERSISTENT connection to the TV,
   reacting instantly the moment the TV itself pushes a state change
   (see that function's own docstring — this is the real "push
   subscriptions" half, confirmed live to need no manual subscribe_x()
   calls, aiowebostv already wires this up inside connect()). Right
   now that means: a manual volume nudge while on the kiosk snaps back
   to KIOSK_VOLUME within about a second, not up to a minute later.

2. _poll_loop below: the dashboard's own desired state (night_mode_
   active, queued notifications) lives in Upstash, a plain REST key/
   value store with no push/webhook mechanism on the free tier — there
   is no way to make that half instant, only faster-polled. Session
   request: "if it means everything will start reacting in real time,
   that's good" — CHECK_INTERVAL_SECONDS dropped from 60s to 20s (3x),
   a real responsiveness gain, but deliberately NOT dropped further:
   this app has a documented, shared 500k-command/month Upstash budget
   across every feature that uses it, and 20s already roughly triples
   this one service's own share of that rather than pushing it toward
   dominating it the way something far more aggressive (5-10s) would.

Session request (still true, unchanged): "check the state every 15
minutes until it's back to HDMI 1 or the TV is off itself, and then
rest there" for bedtime engaging (power_off_if_ours, RECHECK_INTERVAL_
SECONDS while deferred); "as simple as possible... turn off TV, you
put kiosk on" for the not-bedtime direction (wake_and_switch_if_safe,
every poll tick, no recheck gating — see lg_tv_control.py's own
docstrings for why each is a safe, cheap no-op when there's nothing to
actually do).

Session correction: the FIRST power-off attempt each night no longer
fires a flat NIGHT_MODE_OFF_DELAY_SECONDS after night mode simply
engages -- it now waits for sleep_tracker.screen_sleep_time (the real
calculated bedtime + a grace period), falling back to the old flat
delay only when there's no real bedtime to anchor to (e.g. a genuine
day off). The flat delay used to mean the TV could go to sleep hours
before the real "Get into bed" CTA on the dashboard ever showed.

Run as its own systemd --user service (see systemd/lg-tv-sync.service)
— reusing this same venv (aiowebostv installed alongside everything
else here) rather than a separate one."""

import asyncio
import json
import time
from datetime import date, datetime
from pathlib import Path

import lg_tv_control
import persisted_state
import sleep_tracker

CHECK_INTERVAL_SECONDS = 20
RECHECK_INTERVAL_SECONDS = 15 * 60
# Session request: "the TV doesn't turn off until... 15 minutes after
# night mode is kicked in." A flat grace window on the ENGAGING
# transition only -- the TV stays on for this long after night mode
# starts before the first power-off attempt is even made. Distinct
# from RECHECK_INTERVAL_SECONDS above (which governs re-attempts once
# already deferred because the Xbox is in use) -- this just delays the
# very first attempt.
NIGHT_MODE_OFF_DELAY_SECONDS = 15 * 60
# How often to retry the daily volume floor if the TV wasn't reachable
# the last time -- not every single poll tick (the TV being off most of
# the night is the normal case, no reason to hammer a connect attempt
# that often for a check that only needs to succeed once a day).
VOLUME_CHECK_RETRY_SECONDS = 30 * 60

_STATE_DIR = Path.home() / ".local" / "state" / "kiosk-watchdog"
_STATE_FILE = _STATE_DIR / "lg_tv_sync_state.json"
_LOG_FILE = _STATE_DIR / "lg-tv-sync.log"

_DEFAULT_STATE = {
    "desired_active": None,  # last night_mode_active value this module has seen/acted on
    "settled": True,  # whether that desired state has been fully achieved (or confirmed N/A)
    "next_check_at": 0.0,  # don't recheck (Xbox-deferred case) again before this time
    "night_engaged_at": 0.0,  # epoch time night mode most recently engaged -- fallback target basis
    "volume_floor_date": None,  # ISO date the daily volume floor last actually ran
    "next_volume_check_at": 0.0,
    "ip_check_date": None,  # ISO date lg_tv_control.verify_tv_ip last actually ran
    "notifications_shown_at": 0.0,  # watermark for lg_tv_control.send_pending_notifications
}


def _log(msg: str) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}\n")


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return {**_DEFAULT_STATE, **json.loads(_STATE_FILE.read_text())}
        except Exception:
            pass
    return dict(_DEFAULT_STATE)


def _save_state(state: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state))


async def _tick() -> None:
    now_ts = time.time()
    state = _load_state()

    night_mode = persisted_state.load("night_mode_active", None)
    if night_mode is not None:
        desired_active = bool(night_mode.get("active"))
        if state["desired_active"] != desired_active:
            state["desired_active"] = desired_active
            state["settled"] = False
            state["next_check_at"] = 0.0
            if desired_active:
                state["night_engaged_at"] = now_ts
                _log("night mode engaged")

        if desired_active:
            # Session bug, live: night mode's own day-window now also
            # engages during the morning wake-preview/overdue span (see
            # sleep_tracker.in_wake_grace_window's own docstring) -- not
            # just real evening bedtime. screen_sleep_time's "bedtime"
            # math, evaluated at THIS hour, resolves to LAST NIGHT's
            # already-passed bedtime (_apply_bedtime_cap pulls a same-
            # morning wake_time_for back onto the previous evening), so
            # the power-off-after-bedtime check below saw a target
            # already in the past and immediately powered the TV off
            # right as wake_preview_if_due should have been showing it
            # (confirmed live: engaged 08:44:42, powered off 08:44:46).
            # Skip the power-off branch entirely while in this window --
            # it was never a real bedtime to begin with -- and let
            # wake_preview_if_due (still called every tick below) own
            # the TV instead.
            if sleep_tracker.in_wake_grace_window(datetime.now()):
                pass
            # Bedtime: power off if ours, but not until the REAL
            # calculated bedtime (+ grace) has passed -- see sleep_
            # tracker.screen_sleep_time's own docstring for why this is
            # anchored to real bedtime, not the fixed night-mode-engage
            # moment (session correction: a flat delay from engage could
            # put the TV to sleep hours before "Get into bed" ever
            # showed). Falls back to the old flat-delay-from-engage
            # shape only when there's no real bedtime to anchor to at
            # all (e.g. a genuine day off). The explicit 15-minute
            # recheck cadence while deferred (Xbox in use) still applies
            # once past that target.
            elif not state["settled"] and now_ts >= state["next_check_at"]:
                sleep_time = sleep_tracker.screen_sleep_time(datetime.now())
                target_ts = (
                    sleep_time.timestamp() if sleep_time is not None
                    else state["night_engaged_at"] + NIGHT_MODE_OFF_DELAY_SECONDS
                )
                if now_ts >= target_ts:
                    result = await lg_tv_control.power_off_if_ours(_log)
                    if result == "settled":
                        state["settled"] = True
                    else:
                        state["next_check_at"] = now_ts + RECHECK_INTERVAL_SECONDS
            # Session request: "have the TV turn on like an hour before
            # I have to get up... if I wake up I know how much time I
            # have." Independent of the power-off settling above --
            # runs every tick while still in night mode, own internal
            # window/dedup (see its own docstring), so it can fire even
            # after this cycle's power-off action has already settled.
            await lg_tv_control.wake_preview_if_due(_log)
        else:
            # Not bedtime: the TV should default to showing the kiosk
            # unless the Xbox is genuinely in use -- checked every tick,
            # not gated on "settled", per this module's own docstring.
            await lg_tv_control.wake_and_switch_if_safe(_log)
            state["settled"] = True

    today = date.today().isoformat()
    if state["volume_floor_date"] != today and now_ts >= state["next_volume_check_at"]:
        ran = await lg_tv_control.enforce_volume_floor(_log)
        if ran:
            state["volume_floor_date"] = today
        else:
            state["next_volume_check_at"] = now_ts + VOLUME_CHECK_RETRY_SECONDS

    # Session audit: "is there a gap we haven't bridged yet" -- see
    # lg_tv_control.verify_tv_ip's own docstring. Once a day, no retry-
    # if-it-fails gating needed the way volume/notifications have --
    # an SSDP scan that finds nothing just means the TV's off right
    # now, same as any other day it'll answer next time this runs.
    if state["ip_check_date"] != today:
        await lg_tv_control.verify_tv_ip(_log)
        state["ip_check_date"] = today

    state["notifications_shown_at"] = await lg_tv_control.send_pending_notifications(
        state["notifications_shown_at"], _log
    )

    _save_state(state)


async def _poll_loop() -> None:
    while True:
        try:
            await _tick()
        except Exception as e:
            _log(f"tick failed: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _main_async() -> None:
    await asyncio.gather(_poll_loop(), lg_tv_control.watch_state(_log))


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
