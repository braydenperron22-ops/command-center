"""Fetches and parses one or more published/private (read-only) ICS
calendar feeds for today's agenda on the Today page — provider-agnostic,
so an iCloud "published calendar" link and a Google Calendar "secret
address in iCal format" work identically, merged into one combined
agenda rather than picking just one source.

Uses icalendar + recurring-ical-events rather than hand-rolling ICS
parsing — real calendars have recurring events (weekly recurring
classes, in this case), and correctly expanding those needs real
recurrence-rule logic (BYDAY, UNTIL, exceptions, timezones), not
something worth getting subtly wrong via a custom implementation.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests
import streamlit as st

import fetch_throttle
from config import TIMEZONE

CACHE_TTL_SECONDS = 15 * 60

# The shift calendar's titles are the raw bulk-imported job title
# ("Customer Experience Associate - Central, Sales"), not something
# worth reading verbatim on a dashboard every morning — normalized to
# "Work" for display. Session request: was an exact-string alias list
# (three near-duplicate spellings — "Customer Experience Associate -
# Central, Sales", "CEA Central - Sales", "CEA - Central, Sales" — that
# needed a new entry every time the calendar import produced yet
# another punctuation/wording variant); now a substring match instead,
# so any shift title containing either phrase gets caught regardless of
# how it's otherwise punctuated or abbreviated. Nothing else about the
# event (start/end/location) is touched.
_WORK_KEYWORDS = ("customer experience associate", "sales")
# Narrower than _WORK_KEYWORDS above on purpose — session context:
# "when you see customer experience associate central [on the
# calendar], that basically means I have to be a teller for like a
# couple hours during the day to cover lunch and stuff... make sure the
# AI knows that." A plain "sales" shift doesn't carry this same real
# annoyance; only the CEA/teller-coverage title does, so this is its
# own check, not folded into the generic Work normalization above.
# Includes the bare "cea" abbreviation too — real calendar imports have
# used both the spelled-out title and "CEA Central - Sales"/"CEA -
# Central, Sales" for the exact same shift (see _WORK_KEYWORDS' own
# comment on that history).
_TELLER_COVERAGE_KEYWORDS = ("customer experience associate", "cea")


def _normalize_summary(raw: str) -> str:
    lowered = raw.strip().lower()
    if any(keyword in lowered for keyword in _WORK_KEYWORDS):
        return "Work"
    return raw


def _is_teller_coverage(raw: str) -> bool:
    lowered = raw.strip().lower()
    return any(keyword in lowered for keyword in _TELLER_COVERAGE_KEYWORDS)

# Same reasoning as every other data client in this app: never let a
# transient fetch/parse failure blank the page, fall back to the last
# successfully parsed agenda instead.
_last_good_events: list[dict] | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_calendar_raw(ics_url: str) -> bytes:
    fetch_throttle.wait_turn()
    resp = requests.get(ics_url, timeout=10)
    resp.raise_for_status()
    return resp.content


def _events_from_one(calendar: dict, today: date) -> list[dict]:
    raw = _fetch_calendar_raw(calendar["url"])
    cal = icalendar.Calendar.from_ical(raw)
    occurrences = recurring_ical_events.of(cal).between(today, today + timedelta(days=1))
    # Trusted per source, not guessed per-event from the title — the
    # shifts on Brayden's Google calendar were bulk-imported by Gemini
    # with a placeholder 1-hour end time on every entry, not the real
    # shift length, so that source is configured show_end_time=false.
    # Keying off which calendar an event came from is more robust than
    # matching on titles like "Sales", which has no reliable "this is a
    # shift" marker in the text itself.
    show_end_time = calendar.get("show_end_time", True)
    events = []
    for e in occurrences:
        start = e.get("DTSTART").dt
        end_field = e.get("DTEND")
        end = end_field.dt if end_field else start
        all_day = not isinstance(start, datetime)
        # Merging multiple ICS sources (see module docstring) means a
        # naive (floating-time) DTSTART from one calendar can end up
        # sorted alongside an aware one from another — comparing them
        # directly raises TypeError and blanks the whole agenda for this
        # cache window. Normalized to aware right after parsing rather
        # than only guarding the sort site, so every consumer of
        # "start"/"end" downstream gets a consistent type. Assumed to be
        # TIMEZONE, not UTC: a floating ICS time is meant to be read in
        # the viewer's own local zone, which for this always-local kiosk
        # is exactly TIMEZONE — and pages_today.py's _row_class already
        # reuses event["start"].tzinfo directly to reinterpret a naive
        # `now` as that same zone, so this also has to actually BE
        # TIMEZONE, not just any aware zone, for that to stay correct.
        if not all_day:
            if start.tzinfo is None:
                start = start.replace(tzinfo=ZoneInfo(TIMEZONE))
            if isinstance(end, datetime) and end.tzinfo is None:
                end = end.replace(tzinfo=ZoneInfo(TIMEZONE))
        raw_summary = str(e.get("SUMMARY", "Untitled"))
        events.append({
            "summary": _normalize_summary(raw_summary),
            "is_teller_coverage": _is_teller_coverage(raw_summary),
            "start": start,
            "end": end,
            "location": str(e.get("LOCATION")) if e.get("LOCATION") else None,
            "all_day": all_day,
            "show_end_time": show_end_time,
        })
    return events


def todays_events(calendars: list[dict], today: date) -> list[dict]:
    """Events overlapping `today` across every configured calendar,
    merged and sorted all-day-first then by start time. Each source is
    fetched independently — one calendar being down or slow doesn't
    lose events from the others; falls back to the last successful
    merge only if every source fails this round."""
    global _last_good_events
    all_events = []
    any_success = False
    for calendar in calendars:
        try:
            all_events.extend(_events_from_one(calendar, today))
        except Exception:
            continue
        any_success = True

    if not any_success:
        return _last_good_events or []

    all_events.sort(key=lambda e: (not e["all_day"], e["start"] if not e["all_day"] else None))
    _last_good_events = all_events
    return all_events
