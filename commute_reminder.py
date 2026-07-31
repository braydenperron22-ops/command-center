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

import html
from datetime import datetime, timedelta

import streamlit as st

import calendar_client
import commute_client
import commute_history
import ntfy_client
import persisted_state
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

# check() runs once per rerun (~5s during the whole commute window),
# not once per genuine state change like the milestone/push saves below
# it — loading this fresh from persisted_state on every single call was
# a real, live-confirmed bug (a Redis MONITOR capture showed a GET on
# this key every few seconds around the clock, easily enough volume on
# its own to make a real dent in the whole app's monthly Upstash
# command budget). Same fix shape as news.py's _seen_headlines/_decided
# and gemini_client's periodic cache: load once at import into a module
# global, save only on a genuine change (see check() below — the save
# call only ever runs when a milestone is actually newly due, same as
# it always did).
#
# Per-instance (session request: "every single toast we get... make
# sure every terminal gets its own alert") — "has THIS instance already
# shown this leave-soon toast today" shouldn't block a genuinely
# separate instance from showing its own. commute_milestones below (the
# phone-push dedup) stays on its single shared key on purpose — the
# same phone must never buzz twice for one milestone.
_shown_state: dict = persisted_state.load_per_instance("commute_reminder_shown", {"date": None, "events": {}})


def _leave_text(minutes: int) -> str:
    if minutes == 0:
        return "Leave now"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "Leave in an hour" if hours == 1 else f"Leave in {hours} hours"
    return f"Leave in {minutes} min"


def _alert_label(shift: dict) -> str:
    """The toast label / push title for this shift's leave reminder —
    session request: "make it say work when it's, like, sales or
    customer experience associate or a mix of both... for everything
    else, make it, like, leave soon and then the event." Both push
    ("Leave for work") and the on-screen toast label ("LEAVE SOON")
    used to be hardcoded regardless of which calendar event this
    actually was, even though _current_shift already tracks non-shift
    appointments too (see this module's own docstring). Reuses
    calendar_client's own normalization here rather than re-matching
    "sales"/"customer experience associate"/etc. a second time — a
    real work shift's summary is already collapsed to exactly "Work"
    by the time it reaches this module (see _SUMMARY_ALIASES), so
    checking for that string is checking "is this actually a shift"."""
    if shift["summary"] == "Work":
        return "Work"
    return f"Leave soon: {shift['summary']}"


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


