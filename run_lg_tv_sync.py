"""Entry point for LG TV sync — checks once a minute whether the
dashboard's real night_mode_active state (night_mode.sync_active_state,
read the same way run_spoken_morning_brief.py already reads its own
Upstash-backed signals) has flipped since last checked, and if so,
either powers the TV off (night mode engaging) or wakes it back to our
input (night mode ending) — see lg_tv_control.py's own docstring for
the real "don't interrupt what's already playing" logic behind both of
those.

Run as its own systemd --user service (see systemd/lg-tv-sync.service)
— same lightweight, plain-polling-loop shape as run_spoken_morning_
brief.py, reusing this same venv (aiowebostv installed alongside
everything else here) rather than a separate one."""

import asyncio
import time
from pathlib import Path

import lg_tv_control
import persisted_state

CHECK_INTERVAL_SECONDS = 60
_LAST_STATE_FILE = Path.home() / ".local" / "state" / "kiosk-watchdog" / "lg_tv_sync_last_state"


def _log(msg: str) -> None:
    _LAST_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_file = _LAST_STATE_FILE.parent / "lg-tv-sync.log"
    with open(log_file, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}\n")


def _last_known_state() -> str | None:
    if _LAST_STATE_FILE.exists():
        return _LAST_STATE_FILE.read_text().strip() or None
    return None


def _save_state(active: bool) -> None:
    _LAST_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_STATE_FILE.write_text("true" if active else "false")


def _tick() -> None:
    state = persisted_state.load("night_mode_active", None)
    if state is None:
        return
    active = bool(state.get("active"))
    active_str = "true" if active else "false"
    if active_str == _last_known_state():
        return

    if active:
        asyncio.run(lg_tv_control.power_off_if_ours(_log))
    else:
        asyncio.run(lg_tv_control.wake_and_switch_if_safe(_log))
    _save_state(active)


def main() -> None:
    while True:
        try:
            _tick()
        except Exception as e:
            _log(f"tick failed: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
