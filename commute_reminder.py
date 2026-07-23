"""A countdown reminder for when to leave for work, riding the same
bottom-bar toast mechanism the breaking-news alerts use (see app.py's
news_queue) — it "drops into" that bar rather than being a separate UI
element, so it doesn't compete for space with anything else.

Considers every shift-type calendar event today (see calendar_client's
show_end_time — the same signal that already distinguishes a real
shift from a normal calendar event on the Today page), not just the
first — an early appointment shouldn't use up the day's only leave
tracking and leave a later shift with none at all. Only ever engages
with one event at a time (see _current_shift): whichever is earliest
and hasn't gone stale yet, so once one event's window closes the next
one in the day picks up automatically. Nothing shows on a day with no
shift, and nothing fires hours late if the dashboard happened to be
asleep through the whole window.
"""

from datetime import datetime, timedelta

import streamlit as st

import calendar_client
import commute_client
import commute_history
import ntfy_client
from config import COMMUTE_DESTINATION

EARLY_BUFFER_MINUTES = 10
# How volatile the default commute's been recently bumps the buffer
# above the flat minimum — swinging readings suggest changing
# conditions (an accident just happened, traffic's actively building)
# worth padding for, where a steady commute doesn't need it. Only
# applies to the default Work commute: that's the only route with any
# history (see commute_client.route's record_history), so a one-off
# event location always just gets the flat EARLY_BUFFER_MINUTES.
ADAPTIVE_BUFFER_LOOKBACK_SECONDS = 60 * 60
ADAPTIVE_BUFFER_MIN_READINGS = 3  # below this, there's not enough signal to trust — use the flat minimum
ADAPTIVE_BUFFER_MAX_MINUTES = 20
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
# you actually want it parked on screen: the final two hours, plus a
# short grace period after so it doesn't vanish the instant you're
# running late. (Session request: bumped from 60 to 120.)
HEADLINE_WINDOW_MINUTES = 120
HEADLINE_GRACE_MINUTES = 10

# Intro sequencing via the toast-label-intro/toast-headline-intro CSS
# animations in theme.py — see news.py's STRETCH_END for why this is a
# CSS animation with a negative animation-delay rather than plain
# per-rerun inline styles (same mechanism, kept in sync with news.py's
# copy of these two constants).
STRETCH_END = 1.8
SLIDE_END = 3.0


def _leave_text(minutes: int) -> str:
    if minutes == 0:
        return "Leave now"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "Leave in an hour" if hours == 1 else f"Leave in {hours} hours"
    return f"Leave in {minutes} min"


def _todays_shift_events(now: datetime) -> list[dict]:
    """Every shift-type event today, sorted by start time — plural,
    since a day can have more than one (an appointment earlier, a
    shift later)."""
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return []
    events = calendar_client.todays_events(calendars, now.date())
    return sorted(
        (e for e in events if not e["all_day"] and not e["show_end_time"]),
        key=lambda e: e["start"],
    )


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


def _adaptive_buffer_minutes(using_default_destination: bool) -> float:
    """EARLY_BUFFER_MINUTES, bumped up when the default commute has
    been swinging around a lot in the last hour — a widening spread
    between readings suggests conditions actively changing, worth
    padding for beyond the flat minimum. Custom event destinations
    have no history to judge from (see commute_client.route's
    record_history), so they always just get the flat minimum."""
    if not using_default_destination:
        return EARLY_BUFFER_MINUTES
    readings = commute_history.readings_within(ADAPTIVE_BUFFER_LOOKBACK_SECONDS)
    if len(readings) < ADAPTIVE_BUFFER_MIN_READINGS:
        return EARLY_BUFFER_MINUTES
    minutes = [r["duration_seconds"] / 60 for r in readings]
    spread = max(minutes) - min(minutes)
    return min(EARLY_BUFFER_MINUTES + spread, ADAPTIVE_BUFFER_MAX_MINUTES)