def check(now: datetime) -> dict | None:
    """Call once per rerun. Returns a news_queue-shaped alert dict the
    moment a new milestone is due for whichever shift is currently
    relevant, else None. Milestone "shown" state is tracked per event
    (not just per day) — so a second event later the same day gets its
    own full run of milestones rather than silently inheriting ones
    already used up by an earlier event that happened to cross the
    same minute marks.

    Also pushes a phone notification for the same milestone, once per
    (event, milestone), disk-persisted independently of the on-screen
    "shown" state above (see the push call's own comment further
    down) — both are persisted now, but kept as two separate tracked
    sets rather than unified into one, matching how independently they
    already behaved before this fix."""
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

    # Disk-persisted (persisted_state), not st.session_state — session
    # report: "the ticker tape doesn't show up at all on some pages...
    # I haven't received any [market news]." Traced to this same
    # milestone toast re-firing far more than intended: st.session_state
    # is scoped per browser CONNECTION, and this kiosk's own hourly
    # reload watchdog (app.py) forces a fresh connection every 60
    # minutes — which reset this "shown" tracking right back to empty
    # while a shift's multi-hour leave-window was often still open,
    # letting the same milestone re-fire as if new roughly once an hour
    # for as long as that window stayed active. A toast re-triggering
    # that often effectively monopolized the shared bottom-bar slot,
    # crowding out both the ticker AND whatever real news/market alert
    # would otherwise have become "current" in the same queue. This was
    # previously a known, deliberately-accepted gap (see this function's
    # own history below) — not deliberate anymore now that it's shown to
    # cause real harm. Persisted the same way the push tracking just
    # below already was, for exactly the same reason: a module global
    # alone survives multiple browser sessions but not an actual reload/
    # reconnect; this needs to survive both.
    #
    # Loaded once at import (see _shown_state's own module-level
    # comment), not re-loaded here on every call — a real Redis MONITOR
    # capture caught the very first version of this fix doing exactly
    # that (a GET on this key every few seconds, around the clock),
    # which would have been a real, ongoing drain on the whole app's
    # monthly Upstash command budget for no reason: nothing about this
    # value needs to be re-fetched mid-process, since this same process
    # is the only thing that ever writes it (the save call below stays
    # exactly as targeted as it always was — only when a milestone is
    # actually newly due, not every rerun).
    global _shown_state
    if _shown_state["date"] != now.date().isoformat():
        _shown_state = {"date": now.date().isoformat(), "events": {}}

    event_key = f"{shift['summary']}|{shift['start'].isoformat()}"
    shown_for_event = set(_shown_state["events"].get(event_key, []))

    milestone = _due_milestone(minutes_until_leave, shown_for_event)
    if milestone is None:
        return None
    shown_for_event.add(milestone)
    _shown_state["events"][event_key] = sorted(shown_for_event)
    persisted_state.save_per_instance("commute_reminder_shown", _shown_state)

    # Disk-persisted (persisted_state), not a plain module-level global
    # or st.session_state — session report: "I received the leave for
    # work [alert] three times," then, after a module-level-global fix,
    # a duplicate morning brief push traced to a redeploy resetting an
    # in-memory tracker right back to empty. A module global alone
    # survives multiple browser sessions but not an actual process
    # restart; this needs to survive both.
    pushed = persisted_state.load("commute_milestones", {"date": None, "keys": []})
    if pushed["date"] != now.date().isoformat():
        pushed = {"date": now.date().isoformat(), "keys": []}
    push_key = f"{event_key}|{milestone}"
    label = _alert_label(shift)
    if push_key not in pushed["keys"]:
        pushed["keys"].append(push_key)
        persisted_state.save("commute_milestones", pushed)
        ntfy_client.send(title=label, message=_leave_text(milestone), priority="high", tags="clock3")

    return {"headline": _leave_text(milestone), "category": "Commute", "important": False, "kind": "commute", "label": label}


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


def _remaining_until_leave(now: datetime) -> float | None:
    """Seconds until leave-by time for whichever shift is currently
    tracked (see _current_shift), or None if there's nothing to track
    today — shared by render_leave_headline and leave_headline_active
    so the two can never quietly drift apart on what "active" means."""
    leave_by = leave_by_time(now)
    if leave_by is None:
        return None
    now_aware = now.replace(tzinfo=leave_by.tzinfo)
    return (leave_by - now_aware).total_seconds()


# Escalating visual intensity as leave-by approaches — session
# request: "make the leave in timer chill and it progressively gets
# more intense and alerting the closer we are to the leave time." It
# used to be the same red pulse for the entire HEADLINE_WINDOW_MINUTES
# window, which read as maximally urgent from the moment it first
# appeared — two hours out is advance notice, not a deadline. These
# thresholds must stay in sync with the matching ones in app.py's
# live-countdown ticker script (JS can't call back into Python, so
# that's the two places' agreed contract). This copy only decides the
# very first frame's tier, same as _format_clock below; the JS ticker
# recomputes it for real every second from there, independent of
# Streamlit's 5s rerun cadence.
INTENSITY_AWARE_SECONDS = 60 * 60
INTENSITY_URGENT_SECONDS = 30 * 60
INTENSITY_CRITICAL_SECONDS = 10 * 60


def _intensity_tier(remaining_seconds: float) -> str:
    if remaining_seconds <= 0:
        return "overdue"
    if remaining_seconds <= INTENSITY_CRITICAL_SECONDS:
        return "critical"
    if remaining_seconds <= INTENSITY_URGENT_SECONDS:
        return "urgent"
    if remaining_seconds <= INTENSITY_AWARE_SECONDS:
        return "aware"
    return "calm"


