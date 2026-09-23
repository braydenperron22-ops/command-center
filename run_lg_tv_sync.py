"""Entry point for LG TV sync — checks once a minute whether the
dashboard's real night_mode_active state (night_mode.sync_active_state,
read the same way run_spoken_morning_brief.py already reads its own
Upstash-backed signals) has flipped, and if so, either powers the TV
off (night mode engaging) or wakes it back to our input (night mode
ending) — see lg_tv_control.py's own docstring for the real "don't
interrupt what's already playing" logic behind both of those, and for
what "settled" vs "deferred" mean below.

Session request: "check the state every 15 minutes until it's back to
HDMI 1 or the TV is off itself, and then rest there." A fresh
night_mode_active transition to ENGAGING (bedtime) is acted on
immediately; if that action comes back "deferred" (the Xbox is
genuinely in use), this schedules its own recheck for RECHECK_INTERVAL_
SECONDS later rather than hammering the TV every single 60s tick.
Once "settled", nothing more happens on that side until the next real
transition.

Session follow-up: "there's a tangible difference between me playing
Xbox at 8:30 in the morning being done... and me turning off the TV
when it's time for bed. If I'm done playing Xbox and turn off the TV
in the morning, I want you to turn that TV back on and put it to the
kiosk... as simple as possible." The NOT-bedtime direction is
therefore handled differently on purpose: wake_and_switch_if_safe runs
on EVERY tick while night mode is inactive, not just once on a fresh
transition with a 15-minute recheck -- it's already a safe no-op both
when the TV's already on the kiosk (nothing to do) and when it's
genuinely on the Xbox (defers, does nothing), so there's no real cost
to checking continuously, and it means the TV comes back to the kiosk
within about a minute of actually being turned off, any time of day,
not just right after night mode ends.

Also runs the daily volume-floor check (lg_tv_control.
enforce_volume_floor) independently of all of the above -- see its own
docstring for why that one isn't gated on which input is active -- and
forwards any queued phone-style notification (lg_tv_control.
send_pending_notifications) to the TV screen every tick, but only ever
while genuinely away from the kiosk's own input.

Run as its own systemd --user service (see systemd/lg-tv-sync.service)
— same lightweight, plain-polling-loop shape as run_spoken_morning_
brief.py, reusing this same venv (aiowebostv installed alongside
everything else here) rather than a separate one."""

import asyncio
import json
import time
from datetime import date
from pathlib import Path

import lg_tv_control
import persisted_state

CHECK_INTERVAL_SECONDS = 60
RECHECK_INTERVAL_SECONDS = 15 * 60
# How often to retry the daily volume floor if the TV wasn't reachable
# the last time -- not every single 60s tick (the TV being off most of
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


def _tick() -> None:
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
                result = asyncio.run(lg_tv_control.power_off_if_ours(_log))
                if result == "settled":
                    state["settled"] = True
                else:
                    state["next_check_at"] = now_ts + RECHECK_INTERVAL_SECONDS
        else:
            # Not bedtime: the TV should default to showing the kiosk
            # unless the Xbox is genuinely in use -- checked every tick,
            # not gated on "settled", per this module's own docstring.
            asyncio.run(lg_tv_control.wake_and_switch_if_safe(_log))
            state["settled"] = True

    today = date.today().isoformat()
    if state["volume_floor_date"] != today and now_ts >= state["next_volume_check_at"]:
        ran = asyncio.run(lg_tv_control.enforce_volume_floor(_log))
        if ran:
            state["volume_floor_date"] = today
        else:
            state["next_volume_check_at"] = now_ts + VOLUME_CHECK_RETRY_SECONDS

    state["notifications_shown_at"] = asyncio.run(
        lg_tv_control.send_pending_notifications(state["notifications_shown_at"], _log)
    )

    _save_state(state)


def main() -> None:
    while True:
        try:
            _tick()
        except Exception as e:
            _log(f"tick failed: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
