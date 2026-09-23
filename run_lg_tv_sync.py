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
night_mode_active transition is acted on immediately; if that action
comes back "deferred" (something else -- the Xbox -- is genuinely in
use), this schedules its own recheck for RECHECK_INTERVAL_SECONDS
later rather than waiting for the next real transition or hammering
the TV every single 60s tick. Once an action comes back "settled",
nothing more happens until night_mode_active genuinely flips again.

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

        if not state["settled"] and now_ts >= state["next_check_at"]:
            if desired_active:
                result = asyncio.run(lg_tv_control.power_off_if_ours(_log))
            else:
                result = asyncio.run(lg_tv_control.wake_and_switch_if_safe(_log))
            if result == "settled":
                state["settled"] = True
            else:
                state["next_check_at"] = now_ts + RECHECK_INTERVAL_SECONDS

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
