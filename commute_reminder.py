"""A countdown reminder for when to leave for work, riding the same
bottom-bar toast mechanism the breaking-news alerts use (see app.py's
news_queue) — it "drops into" that bar rather than being a separate UI
element, so it doesn't compete for space with anything else.

Only ever considers TODAY's earliest shift-type calendar event (see
calendar_client's show_end_time — the same signal that already
distinguishes a real shift from a normal calendar event on the Today
page), and only fires within a reasonable active window around it —
nothing shows on a day with no shift, and nothing fires hours late if
the dashboard happened to be asleep through the whole window.
"""

from datetime import datetime, timedelta

import streamlit as st

import calendar_client
import commute_client
from config import COMMUTE_DESTINATION

EARLY_BUFFER_MINUTES = 10
# Widest to narrowest — fired in this order as the leave-by time
# approaches, each exactly once per day. Starts two hours out so there's
# real advance notice in the morning, not just a last-hour scramble.
MILESTONES_MINUTES = [120, 90, 60, 45, 30, 20, 15, 10, 5, 3, 0]
# Floor for how late a stale reminder is still worth firing at all —
# past this, the dashboard was probably asleep through the whole
# window, and "Leave now" 40 minutes after the fact isn't useful.
LATEST_FIRE_MINUTES = -30

# The persistent headline (render_leave_headline, below) is deliberately
# narrower than the toast milestones above — hours-out visibility is
# what those toasts are for. The headline is for the one window where
# you actually want it parked on screen: the final hour, plus a short
# grace period after so it doesn't vanish the instant you're running late.
HEADLINE_WINDOW_MINUTES = 60
HEADLINE_GRACE_MINUTES = 10

STRETCH_END = 1.8
SLIDE_END = 3.0


def _leave_text(minutes: int) -> str:
    if minutes == 0:
        return "Leave now"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "Leave in an hour" if hours == 1 else f"Leave in {hours} hours"
    return f"Leave in {minutes} min"


def _todays_shift_event(now: datetime) -> dict | None:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    events = calendar_client.todays_events(calendars, now.date())
    shifts = sorted(
        (e for e in events if not e["all_day"] and not e["show_end_time"]),
        key=lambda e: e["start"],
    )
    return shifts[0] if shifts else None


def _destination_for_shift(shift: dict) -> dict | None:
    """{"lat", "lon", "label"} from the shift's own calendar location,
    or None if it doesn't have one or geocoding fails — None means
    "use the default COMMUTE_DESTINATION" to every caller here, so a
    shift with no location (or a bad one) behaves exactly as before."""
    if not shift.get("location"):
        return None
    # Geocoding gets the full address (better match quality), but the
    # label is just the venue/first segment ("Highview Golf Course",
    # not the whole street address) — this ends up in a tile-label
    # ("HOME → ...") alongside the short "Work" it usually reads, and a
    # full address there would wrap across several lines instead.
    geocoded = commute_client.geocode(" ".join(shift["location"].splitlines()))
    if not geocoded:
        return None
    label = shift["location"].splitlines()[0].split(",")[0].strip()
    return {**geocoded, "label": label}


def todays_destination(now: datetime) -> dict:
    """Where today's commute actually goes, resolved to a real
    {"lat", "lon", "label"} — shared by leave_by_time and the Today
    page's commute tile so they always agree on the destination rather
    than the tile silently still assuming Work while the countdown
    routes somewhere else. Falls back to COMMUTE_DESTINATION when
    there's no shift today, no location on it, or geocoding fails."""
    shift = _todays_shift_event(now)
    if shift is None:
        return COMMUTE_DESTINATION
    return _destination_for_shift(shift) or COMMUTE_DESTINATION


def _due_milestone(minutes_until_leave: float, shown_today: set[int]) -> int | None:
    """The largest not-yet-shown milestone we've now reached — skips
    (marks as shown without firing) any larger ones already blown past,
    so waking up from sleep with 25 minutes left fires "Leave in 30",
    not a stale "Leave in 60"."""
    candidates = [m for m in MILESTONES_MINUTES if minutes_until_leave <= m]
    if not candidates:
        return None
    due = min(candidates)
    if due in shown_today:
        return None
    for m in MILESTONES_MINUTES:
        if m > due:
            shown_today.add(m)
    return due


