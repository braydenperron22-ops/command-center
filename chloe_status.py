"""Chloe's real-time status — "School"/"Gym"/etc, or "Home" when she's
not inside any tracked calendar event right now. Session request:
"I want to know like when she's at school and when she gets home and
when she goes to the gym... nice passive data to know. I want to know
if she's at school before calling her type thing." Derived straight
from her own tagged calendar events (calendar_client.py's "owner"/
"calendar_label" fields, added when her calendars were connected) —
no new data source, no per-minute location tracking, just a read of
whatever's already fetched for the agenda.

"Home" is a default, not a confirmed fact — the only real signal this
has is "inside a tracked event" or "not." Once her last event of the
day ends, this reads as "Home" even though she could still be in
transit; that's an accepted, disclosed simplification (see
current_status's own docstring), not something worth a second data
source (a real location API) to fix for a "nice to know" feature.

Session follow-up: "I only want her events to show if she's here...
if she's spending the night and she's got school the next morning,
then I want it to appear on the kiosk." Tried automatic detection
first (network device presence) — ruled out live: "Apple devices hide
their device data." Landed on the simplest reliable thing instead: a
plain manual flag, toggled by the Q hotkey (app.py's own kiosk-hotkeys
script) and held in Upstash via persisted_state so it survives a kiosk
restart — same "don't over-engineer, ask directly" reasoning the
shopping list page already used."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import calendar_client
import persisted_state
from config import TIMEZONE

HOME_LABEL = "Home"

_HERE_KEY = "chloe_here"
_chloe_here: bool = persisted_state.load(_HERE_KEY, False)


def is_here() -> bool:
    return _chloe_here


# Real bug, found live: "toast alerts stay up for way too long... the
# Chloe is here toast is still up, probably five or six minutes." The
# arrival announcement (app.py's own Q-hotkey handler) had zero dedup —
# a few real Q presses in a row while testing queued that many separate
# 30-second toasts back to back (toast_queue is process-wide, no size
# cap), which plays out looking exactly like one toast frozen on screen
# for minutes. In-memory, not persisted_state — this only needs to
# survive across reruns within the same running process (exactly what
# a plain module-level variable in an imported module already does),
# not across a real restart; a restart-then-genuine-arrival should
# always get to announce, not be silently suppressed by a stale
# pre-restart cooldown.
ANNOUNCE_COOLDOWN_SECONDS = 5 * 60
_last_announced_at = 0.0


def should_announce_arrival(now_ts: float | None = None) -> bool:
    """True at most once per ANNOUNCE_COOLDOWN_SECONDS — call only on a
    genuine away->here flip. Stamps the cooldown itself (not a separate
    "mark" step) so the check and the commit can't drift apart."""
    global _last_announced_at
    now_ts = now_ts if now_ts is not None else time.time()
    if now_ts - _last_announced_at < ANNOUNCE_COOLDOWN_SECONDS:
        return False
    _last_announced_at = now_ts
    return True


def set_here(value: bool) -> None:
    """Called only from app.py's own one-shot Q-hotkey handler — never
    on every rerun (see persisted_state's own "never load() on every
    rerun" rule; this module already respects that by loading once at
    import time above, and only ever writes here, on a real toggle)."""
    global _chloe_here
    _chloe_here = value
    persisted_state.save(_HERE_KEY, value)


def _chloe_events_today(today) -> list[dict]:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return []
    events = calendar_client.todays_events(calendars, today)
    # all_day events (a "Reading Week" banner, say) aren't a real
    # "where is she right now" signal — only real start/end blocks are.
    return [e for e in events if e.get("owner") == "chloe" and not e["all_day"]]


def current_status(now: datetime) -> str | None:
    """Her calendar_label (School/Gym/Clinical/Appointment/Work) for
    whichever tracked event currently contains `now`, HOME_LABEL if
    she's here but not in one, or None entirely if is_here() is False
    — her schedule isn't relevant to this household's kiosk on a night
    she isn't actually staying over. The FIRST matching event wins on
    the rare chance two overlap — real overlaps between her own
    calendars should be rare enough that picking one over the other
    doesn't matter much."""
    if not is_here():
        return None
    now_aware = now if now.tzinfo else now.replace(tzinfo=ZoneInfo(TIMEZONE))
    for event in _chloe_events_today(now_aware.date()):
        if event["start"] <= now_aware < event["end"]:
            return event.get("calendar_label") or event["summary"]
    return HOME_LABEL
