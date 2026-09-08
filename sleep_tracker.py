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

# Session request: "when there's ten minutes left on the timer, I want
# to say, like, get into bed... in order to get the full eight hours of
# sleep, I need to be asleep when that timer hits zero." The countdown
# itself (bedtime_for) is already backed off by WAKE_BUFFER_MINUTES from
# the actual commitment, but that buffer covers waking up and getting
# moving — it says nothing about the minutes it takes to physically stop
# what you're doing and get in bed BEFORE the target, which is the whole
# point of "asleep by zero." Same 600-second boundary the leave-timer's
# own client-side script (app.py's kiosk-live-countdown) already uses
# for ITS "critical" tier — not a coincidence, reusing that exact
# vocabulary/threshold rather than inventing bedtime's own.
BEDTIME_CTA_MINUTES = 10


def _shift_events_for(calendars: list[dict], day: date) -> list[dict]:
    events = calendar_client.todays_events(calendars, day)
    return sorted(
        (e for e in events if not e["all_day"] and not e["show_end_time"]),
        key=lambda e: e["start"],
    )


# Session report, live: a 2pm golf tee time got treated as "something
# to wake up early for," computing a wake_time of 12:30pm and keeping
# night mode dimmed until then — screen still showing the night clock
# at almost 8am. _shift_events_for's own filter (not all_day, not
# show_end_time) is the same one commute_reminder's leave-timer uses,
# and that's fine there — you leave for a 2pm tee time same as a 7am
# shift. But this module's whole premise is "wake up N minutes before
# THE THING" — only sound for a genuine morning commitment, never an
# afternoon appointment nobody needs an early alarm for. Real appointment
# data (golf, apartment shopping) surfaced this immediately; no reason
# to wait for a second live report to fix it the same way the earlier
# date-boundary bugs got fixed only after shipping.
WAKE_RELEVANT_CUTOFF_HOUR = 12


def _next_commitment(now: datetime) -> dict | None:
    """The earliest real, still-upcoming MORNING commitment — checks
    today first (covers the "it's 2am, the shift I'm waking up for is
    technically later today" case) then tomorrow, so this reads
    correctly regardless of what time it is right now when it's
    called. Skips anything starting at or after WAKE_RELEVANT_CUTOFF_
    HOUR regardless of which day it falls on — an afternoon commitment
    is real for commute_reminder's own leave-timer purposes, but never
    a reason for THIS module to compute an early wake-up/bedtime."""
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    for day_offset in (0, 1):
        day = (now + timedelta(days=day_offset)).date()
        for event in _shift_events_for(calendars, day):
            start = event["start"]
            if start.hour >= WAKE_RELEVANT_CUTOFF_HOUR:
                continue
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


# Session request: "make the bedtime clock visible on jumbotron, just
# like the leave in timer... takes over the bottom rotating bar." Same
# shared-source-of-truth shape commute_reminder._countdown_info already
# established for the leave timer — one function feeding both the
# headline-rotation candidate AND the jumbotron ticker-slot renderer,
# so the two can never disagree. Tier values are the SAME intensity-*
# vocabulary .jumbo-leave-ticker's own CSS (theme.py) already defines
# for the leave timer (calm/aware/urgent/critical/overdue). Used to only
# need 3 of the 5 (no distinct "aware" or "critical" phase) — now uses
# "critical" too, for the real "get into bed" call-to-action window (see
# BEDTIME_CTA_MINUTES) — still no new CSS, .intensity-critical already
# exists for the leave timer's own identical 10-minute boundary.
_TIER_TO_ROTATION_CLASS = {
    "calm": "rotation-calm",
    "urgent": "rotation-notice",
    "critical": "rotation-critical",
    "overdue": "rotation-warning",
}
# The live-countdown ticker's per-second text is a client-side JS
# substitution into this template (app.py's kiosk-live-countdown script)
# — a *static* string baked in at whatever Streamlit rerun last ran, not
# re-evaluated against tier logic every second. That's fine: a rerun
# lands well inside a minute in practice, so the wording change at the
# CTA boundary shows up with the same small, expected lag every other
# tier transition already has here.
_TIER_TEMPLATE = {
    "calm": "Bedtime in {}",
    "urgent": "Bedtime in {}",
    "critical": "Get into bed — {}",
}
_ZERO_TEXT = "Get into bed now"