def leave_by_time(now: datetime) -> datetime | None:
    """When you need to leave today to arrive EARLY_BUFFER_MINUTES early
    for your first shift, given the live commute estimate to wherever
    that shift's own calendar location says — not always Work — None
    if there's no shift today or the commute time isn't available.
    Shared by check(), below, and the persistent headline, so both
    agree on the exact same target."""
    shift = _todays_shift_event(now)
    if shift is None:
        return None

    route = commute_client.route(_destination_for_shift(shift))
    if not route:
        return None

    return shift["start"] - timedelta(seconds=route["duration_seconds"]) - timedelta(minutes=EARLY_BUFFER_MINUTES)


def check(now: datetime) -> dict | None:
    """Call once per rerun. Returns a news_queue-shaped alert dict the
    moment a new milestone is due, else None."""
    leave_by = leave_by_time(now)
    if leave_by is None:
        return None

    # `now` arrives naive but already IN the local zone — reinterpret,
    # don't convert (see pages_today.py's _row_class for why .replace()
    # and not .astimezone()).
    now_aware = now.replace(tzinfo=leave_by.tzinfo)
    minutes_until_leave = (leave_by - now_aware).total_seconds() / 60

    if not (LATEST_FIRE_MINUTES <= minutes_until_leave <= max(MILESTONES_MINUTES)):
        return None

    state = st.session_state.setdefault("commute_reminder", {"date": None, "shown": set()})
    if state["date"] != now.date():
        state["date"] = now.date()
        state["shown"] = set()

    milestone = _due_milestone(minutes_until_leave, state["shown"])
    if milestone is None:
        return None
    state["shown"].add(milestone)

    return {"headline": _leave_text(milestone), "category": "Commute", "important": False, "kind": "commute"}


def _format_minutes(remaining_seconds: float) -> str:
    # Worded units ("1h 26m"/"45 min"), not a colon-separated clock face
    # ("1:26") — a colon format reads as a live stopwatch, and this only
    # updates once a minute (see render_leave_headline), so it'd look
    # stuck rather than calm. Words don't carry that "should be actively
    # ticking" expectation.
    total_minutes = max(0, int(remaining_seconds) // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes} min"


def render_leave_headline(now: datetime) -> None:
    """A standalone red headline above the hero clock/weather row —
    page-independent (renders regardless of which of the 6 rotating
    pages is currently up, unlike anything living inside a page's own
    render()), so it's actually visible during the one window that
    matters: the final hour before you need to leave, through a
    HEADLINE_GRACE_MINUTES grace period after. Silent outside that
    window — hours-out awareness is what the milestone toasts above are
    for; this is specifically for keeping tabs once it's close."""
    leave_by = leave_by_time(now)
    if leave_by is None:
        return
    now_aware = now.replace(tzinfo=leave_by.tzinfo)
    remaining = (leave_by - now_aware).total_seconds()
    if not (-HEADLINE_GRACE_MINUTES * 60 <= remaining <= HEADLINE_WINDOW_MINUTES * 60):
        return
    text = "Leave now" if remaining <= 0 else f"Leave in {_format_minutes(remaining)}"
    st.markdown(f'<div class="leave-headline">{text}</div>', unsafe_allow_html=True)


def render_bar(alert: dict, elapsed: float) -> None:
    """Same stretch-then-slide intro as news.render_alert_bar (kept as
    a separate, smaller implementation rather than teaching that
    function a third "kind" — commute reminders aren't news, and
    shouldn't grow that module's scope to accommodate them)."""
    if elapsed < STRETCH_END:
        label_progress = elapsed / STRETCH_END
        label_style = f"opacity: {label_progress:.2f}; transform: translateY(0); letter-spacing: {0.5 * label_progress:.2f}em;"
        headline_style = "opacity: 0; transform: translateX(16px);"
    elif elapsed < SLIDE_END:
        slide_progress = (elapsed - STRETCH_END) / (SLIDE_END - STRETCH_END)
        label_style = f"opacity: {max(1 - slide_progress * 1.3, 0):.2f}; transform: translateX({-140 * slide_progress:.0f}%); letter-spacing: 0.5em;"
        headline_style = f"opacity: {min(slide_progress * 1.3, 1):.2f}; transform: translateX({16 * (1 - slide_progress):.0f}px);"
    else:
        label_style = "opacity: 0; transform: translateX(-140%);"
        headline_style = "opacity: 1; transform: translateX(0);"

    st.markdown(
        f"""<div class="commute-alert-bar">
            <span class="news-breaking-label" style="{label_style}">LEAVE SOON</span>
            <span class="news-alert-headline" style="{headline_style}">{alert['headline']}</span>
        </div>""",
        unsafe_allow_html=True,
    )
