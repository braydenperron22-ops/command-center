"""Publishes the voice assistant's current state to the same Upstash-
backed persisted_state.py store the kiosk watchdog / night-mode-sync
scripts already use — session requirement: "a visible dashboard status
showing something like MIC: MUTED / LISTENING FOR WAKE WORD /
LISTENING / PROCESSING / SPEAKING... always be obvious when the
assistant is actively processing a command." Reusing this exact channel
(rather than inventing a new one) means the Streamlit Cloud app can
show this badge with zero new infrastructure — see app.py's own small
addition that reads this same key back.

One states dict, one save call per real transition — not a poll loop
writing on a timer, so this costs a small, bounded number of Upstash
commands (state changes, not wall-clock ticks) against the same
500k/month budget every other persisted_state writer in this app
already respects."""

import time

from voice import config

try:
    import persisted_state
except Exception:  # pragma: no cover - persisted_state needs `streamlit` importable
    persisted_state = None

# Mirrors the session's own requested vocabulary directly — app.py's
# badge renders these labels close to verbatim rather than recoding
# them a second time.
STATES = ("muted", "listening_for_wake_word", "listening", "processing", "speaking")

_last_state: str | None = None


def set_state(state: str, detail: str = "") -> None:
    """Best-effort — a failed write here must never take down the
    voice pipeline itself (same rule persisted_state.save's own
    docstring already establishes for every other caller in this app).
    No-ops on a repeated identical state so a state that legitimately
    holds for a while (idle wake-word listening) doesn't spam Upstash
    on every orchestrator loop tick."""
    global _last_state
    if state not in STATES:
        state = "listening_for_wake_word"
    if state == _last_state:
        return
    _last_state = state
    if persisted_state is None:
        return
    try:
        persisted_state.save(config.STATUS_KEY, {
            "state": state,
            "detail": detail,
            "assistant_name": config.ASSISTANT_NAME,
            "at": time.time(),
        })
    except Exception:
        pass


def is_muted() -> bool:
    """Reads the mic-mute flag — see voice/audio_io.py for how this
    gets set (a software toggle, pending real hardware mute — see this
    project's own architecture writeup on why a physical mute button is
    the preferred long-term answer)."""
    if persisted_state is None:
        return False
    try:
        return bool(persisted_state.load(config.MUTE_KEY, False))
    except Exception:
        return False


def set_muted(muted: bool) -> None:
    if persisted_state is None:
        return
    try:
        persisted_state.save(config.MUTE_KEY, bool(muted))
    except Exception:
        pass
    set_state("muted" if muted else "listening_for_wake_word")