def _countdown_info(now: datetime) -> tuple[int, str, str] | None:
    """(target_ms, intensity tier, first-frame text) — bedtime's own
    version of commute_reminder._countdown_info. Active from
    HEADLINE_WINDOW_MINUTES before bedtime through OVERDUE_GRACE_MINUTES
    after it. Tiers: "calm" (>30min), "urgent" (<=30min, still just a
    countdown — plenty of time to wrap up whatever you're doing),
    "critical" (<=BEDTIME_CTA_MINUTES, the actual "stop and go" moment —
    text becomes the call-to-action, not just a number), "overdue" (past
    bedtime, within the grace window — same CTA, framed as already
    late)."""
    bedtime = bedtime_for(now)
    if bedtime is None:
        return None
    now_aware = now.replace(tzinfo=bedtime.tzinfo) if bedtime.tzinfo else now
    remaining = (bedtime - now_aware).total_seconds()
    if not (-OVERDUE_GRACE_MINUTES * 60 <= remaining <= HEADLINE_WINDOW_MINUTES * 60):
        return None
    target_ms = int(bedtime.timestamp() * 1000)
    if remaining <= 0:
        tier = "overdue"
        text = _ZERO_TEXT
    elif remaining <= BEDTIME_CTA_MINUTES * 60:
        tier = "critical"
        text = f"Get into bed — {_format_clock(remaining)}"
    elif remaining <= 30 * 60:
        tier = "urgent"
        text = f"Bedtime in {_format_clock(remaining)}"
    else:
        tier = "calm"
        text = f"Bedtime in {_format_clock(remaining)}"
    return target_ms, tier, text


def bedtime_headline_active(now: datetime) -> bool:
    """Cheap boolean check, same shape as commute_reminder.
    leave_headline_active — for callers that only need "is this active
    right now," not the full candidate dict (app.py's own jumbotron
    ticker-slot dispatch is exactly that)."""
    return _countdown_info(now) is not None


def bedtime_headline_candidate(now: datetime) -> dict | None:
    """{"text", "css_class", "target_ms", "template", "zero_text"} —
    same shape every other headline_rotation.py source uses."""
    info = _countdown_info(now)
    if info is None:
        return None
    target_ms, tier, text = info
    return {
        "text": text,
        "css_class": _TIER_TO_ROTATION_CLASS[tier],
        "target_ms": target_ms,
        "template": _TIER_TEMPLATE.get(tier, "Bedtime in {}"),
        "zero_text": _ZERO_TEXT,
    }


def countdown_span_html(now: datetime) -> tuple[str, str] | None:
    """(tier, html) for the raw live-countdown <span> — same underlying
    data as bedtime_headline_candidate/render_ticker_bedtime_bar, just
    without a fixed wrapper div baked in, so a caller with its own
    layout (night_mode's single-markdown full-screen view, the BRDN
    terminal's own panel grid) can place and style it itself rather than
    being stuck with the jumbotron ticker's own bottom-bar shape. None
    when there's nothing to show right now, same as every other public
    check in this module."""
    info = _countdown_info(now)
    if info is None:
        return None
    target_ms, tier, text = info
    template = _TIER_TEMPLATE.get(tier, "Bedtime in {}")
    html_snippet = (
        f'<span class="live-countdown" data-intensity data-target-ms="{target_ms}" '
        f'data-format="clock" data-template="{template}" data-zero-text="{_ZERO_TEXT}">{text}</span>'
    )
    return tier, html_snippet


def render_ticker_bedtime_bar(now: datetime) -> None:
    """The jumbotron ticker-slot version — same .jumbo-leave-ticker
    class/shape as commute_reminder.render_ticker_leave_bar (matches
    that slot's position/z-index exactly), just bedtime's own text/tier
    instead of the leave timer's. See this function's own call site in
    app.py for the real reason it exists: a 10pm game running past
    bedtime used to leave the countdown invisible for hours, same
    problem the leave-timer ticker was originally built to solve.
    Session follow-up: also called unconditionally (self-guarding, same
    as here) from pages_brdn_terminal.py's own footer — the BRDN
    terminal is the other full-screen takeover mode that used to blank
    this out, since it isn't gated on _jumbotron_active either."""
    result = countdown_span_html(now)
    if result is None:
        return
    tier, span_html = result
    st.markdown(f'<div class="jumbo-leave-ticker intensity-{tier}">{span_html}</div>', unsafe_allow_html=True)


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