def todays_destination(now: datetime) -> dict:
    """Where today's commute actually goes right now, resolved to a
    real {"lat", "lon", "label"} — shared by leave_by_time and the
    Today page's commute tile so they always agree on the destination
    rather than the tile silently still assuming Work while the
    countdown routes somewhere else. Falls back to COMMUTE_DESTINATION
    when there's no currently-relevant shift, no location on it, or
    geocoding fails."""
    current = _current_shift(now)
    if current is None:
        return COMMUTE_DESTINATION
    return _destination_for_shift(current[0]) or COMMUTE_DESTINATION


def _due_milestone(minutes_until_leave: float, shown_for_event: set[int]) -> int | None:
    """The largest not-yet-shown milestone we've now reached — skips
    (marks as shown without firing) any larger ones already blown past,
    so waking up from sleep with 25 minutes left fires "Leave in 30",
    not a stale "Leave in 60"."""
    candidates = [m for m in MILESTONES_MINUTES if minutes_until_leave <= m]
    if not candidates:
        return None
    due = min(candidates)
    if due in shown_for_event:
        return None
    for m in MILESTONES_MINUTES:
        if m > due:
            shown_for_event.add(m)
    return due


def _leave_by_for_shift(shift: dict) -> datetime | None:
    """leave_by for one specific shift event — None if the commute
    time to its destination isn't available."""
    destination = _destination_for_shift(shift)
    route = commute_client.route(destination)
    if not route:
        return None
    buffer_minutes = _adaptive_buffer_minutes(using_default_destination=destination is None)
    return shift["start"] - timedelta(seconds=route["duration_seconds"]) - timedelta(minutes=buffer_minutes)


def _current_shift(now: datetime) -> tuple[dict, datetime] | None:
    """Whichever of today's shift events is the one to currently pay
    attention to, with its leave_by — the first (earliest-starting)
    one whose leave_by hasn't gone stale yet (more than
    LATEST_FIRE_MINUTES past). Once one event's window closes, this
    naturally moves on to the next event in the day rather than
    staying stuck on a shift that's already come and gone."""
    for shift in _todays_shift_events(now):
        leave_by = _leave_by_for_shift(shift)
        if leave_by is None:
            continue
        now_aware = now.replace(tzinfo=leave_by.tzinfo)
        minutes_until_leave = (leave_by - now_aware).total_seconds() / 60
        if minutes_until_leave >= LATEST_FIRE_MINUTES:
            return shift, leave_by
    return None


def leave_by_time(now: datetime) -> datetime | None:
    """When you need to leave for whichever of today's shift events is
    currently relevant (see _current_shift), given the live commute
    estimate to wherever that event's own calendar location says — not
    always Work. None if there's no relevant shift today or the
    commute time isn't available. Shared by check(), below, and the
    persistent headline, so both agree on the exact same target."""
    current = _current_shift(now)
    return current[1] if current else None


# Module-level, NOT st.session_state (unlike `state` below, which
# stays session-scoped for the on-screen toast's own "shown" tracking —
# that part wasn't reported as broken). Session report: "I received the
# leave for work [alert] three times." st.session_state is scoped per
# browser connection; any reconnect (a Cloud restart, a dropped
# connection) starts a fresh session with empty state, so a dedup built
# on it fires again from that session's point of view even though the
# milestone already pushed once from a previous connection. The push
# specifically needs to survive that in a way the on-screen toast
# doesn't strictly need to, so it gets its own independent, process-
# wide tracking here.
_notified_milestones: set[str] = set()
_notified_milestones_date = None


