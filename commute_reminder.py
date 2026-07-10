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

EARLY_BUFFER_MINUTES = 10
# Widest to narrowest — fired in this order as the leave-by time
# approaches, each exactly once per day.
MILESTONES_MINUTES = [60, 45, 30, 20, 15, 10, 5, 3, 0]
# Floor for how late a stale reminder is still worth firing at all —
# past this, the dashboard was probably asleep through the whole
# window, and "Leave now" 40 minutes after the fact isn't useful.
LATEST_FIRE_MINUTES = -30

STRETCH_END = 1.8
SLIDE_END = 3.0


def _leave_text(minutes: int) -> str:
    if minutes == 0:
        return "Leave now"
    if minutes == 60:
        return "Leave in an hour"
    return f"Leave in {minutes} min"


def _todays_shift_start(now: datetime) -> datetime | None:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    events = calendar_client.todays_events(calendars, now.date())
    shifts = sorted(
        (e for e in events if not e["all_day"] and not e["show_end_time"]),
        key=lambda e: e["start"],
    )
    return shifts[0]["start"] if shifts else None


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


def check(now: datetime) -> dict | None:
    """Call once per rerun. Returns a news_queue-shaped alert dict the
    moment a new milestone is due, else None."""
    shift_start = _todays_shift_start(now)
    if shift_start is None:
        return None

    route = commute_client.route()
    if not route:
        return None

    # `now` arrives naive but already IN the local zone — reinterpret,
    # don't convert (see pages_today.py's _row_class for why .replace()
    # and not .astimezone()).
    now_aware = now.replace(tzinfo=shift_start.tzinfo)
    leave_by = shift_start - timedelta(seconds=route["duration_seconds"]) - timedelta(minutes=EARLY_BUFFER_MINUTES)
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
