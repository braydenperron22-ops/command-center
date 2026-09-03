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

from datetime import date, datetime, time, timedelta

import streamlit as st

import calendar_client
import ntfy_client
import persisted_state

WAKE_BUFFER_MINUTES = 90
SLEEP_TARGET_HOURS = 8

# Session follow-up, live: "it's gonna tell me to go to about twelve
# thirty [AM]. That can't happen... make it the latest it can tell me
# to go to bed, ten thirty PM." A long enough wake-buffer-before-a-late-
# commitment day was pushing the 8-hour-back math well past midnight —
# real math, but not a real bedtime anyone should be nudged toward. The
# cap only ever pulls a too-late bedtime EARLIER (to 10:30pm that same
# evening); a day whose natural math already lands before 10:30pm is
# completely untouched — the target is never pushed later than what
# the real wake-up already computed.
BEDTIME_CAP_HOUR = 22
BEDTIME_CAP_MINUTE = 30

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
    day off doesn't get a synthetic bedtime).

    Deliberately stays timezone-AWARE (calendar event start times come
    back that way) rather than matching app.py's own naive `now` —
    same choice commute_reminder's leave_by_time already makes, for the
    same reason: target_ms below (and app.py's own marker div for the
    client-side audio ramp) needs .timestamp() to be correct regardless
    of the server's own system timezone, which only holds for a
    genuinely aware datetime — a naive one's .timestamp() silently
    assumes the MACHINE's local zone, wrong on a UTC-clocked Cloud
    container. (First pass here stripped tzinfo instead, to match `now`
    for a comparison in app.py — fixed the crash locally but shipped a
    real live one: caught immediately after deploy, reverted. The
    comparison that actually needs a naive value belongs at that one
    app.py call site, not baked into this function's own contract.)"""
    commitment = _next_commitment(now)
    if commitment is None:
        return None
    return commitment["start"] - timedelta(minutes=WAKE_BUFFER_MINUTES)


def _apply_bedtime_cap(bedtime: datetime) -> datetime:
    """Never later than BEDTIME_CAP_HOUR:MINUTE on the evening bedtime
    actually belongs to — a bedtime landing after midnight (hour < 12)
    belongs to the PREVIOUS calendar date's evening, the same way
    anyone would actually describe "tonight" past midnight; landing
    that same cap on bedtime's own date for an after-midnight value
    would compare against the WRONG evening (tomorrow's, not
    tonight's) and fail to cap anything at all."""
    evening_date = bedtime.date() if bedtime.hour >= 12 else bedtime.date() - timedelta(days=1)
    cap = datetime.combine(evening_date, time(BEDTIME_CAP_HOUR, BEDTIME_CAP_MINUTE), tzinfo=bedtime.tzinfo)
    return min(bedtime, cap)


def bedtime_for(now: datetime) -> datetime | None:
    wake = wake_time_for(now)
    if wake is None:
        return None
    return _apply_bedtime_cap(wake - timedelta(hours=SLEEP_TARGET_HOURS))


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


# Session follow-up: "a phone ping, not just a screen countdown... the
# on-screen countdown only helps if you're looking at the kiosk." Same
# persisted-dedup shape commute_reminder's own leave-timer push already
# uses (a plain saved list of already-sent keys) — keyed by calendar
# date so a fresh day always gets its own real chance to fire again,
# not just once ever.
_PUSHED_DATES_KEY = "sleep_bedtime_pushed_dates"
_pushed_dates: list[str] = persisted_state.load(_PUSHED_DATES_KEY, [])
PUSH_LEAD_MINUTES = 30


def maybe_push_wind_down(now: datetime) -> None:
    """Call once per rerun (app.py, unconditional, same shape as
    groq_client.notify_if_outage's own call site) — a single push in
    the PUSH_LEAD_MINUTES window before bedtime, never more than one
    per calendar date. Deliberately not wired into the faster 10s toast
    fragment — a background push has no reason to need sub-minute
    reaction time, and the outer script's own cadence is more than
    fine-grained enough to land inside a 30-minute window."""
    bedtime = bedtime_for(now)
    if bedtime is None:
        return
    now_aware = now.replace(tzinfo=bedtime.tzinfo) if bedtime.tzinfo else now
    remaining = (bedtime - now_aware).total_seconds()
    if not (0 <= remaining <= PUSH_LEAD_MINUTES * 60):
        return
    date_key = bedtime.date().isoformat()
    if date_key in _pushed_dates:
        return
    _pushed_dates.append(date_key)
    persisted_state.save(_PUSHED_DATES_KEY, _pushed_dates)
    minutes = max(1, int(remaining // 60))
    ntfy_client.send(
        title="Wind down",
        message=f"Bedtime in {minutes} min",
        priority="default",
        tags="crescent_moon",
    )