def check(now: datetime) -> dict | None:
    """Call once per rerun. Returns a news_queue-shaped alert dict the
    moment a new milestone is due for whichever shift is currently
    relevant, else None. Milestone "shown" state is tracked per event
    (not just per day) — so a second event later the same day gets its
    own full run of milestones rather than silently inheriting ones
    already used up by an earlier event that happened to cross the
    same minute marks.

    Also pushes a phone notification for the same milestone, once per
    (event, milestone) — see _notified_milestones's own comment for why
    that's tracked separately from the on-screen "shown" state above."""
    current = _current_shift(now)
    if current is None:
        return None
    shift, leave_by = current

    # `now` arrives naive but already IN the local zone — reinterpret,
    # don't convert (see pages_today.py's _row_class for why .replace()
    # and not .astimezone()).
    now_aware = now.replace(tzinfo=leave_by.tzinfo)
    minutes_until_leave = (leave_by - now_aware).total_seconds() / 60

    if not (LATEST_FIRE_MINUTES <= minutes_until_leave <= max(MILESTONES_MINUTES)):
        return None

    state = st.session_state.setdefault("commute_reminder", {"date": None, "shown": {}})
    if state["date"] != now.date():
        state["date"] = now.date()
        state["shown"] = {}

    event_key = f"{shift['summary']}|{shift['start'].isoformat()}"
    shown_for_event = state["shown"].setdefault(event_key, set())

    milestone = _due_milestone(minutes_until_leave, shown_for_event)
    if milestone is None:
        return None
    shown_for_event.add(milestone)

    global _notified_milestones_date
    if _notified_milestones_date != now.date():
        _notified_milestones_date = now.date()
        _notified_milestones.clear()
    push_key = f"{event_key}|{milestone}"
    if push_key not in _notified_milestones:
        _notified_milestones.add(push_key)
        ntfy_client.send(title="Leave for work", message=_leave_text(milestone), priority="high", tags="clock3")

    return {"headline": _leave_text(milestone), "category": "Commute", "important": False, "kind": "commute"}


def _format_clock(remaining_seconds: float) -> str:
    """H:MM:SS (or MM:SS under an hour) — session request: "why do they
    not show seconds like our other client side timer in the jumbotron
    mode. make it look like that," matching pages_jumbotron._fmt_
    countdown's own fallback exactly. Only ever the first frame's
    value; app.py's global live-countdown ticker (data-format="clock")
    recomputes this for real every second from there."""
    total = max(0, int(remaining_seconds))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def render_leave_headline(now: datetime) -> None:
    """A standalone red headline above the hero clock/weather row —
    page-independent (renders regardless of which of the 6 rotating
    pages is currently up, unlike anything living inside a page's own
    render()), so it's actually visible during the one window that
    matters: the final HEADLINE_WINDOW_MINUTES before you need to leave,
    through a HEADLINE_GRACE_MINUTES grace period after. Silent outside that
    window — hours-out awareness is what the milestone toasts above are
    for; this is specifically for keeping tabs once it's close.

    Ticks for real once a second via app.py's global live-countdown
    ticker script (session request, after the jumbotron got the same
    treatment: "make that logic work for all the timer elements...
    specifically the big red leave in timer") — the text below is only
    ever the first frame's value; data-target-ms/data-template/
    data-zero-text drive everything from here on, independent of
    Streamlit's own 5s rerun cadence."""
    leave_by = leave_by_time(now)
    if leave_by is None:
        return
    now_aware = now.replace(tzinfo=leave_by.tzinfo)
    remaining = (leave_by - now_aware).total_seconds()
    if not (-HEADLINE_GRACE_MINUTES * 60 <= remaining <= HEADLINE_WINDOW_MINUTES * 60):
        return
    target_ms = int(leave_by.timestamp() * 1000)
    text = "Leave now" if remaining <= 0 else f"Leave in {_format_clock(remaining)}"
    st.markdown(
        f'<div class="leave-headline"><span class="live-countdown" data-target-ms="{target_ms}" '
        f'data-format="clock" data-template="Leave in {{}}" data-zero-text="Leave now">{text}</span></div>',
        unsafe_allow_html=True,
    )


def render_bar(alert: dict, elapsed: float, variant: str = "a") -> None:
    """Same stretch-then-slide intro as news.render_alert_bar (kept as
    a separate, smaller implementation rather than teaching that
    function a third "kind" — commute reminders aren't news, and
    shouldn't grow that module's scope to accommodate them).

    `variant` — see news.render_alert_bar's docstring; same reason,
    same fix."""
    delay = f"animation-delay: -{elapsed:.2f}s;"
    st.markdown(
        f"""<div class="commute-alert-bar">
            <span class="news-breaking-label toast-label-anim-{variant}" style="{delay}">LEAVE SOON</span>
            <span class="news-alert-headline toast-headline-anim-{variant}" style="{delay}">{alert['headline']}</span>
        </div>""",
        unsafe_allow_html=True,
    )
