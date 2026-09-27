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
source (a real location API) to fix for a "nice to know" feature."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import calendar_client
from config import TIMEZONE

HOME_LABEL = "Home"


def _chloe_events_today(today) -> list[dict]:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return []
    events = calendar_client.todays_events(calendars, today)
    # all_day events (a "Reading Week" banner, say) aren't a real
    # "where is she right now" signal — only real start/end blocks are.
    return [e for e in events if e.get("owner") == "chloe" and not e["all_day"]]


def current_status(now: datetime) -> str:
    """Her calendar_label (School/Gym/Clinical/Appointment/Work) for
    whichever tracked event currently contains `now`, or HOME_LABEL if
    none does. The FIRST matching event wins on the rare chance two
    overlap — real overlaps between her own calendars should be rare
    enough that picking one over the other doesn't matter much."""
    now_aware = now if now.tzinfo else now.replace(tzinfo=ZoneInfo(TIMEZONE))
    for event in _chloe_events_today(now_aware.date()):
        if event["start"] <= now_aware < event["end"]:
            return event.get("calendar_label") or event["summary"]
    return HOME_LABEL
