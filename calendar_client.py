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

import icalendar
import recurring_ical_events
import requests
import streamlit as st

CACHE_TTL_SECONDS = 15 * 60

# Same reasoning as every other data client in this app: never let a
# transient fetch/parse failure blank the page, fall back to the last
# successfully parsed agenda instead.
_last_good_events: list[dict] | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_calendar_raw(ics_url: str) -> bytes:
    resp = requests.get(ics_url, timeout=10)
    resp.raise_for_status()
    return resp.content


def _events_from_one(ics_url: str, today: date) -> list[dict]:
    raw = _fetch_calendar_raw(ics_url)
    cal = icalendar.Calendar.from_ical(raw)
    occurrences = recurring_ical_events.of(cal).between(today, today + timedelta(days=1))
    events = []
    for e in occurrences:
        start = e.get("DTSTART").dt
        end_field = e.get("DTEND")
        end = end_field.dt if end_field else start
        all_day = not isinstance(start, datetime)
        events.append({
            "summary": str(e.get("SUMMARY", "Untitled")),
            "start": start,
            "end": end,
            "location": str(e.get("LOCATION")) if e.get("LOCATION") else None,
            "all_day": all_day,
        })
    return events


def todays_events(ics_urls: list[str], today: date) -> list[dict]:
    """Events overlapping `today` across every configured calendar,
    merged and sorted all-day-first then by start time. Each source is
    fetched independently — one calendar being down or slow doesn't
    lose events from the others; falls back to the last successful
    merge only if every source fails this round."""
    global _last_good_events
    all_events = []
    any_success = False
    for url in ics_urls:
        try:
            all_events.extend(_events_from_one(url, today))
        except Exception:
            continue
        any_success = True

    if not any_success:
        return _last_good_events or []

    all_events.sort(key=lambda e: (not e["all_day"], e["start"] if not e["all_day"] else None))
    _last_good_events = all_events
    return all_events