def leave_headline_active(now: datetime) -> bool:
    """Whether render_leave_headline would show anything right now —
    app.py calls this ahead of its own night-dim decision (session
    request: force the display bright while the leave-in countdown is
    up and it's still before 7am, rather than sitting dimmed through an
    early-morning appointment's countdown)."""
    remaining = _remaining_until_leave(now)
    return remaining is not None and -HEADLINE_GRACE_MINUTES * 60 <= remaining <= HEADLINE_WINDOW_MINUTES * 60


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
    Streamlit's own 5s rerun cadence. The intensity tier (see
    _intensity_tier above) rides the same per-second tick via the
    data-intensity marker — the ticker script only manages elements
    that carry it, so the jumbotron/sports countdowns sharing that same
    global ticker are untouched."""
    info = _countdown_info(now)
    if info is None:
        return
    target_ms, tier, text = info
    st.markdown(
        f'<div class="leave-headline intensity-{tier}"><span class="live-countdown" data-intensity '
        f'data-target-ms="{target_ms}" data-format="clock" data-template="Leave in {{}}" '
        f'data-zero-text="Leave now">{text}</span></div>',
        unsafe_allow_html=True,
    )


def _countdown_info(now: datetime) -> tuple[int, str, str] | None:
    """(target_ms, intensity tier, first-frame text) shared by
    render_leave_headline and render_ticker_leave_bar below — same
    window/gating logic, just two different places it ends up on
    screen."""
    leave_by = leave_by_time(now)
    if leave_by is None:
        return None
    remaining = _remaining_until_leave(now)
    if remaining is None or not (-HEADLINE_GRACE_MINUTES * 60 <= remaining <= HEADLINE_WINDOW_MINUTES * 60):
        return None
    target_ms = int(leave_by.timestamp() * 1000)
    tier = _intensity_tier(remaining)
    text = "Leave now" if remaining <= 0 else f"Leave in {_format_clock(remaining)}"
    return target_ms, tier, text


def render_ticker_leave_bar(now: datetime) -> None:
    """Compact countdown for the bottom ticker-bar slot (see ticker.py's
    own .ticker-bar) — session report: today's the exact conflict this
    was built for, a golf tee time (leave-in window) landing during a
    Jays game: "can we format it differently so it doesn't take up the
    same space since that space is crucial for the jumbotron... replace
    the bottom scroll bar with a timer... game alerts and breaking news
    is allowed to trump the timer but at least its still there." The
    big red .leave-headline (render_leave_headline above) already skips
    itself during a jumbotron takeover entirely — there's no room for it
    on that board — which meant an early-shift countdown during game
    time only ever surfaced as a handful of one-off milestone toasts,
    not something continuously visible.

    app.py calls this instead of ticker.py's market/crypto ticker only
    while BOTH _jumbotron_active and this is true (see
    leave_headline_active) AND the toast queue is empty — same slot
    (position/z-index match .ticker-bar exactly), so a real toast
    (a scoring play, breaking news, even this same countdown's own
    milestone toasts) still visually covers it the instant one fires,
    same as it already covers the market ticker today. Nothing here
    duplicates that toast behavior; this only fills the gap between
    toasts instead of showing crypto prices no one's looking at during
    a game."""
    info = _countdown_info(now)
    if info is None:
        return
    target_ms, tier, text = info
    st.markdown(
        f'<div class="jumbo-leave-ticker intensity-{tier}"><span class="live-countdown" data-intensity '
        f'data-target-ms="{target_ms}" data-format="clock" data-template="Leave in {{}}" '
        f'data-zero-text="Leave now">{text}</span></div>',
        unsafe_allow_html=True,
    )


def render_bar(alert: dict) -> None:
    """Same plain, immediately-visible bar as news.render_alert_bar (see
    its own docstring for why the old stretch-then-slide intro was
    dropped entirely) — kept as a separate, smaller implementation
    rather than teaching that function a third "kind" — commute
    reminders aren't news, and shouldn't grow that module's scope to
    accommodate them.

    `alert["label"]` — see _alert_label — falls back to the old fixed
    text only for a caller that predates that key (there isn't one left
    in this codebase, but check()'s own contract doesn't guarantee it
    either); escaped since a non-"Work" label carries a real calendar
    event's summary, external text same as any other unsafe_allow_html
    interpolation in this app."""
    label = html.escape(alert.get("label", "Leave soon"))
    headline = alert.get("headline", "")
    st.markdown(
        f"""<div class="commute-alert-bar">
            <span class="news-breaking-label">{label}</span>
            <span class="news-alert-headline">{headline}</span>
        </div>""",
        unsafe_allow_html=True,
    )
