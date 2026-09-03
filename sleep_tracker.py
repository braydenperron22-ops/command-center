"""Bedtime countdown + a dynamic "stay quiet until you're actually up"
window — session request: "I really need to start prioritizing my
sleep more... a bedtime timer. Gauge what my commitments are the
following day, and then what time I need to wake up at, ideally one or
two hours before the actual thing. Give me a bedtime, and count down to
that bedtime when we're within two hours of it." Session-confirmed
numbers: 8 hours of sleep, 90 minutes of wake-up lead time.

Two separate things this module answers, both derived from the exact
same "what's the next real commitment" lookup so they can never
disagree with each other:

1. bedtime_headline_candidate — a countdown in the shared red-headline
   rotation (headline_rotation.py), same shape/mechanism as the leave-
   timer's own countdown there, active starting 2 hours out (the
   user's own number).

2. wake_time_for — read by app.py to dynamically extend BOTH night
   mode's dim window and the quiet-hours audio floor (kioskAlertVolume)
   past their fixed 4:30am/5am defaults on a day the real wake-up time
   is later than that — session request: "make sure the display
   actually stays properly dim... too bright early in the morning
   indirectly impacts sleep" and "the only things that should sound
   before my boots are on the ground are the leave van alerts... unless
   [it's] genuinely impactful." Kept as a plain function other modules
   call rather than owning that rendering itself — night_mode.py and
   app.py's own kiosk audio script already own those mechanisms, this
   just answers "how late does quiet need to run today."

Reuses commute_reminder's own shift-event shape and filtering
(_todays_shift_events' exact rule: not all_day and not show_end_time)
rather than reinventing what counts as a real commitment — see that
module's own docstring for why show_end_time is excluded (the TD shift
calendar's own end time is a known placeholder, never real data; start
times are real)."""

from datetime import date, datetime, timedelta

import streamlit as st

import calendar_client

WAKE_BUFFER_MINUTES = 90
SLEEP_TARGET_HOURS = 8

# Same "2 hours" the user asked for, and the same number commute_
# reminder's own leave-timer headline has always used (commute_
# reminder.HEADLINE_WINDOW_MINUTES) — not a coincidence, just the
# established convention for "how far out does a countdown start
# showing" across every source in the shared rotation.
HEADLINE_WINDOW_MINUTES = 120
# Unlike missing a leave-by time (genuinely time-critical, a short
# grace), staying up past a self-set bedtime is a softer miss — worth
# a nudge, not worth nagging all night. Drops off an hour after bedtime
# rather than lingering.
OVERDUE_GRACE_MINUTES = 60


def _shift_events_for(calendars: list[dict], day: date) -> list[dict]:
    events = calendar_client.todays_events(calendars, day)
    return sorted(
        (e for e in events if not e["all_day"] and not e["show_end_time"]),
        key=lambda e: e["start"],
    )


def _next_commitment(now: datetime) -> dict | None:
    """The earliest real, still-upcoming shift/appointment — checks
    today first (covers the "it's 2am, the shift I'm waking up for is
    technically later today" case) then tomorrow, so this reads
    correctly regardless of what time it is right now when it's
    called."""
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    for day_offset in (0, 1):
        day = (now + timedelta(days=day_offset)).date()
        for event in _shift_events_for(calendars, day):
            start = event["start"]
            now_aware = now.replace(tzinfo=start.tzinfo) if start.tzinfo else now
            if start > now_aware:
                return event
    return None


def wake_time_for(now: datetime) -> datetime | None:
    """The real target wake-up time — the next real commitment's own
    start time, minus the session-confirmed 90-minute lead. None if
    there's nothing on the calendar to wake up for at all (a genuine
    day off doesn't get a synthetic bedtime)."""
    commitment = _next_commitment(now)
    if commitment is None:
        return None
    return commitment["start"] - timedelta(minutes=WAKE_BUFFER_MINUTES)


def bedtime_for(now: datetime) -> datetime | None:
    wake = wake_time_for(now)
    if wake is None:
        return None
    return wake - timedelta(hours=SLEEP_TARGET_HOURS)


def _format_clock(remaining_seconds: float) -> str:
    """Same H:MM:SS/MM:SS shape commute_reminder._format_clock and
    pages_jumbotron's own countdown fallback already use — first-frame
    value only, the shared live-countdown ticker script recomputes it
    for real every second from target_ms."""
    total = max(0, int(remaining_seconds))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def bedtime_headline_candidate(now: datetime) -> dict | None:
    """{"text", "css_class", "target_ms", "template", "zero_text"} —
    same shape every other headline_rotation.py source uses. Active
    from HEADLINE_WINDOW_MINUTES before bedtime through
    OVERDUE_GRACE_MINUTES after it; rotation-notice once inside the
    last 30 minutes, rotation-warning once actually overdue — a real
    nudge once it's genuinely past time, not just a flat calm color the
    whole 3-hour span."""
    bedtime = bedtime_for(now)
    if bedtime is None:
        return None
    now_aware = now.replace(tzinfo=bedtime.tzinfo) if bedtime.tzinfo else now
    remaining = (bedtime - now_aware).total_seconds()
    if not (-OVERDUE_GRACE_MINUTES * 60 <= remaining <= HEADLINE_WINDOW_MINUTES * 60):
        return None
    target_ms = int(bedtime.timestamp() * 1000)
    if remaining <= 0:
        css_class = "rotation-warning"
    elif remaining <= 30 * 60:
        css_class = "rotation-notice"
    else:
        css_class = "rotation-calm"
    text = "Bedtime now" if remaining <= 0 else f"Bedtime in {_format_clock(remaining)}"
    return {
        "text": text,
        "css_class": css_class,
        "target_ms": target_ms,
        "template": "Bedtime in {}",
        "zero_text": "Bedtime now",
    }
