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

Run as its own systemd --user service (see systemd/lg-tv-sync.service)
— reusing this same venv (aiowebostv installed alongside everything
else here) rather than a separate one."""

import asyncio
import json
import time
from datetime import date
from pathlib import Path

import lg_tv_control
import persisted_state

CHECK_INTERVAL_SECONDS = 20
RECHECK_INTERVAL_SECONDS = 15 * 60
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
    "next_check_at": 0.0,  # don't touch the TV again for the night-mode action before this time
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
            # A genuine transition -- act right away, don't wait for a
            # recheck window that belonged to the PREVIOUS desired state.
            state["desired_active"] = desired_active
            state["settled"] = False
            state["next_check_at"] = 0.0

        if desired_active:
            # Bedtime: power off if ours, with the explicit 15-minute
            # recheck cadence while deferred (Xbox in use at bedtime).
            if not state["settled"] and now_ts >= state["next_check_at"]:
                result = await lg_tv_control.power_off_if_ours(_log)
                if result == "settled":
                    state["settled"] = True
                else:
                    state["next_check_at"] = now_ts + RECHECK_INTERVAL_SECONDS
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
