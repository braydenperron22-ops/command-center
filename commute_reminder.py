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
import kiosk_tts
import ntfy_client
import persisted_state
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN

# Session request: "update the commute logic to implement a hybrid
# approach... query TomTom using a dynamic future departure time...
# simultaneously pull live incident data... output the maximum (worse)
# of the two values so my UI always takes the safer estimate." Two
# real, separate gaps this closes: a LIVE-only call (the old behavior)
# has no idea a recurring bottleneck is about to build if it hasn't
# started yet (checked at 7am, an 8am jam doesn't show); a PREDICTIVE-
# only call (TomTom's IQ Routes historical profile for a future time)
# has no idea about a fresh, unprecedented anomaly today specifically
# (an accident that just happened isn't in historical data). Taking
# whichever is actually worse catches both. See _hybrid_route below.
#
# How much worse (TomTom's own trafficDelayInSeconds — real minutes
# beyond free-flow, not a comparison against commute_history, which
# only retains 2 hours and can't answer "what's normal for this route"
# at all) counts as worth an amber warning on the Today page's commute
# tile (see pages_today.py's own _render_commute) — half of the normal
# EARLY_BUFFER_MINUTES felt like the right proportion: enough to
# meaningfully eat into that buffer, not just routine noise.
AMBER_DELAY_THRESHOLD_SECONDS = 5 * 60

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

# Session report: "picking my friend up... it's pinging me two hours
# before I have to leave... they woke me up every single time... make
# it so it's not so loud" — for a genuinely early leave_by (this
# session's real example: ~5-6am), the wide-notice milestones above 30
# minutes land at 3-4:30am, hours before the person's actually awake.
# The user's own workaround (deleting the calendar event entirely to
# stop the pings) defeats the whole feature, so this isn't just a
# volume problem — see commute_reminder's own _leave_volume_ceiling for
# that half; this is the OTHER half, whether a far-out milestone should
# fire at all at that hour. Milestones at or under
# QUIET_MILESTONE_MIN_MINUTES always fire regardless of hour (leaving
# in 30/20/15/10/5/3/0 minutes is genuinely needed to not be late, no
# matter how early); only the wider "plenty of time left" heads-ups
# (120/90/60/45) get held back before QUIET_MILESTONE_CUTOFF_HOUR — same
# hour already used as the "reasonable to be awake" line for the
# volume ramp and the morning dim-undim ramp, kept as its own constant
# since this gates something different (whether an alert fires at all,
# not how loud one that does fire should be).
QUIET_MILESTONE_CUTOFF_HOUR = 5
QUIET_MILESTONE_MIN_MINUTES = 30

# Session request: "make the leave in alert silent until the one hour
# mark." Distinct from both quiet-hour gates above: QUIET_MILESTONE_*
# decides whether a wide-notice milestone fires AT ALL before 5am;
# _leave_volume_ceiling decides how LOUD an alert that does fire can
# get. Neither one made the two widest heads-ups (120/90 minutes out)
# silent on an ordinary daytime shift — they always played the same
# chime + spoken line as every other milestone. This is a third,
# independent gate: those two stay fully visible (the toast, the
# countdown headline/ticker) but genuinely produce zero sound —
# chime included, not just the spoken line — until the countdown
# reaches this threshold. Applied in render_bar via a data-silent
# attribute the client checks before making any noise at all (see
# app.py's kioskPlayLeaveVoice), same data-driven shape as data-volume.
LEAVE_ALERT_SILENT_ABOVE_MINUTES = 60

# The persistent headline (leave_headline_candidate, below — shown via
# headline_rotation.py's unified rotation) is deliberately narrower
# than the toast milestones above — hours-out visibility is
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


def _is_home_event(shift: dict) -> bool:
    """True when this event's own calendar location is just "Home" —
    session request: "if the location of an event is... home, don't do
    the whole leave in blah blah blah... it's like a task that I have
    to do... from home... just the timer... don't do the talking."
    A commute-style countdown (drive time to somewhere, a voice reading
    "leave in") doesn't mean anything for something happening right
    where the kiosk already is — matched against COMMUTE_ORIGIN's own
    "Home" label rather than a separate hardcoded string, since that's
    already this app's one canonical name for the home address."""
    location = (shift.get("location") or "").strip().lower()
    return location == COMMUTE_ORIGIN["label"].strip().lower()


def _leave_text(minutes: int, is_home: bool = False) -> str:
    # is_home swaps "Leave" for "Starts" throughout — a home event has
    # nowhere to leave FOR, just a start time to count down to (see
    # _is_home_event's own docstring).
    verb = "Starts" if is_home else "Leave"
    if minutes == 0:
        return "Starts now" if is_home else "Leave now"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{verb} in an hour" if hours == 1 else f"{verb} in {hours} hours"
    return f"{verb} in {minutes} min"


def _alert_label(shift: dict, is_home: bool = False) -> str:
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
    checking for that string is checking "is this actually a shift".

    is_home skips the "Leave soon: " framing entirely (see
    _is_home_event) — just the event's own name, same as "Work" already
    gets on its own."""
    if is_home:
        return shift["summary"]
    if shift["summary"] == "Work":
        return "Work"
    return f"Leave soon: {shift['summary']}"


def _leave_spoken_text(shift: dict, minutes: int) -> str:
    """The exact sentence app.py's kiosk voice speaks for this leave-in
    toast, via Piper (kiosk_tts.py) — session follow-up to the server-
    side-TTS work, moving this out of app.py's own kioskPlayLeaveVoice,
    which used to pull it back apart from the already-rendered label/
    headline text (stripping "Leave soon: " back off, lowercasing the
    headline, etc.) after check() built them. Built directly from the
    same shift/milestone this module already has on hand instead, same
    wording: a named event speaks its own name first ("Golf tee time —
    leave in 15 minutes."), a plain Work shift just speaks the countdown
    ("Leave in 15 minutes.")."""
    headline = _leave_text(minutes)
    if headline.endswith(" min"):
        headline = headline[: -len(" min")] + " minutes"
    if shift["summary"] != "Work":
        return f"{shift['summary']} — {headline.lower()}."
    return f"{headline}."


# Session request: "make it so the alert fires at 100% for leave in
# notifications regardless of time" (a fix for an early-morning jump
# scare) later walked back once that same flat 100% became its own
# problem — "I don't want the leave in timer to wake everyone in my
# family up... but I want it to be louder during the day." Originally
# tied the ceiling to only ONE thing — how early THIS shift's real
# leave-by time is (a 4am leave-by gets a genuinely quiet ceiling, an
# 8am one gets the normal full one) — using the same ramp shape
# already validated for severe weather's own morning ramp (app.py's
# kioskAlertVolume). LEAVE_VOLUME_FLOOR is a floor, not a mute — still
# meant to be heard in-room, just not house-wide.
#
# Session report: "it was like six thirty and it was jolting me awake"
# — leave_by-only missed a real case. An ordinary 8am shift gets the
# full 1.0 ceiling under that scheme, and that ceiling applied to
# EVERY milestone toast for the shift, including the early ones (the
# 2-hour-out, 90-minute-out toasts) that fire well before 8am — a
# 6:30am toast for an 8am shift played at ~68% just from the day ramp
# alone, on top of whatever the chime/voice layers add, loud enough to
# read as a jolt. leave_by alone can't see that: it only knows when
# the shift starts, not when THIS particular alert is actually firing.
LEAVE_VOLUME_FLOOR = 0.35
LEAVE_VOLUME_RAMP_START_HOUR = 5
LEAVE_VOLUME_RAMP_END_HOUR = 8


def _volume_ramp(hour: float) -> float:
    """Shared ramp shape: LEAVE_VOLUME_FLOOR at/before RAMP_START_HOUR,
    full by RAMP_END_HOUR, linear in between. Takes a plain hour
    (fractional) so it can be applied to either a shift's leave_by or
    the actual current time — see _leave_volume_ceiling."""
    if hour <= LEAVE_VOLUME_RAMP_START_HOUR:
        return LEAVE_VOLUME_FLOOR
    if hour >= LEAVE_VOLUME_RAMP_END_HOUR:
        return 1.0
    span = LEAVE_VOLUME_RAMP_END_HOUR - LEAVE_VOLUME_RAMP_START_HOUR
    return LEAVE_VOLUME_FLOOR + (1.0 - LEAVE_VOLUME_FLOOR) * (hour - LEAVE_VOLUME_RAMP_START_HOUR) / span


def _leave_volume_ceiling(now: datetime, leave_by: datetime) -> float:
    """Max playback volume for a leave-countdown alert — the LOWER of
    two independent ceilings, not just leave_by's own:

    - the shift ceiling (how early leave_by itself is) — keeps a 4am
      shift's alerts quiet even right at "leave now," so a genuinely
      early shift never gets blasted just because it's the urgent
      final milestone.
    - the right-now ceiling (how early it actually is when THIS alert
      is firing) — the piece that was missing. Without it, an early
      milestone toast for a normal, later shift inherited that shift's
      full daytime ceiling even while it was still firing in the quiet
      early morning.

    Taking the min means an early shift is never louder than its own
    floor allows, AND an early milestone for a later shift stays quiet
    too — while the two ceilings converge at leave_by itself, so the
    actual "leave now" moment still reaches the shift's true ceiling
    once it's genuinely that time."""
    shift_ceiling = _volume_ramp(leave_by.hour + leave_by.minute / 60)
    now_ceiling = _volume_ramp(now.hour + now.minute / 60)
    return min(shift_ceiling, now_ceiling)


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
    when there's no currently-relevant shift, no location on it,
    geocoding fails, or (see _is_home_event) the location is just
    "Home" — geocoding that literal string is exactly as likely to
    resolve to some unrelated place actually named "Home" somewhere
    else entirely as it is to fail outright, and either way there's no
    real commute to show for a task happening at the kiosk's own
    address; same fallback as "no shift today at all" is the honest
    answer here too."""
    current = _current_shift(now)
    if current is None or _is_home_event(current[0]):
        return COMMUTE_DESTINATION
    return _destination_for_shift(current[0]) or COMMUTE_DESTINATION


def commute_status(now: datetime) -> dict | None:
    """{"route", "destination", "leave_by", "is_congested"} for
    pages_today.py's own commute tile — None only if even a plain live
    call fails outright (no API key, TomTom unreachable, etc).

    Uses the hybrid predictive+live route (_hybrid_route_for_shift)
    whenever there's an active shift to actually plan a departure
    around — leave_by is real in that case, and route is whichever of
    predictive/live is worse. With no active shift (or a home event,
    which has no commute to route at all), there's no target departure
    time to predict FOR, so this falls back to a plain live route to
    todays_destination — same as the tile's own original behavior —
    with leave_by as None and is_congested still meaningful (TomTom's
    own live delay is real information even without a specific
    deadline to weigh it against)."""
    current = _current_shift(now)
    if current is not None and not _is_home_event(current[0]):
        shift = current[0]
        # _current_shift's own leave_by (current[1]) is numerically the
        # same as hybrid_leave_by below (both trace back to the same
        # cached calls) — recomputed here rather than reused because
        # this needs the ROUTE dict too (for is_congested/incident/
        # predicted), which _current_shift's return doesn't carry.
        result = _hybrid_route_for_shift(shift)
        if result:
            route, hybrid_leave_by = result
            destination = _destination_for_shift(shift) or COMMUTE_DESTINATION
            return {
                "route": route,
                "destination": destination,
                "leave_by": hybrid_leave_by,
                "is_congested": is_congested(route),
            }

    destination = todays_destination(now)
    using_default = destination is COMMUTE_DESTINATION
    route = commute_client.route(None if using_default else destination)
    if not route:
        return None
    return {"route": route, "destination": destination, "leave_by": None, "is_congested": is_congested(route)}


def _due_milestone(minutes_until_leave: float, shown_for_event: set[int], now_hour: float) -> int | None:
    """The largest not-yet-shown milestone we've now reached — skips
    (marks as shown without firing) any larger ones already blown past,
    so waking up from sleep with 25 minutes left fires "Leave in 30",
    not a stale "Leave in 60". Before QUIET_MILESTONE_CUTOFF_HOUR, this
    same skip-forward logic also drops any candidate wider than
    QUIET_MILESTONE_MIN_MINUTES — a genuinely early leave_by (this
    session's real example: picking someone up for 6am) would otherwise
    still fire its 120/90/60/45-minute heads-ups in the 3-4:30am dead of
    night. The close-in milestones (30 and under) are exempt from this
    and always fire regardless of hour — those are the ones that
    actually prevent being late, not just an FYI with time to spare."""
    candidates = [
        m for m in MILESTONES_MINUTES
        if minutes_until_leave <= m
        and (m <= QUIET_MILESTONE_MIN_MINUTES or now_hour >= QUIET_MILESTONE_CUTOFF_HOUR)
    ]
    if not candidates:
        return None
    due = min(candidates)
    if due in shown_for_event:
        return None
    for m in MILESTONES_MINUTES:
        if m > due:
            shown_for_event.add(m)
    return due


def _hybrid_route(destination: dict | None, live: dict, target_time: datetime) -> dict:
    """The worse (by duration_seconds) of the already-fetched LIVE route
    and a fresh predictive route for `target_time` — see this module's
    own AMBER_DELAY_THRESHOLD_SECONDS comment for the two real gaps
    this closes. Tags the result with "predicted": True when the
    predictive call is the one that actually won, so a caller can tell
    "this is worse because of a recurring pattern TomTom's historical
    profile already knows about" apart from "this is worse because of
    something happening live right now" — both real, just worth
    labeling differently on screen. Never fails outright: a failed or
    merely-not-worse predictive call just means the live route was
    already the right (or the only available) answer."""
    predictive = commute_client.route(destination, depart_at=target_time)
    if predictive is None or predictive["duration_seconds"] <= live["duration_seconds"]:
        return {**live, "predicted": False}
    return {**predictive, "predicted": True}


def _hybrid_route_for_shift(shift: dict) -> tuple[dict, datetime] | None:
    """(route, leave_by) for one specific shift event, using the hybrid
    predictive+live approach — None if the commute time to its
    destination isn't available (or for a home event, which has no
    commute at all — see _leave_by_for_shift's own docstring).

    Bootstraps its own predictive target_time from a first live-only
    estimate (this shift's own rough leave_by under live-only
    conditions) — the predictive call needs a real time to predict FOR,
    not an arbitrary guess. That bootstrap live call is the exact same
    call _hybrid_route needs anyway, so it's fetched once here and
    passed through rather than fetched twice."""
    if _is_home_event(shift):
        return None
    destination = _destination_for_shift(shift)
    live = commute_client.route(destination)
    if not live:
        return None
    buffer_minutes = _adaptive_buffer_minutes(using_default_destination=destination is None)
    rough_leave_by = shift["start"] - timedelta(seconds=live["duration_seconds"]) - timedelta(minutes=buffer_minutes)
    route = _hybrid_route(destination, live, rough_leave_by)
    leave_by = shift["start"] - timedelta(seconds=route["duration_seconds"]) - timedelta(minutes=buffer_minutes)
    return route, leave_by


def is_congested(route: dict | None) -> bool:
    """Whether this route's own real traffic delay (TomTom's
    trafficDelayInSeconds, whichever of live/predictive it came from)
    is bad enough to earn the amber warning state — see
    AMBER_DELAY_THRESHOLD_SECONDS' own comment for why the threshold is
    what it is, and why this checks the delay itself rather than
    comparing against commute_history (too short a retention window to
    mean anything as a "what's normal" baseline)."""
    return bool(route) and route.get("delay_seconds", 0) >= AMBER_DELAY_THRESHOLD_SECONDS


def _leave_by_for_shift(shift: dict) -> datetime | None:
    """leave_by for one specific shift event — None if the commute
    time to its destination isn't available.

    For a home event (_is_home_event) this is just the event's own
    start time, no commute math at all: there's no destination to
    geocode and no drive time to subtract for something happening
    right where the kiosk already is. Every downstream consumer of
    "leave_by" (the milestone countdown, the persistent headline, the
    ticker) still works unchanged either way — the target instant they
    count down to is just the start time itself instead of a back-
    computed depart time, and _is_home_event/check() below handle
    swapping "Leave" for "Starts" in what actually gets displayed.

    Session request: "output the maximum (worse) of the two values so
    my UI always takes the safer estimate" — uses _hybrid_route_for_
    shift's own hybrid predictive+live duration instead of a plain
    live-only route, so leave_by itself (not just the countdown display)
    reflects whichever is genuinely worse."""
    if _is_home_event(shift):
        return shift["start"]
    result = _hybrid_route_for_shift(shift)
    return result[1] if result else None


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

    milestone = _due_milestone(minutes_until_leave, shown_for_event, now.hour + now.minute / 60)
    if milestone is None:
        return None
    # Captured before the .add() below — genuinely the first milestone
    # ever shown for THIS event (usually the 120-minute one, but not
    # always: a kiosk that starts mid-window, e.g. after a redeploy,
    # can enter partway through and see a smaller number first — this
    # still counts as "the leave timer starting" for that event, since
    # it's this event's own first alert regardless of which number it
    # happens to be). Session request: "as soon as the leave in timer
    # starts for the day... have the morning brief read out to me" —
    # app.py's own orchestration uses this to decide when to swap in
    # the spoken brief; see morning_briefing.spoken_brief_for_leave_
    # timer's own docstring for why this alone isn't sufficient (a
    # second, unrelated shift/errand later the same day would also be
    # "first for ITS OWN event" — that function's own once-per-
    # CALENDAR-DAY dedup is the other half of getting this right).
    is_first_leave_alert_today = not shown_for_event
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
    # is_home: no commute framing (see _is_home_event) — plain "Starts
    # in X" toast/push text, no "Leave soon: " label, and no spoken
    # voice line at all (kiosk_tts/render_bar only synthesize audio
    # when "summary" is non-empty — see render_bar's own comment on
    # data-audio-b64). render_bar's chime is unconditional either way,
    # so a home event still gets the same little ping, just no talking.
    is_home = _is_home_event(shift)
    label = _alert_label(shift, is_home)
    headline = _leave_text(milestone, is_home)
    if push_key not in pushed["keys"]:
        pushed["keys"].append(push_key)
        persisted_state.save("commute_milestones", pushed)
        ntfy_client.send(title=label, message=headline, priority="high", tags="clock3")

    return {
        "headline": headline,
        "category": "Commute",
        "important": False,
        "kind": "commute",
        "label": label,
        "summary": "" if is_home else _leave_spoken_text(shift, milestone),
        "volume": _leave_volume_ceiling(now_aware, leave_by),
        # See LEAVE_ALERT_SILENT_ABOVE_MINUTES above — this milestone's
        # own distance from leave-by, not is_home (a silent-tier home
        # event and an audible-tier one both still just skip the voice
        # line via "summary" above; this is the separate all-sound-off
        # gate for the wide early heads-ups specifically).
        "silent": milestone > LEAVE_ALERT_SILENT_ABOVE_MINUTES,
        # False for a home event even if it genuinely is this event's
        # first alert — a home event never gets a spoken line at all
        # (see "summary" above), so there's nothing for app.py's own
        # spoken-brief override to attach to.
        "is_first_leave_alert_today": is_first_leave_alert_today and not is_home,
    }


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
    today — shared by _countdown_info and leave_headline_active so the
    two can never quietly drift apart on what "active" means."""
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
    """Whether the leave-in countdown (rendered via headline_rotation.py's
    unified rotation now, see leave_headline_candidate below — this
    used to have its own standalone render_leave_headline, retired once
    every "red headline" source moved into that shared rotation) would
    show anything right now — app.py calls this ahead of its own
    night-dim decision (session request: force the display bright while
    the leave-in countdown is up and it's still before 7am, rather than
    sitting dimmed through an early-morning appointment's countdown)."""
    remaining = _remaining_until_leave(now)
    return remaining is not None and -HEADLINE_GRACE_MINUTES * 60 <= remaining <= HEADLINE_WINDOW_MINUTES * 60


def _countdown_info(now: datetime) -> tuple[int, str, str, bool] | None:
    """(target_ms, intensity tier, first-frame text, is_home) shared by
    leave_headline_candidate below and render_ticker_leave_bar further
    down — same window/gating logic, just two different places it ends
    up on screen (the unified top-of-screen rotation vs. the jumbotron's
    own compact ticker slot). is_home (_is_home_event) is what lets
    both callers swap "Leave" for "Starts" without each re-deriving it
    themselves.

    Session request: "if there is a detour in effect, I should see a
    meaningful delay... the leave in timers should be reflective of
    this." The delay itself already was — _leave_by_for_shift (via
    _current_shift above) subtracts a real, traffic-aware duration_
    seconds, which already accounts for whatever detour TomTom's
    routing engine is actually taking around a closure, not a fixed
    baseline (now the HYBRID predictive+live duration specifically —
    see _hybrid_route_for_shift — so a baked-in future bottleneck shows
    up here too, not just a live-right-now one). What was missing was
    the WHY: a shifted number with no visible reason looks identical to
    a slow rush hour. Whichever route (live or predictive) actually won
    the hybrid comparison has its own already-computed "incident" label
    (e.g. "road closed" — see commute_client._incident_label) appended
    here so the countdown explains itself. Re-fetches the hybrid route
    rather than threading it through _leave_by_for_shift's own return —
    st.cache_data (5 min TTL) makes the underlying calls cache hits, not
    a second round of real network calls, and keeps _leave_by_for_
    shift's existing contract (and its other callers, leave_by_time/
    check()) untouched."""
    current = _current_shift(now)
    if current is None:
        return None
    shift, leave_by = current
    remaining = _remaining_until_leave(now)
    if remaining is None or not (-HEADLINE_GRACE_MINUTES * 60 <= remaining <= HEADLINE_WINDOW_MINUTES * 60):
        return None
    target_ms = int(leave_by.timestamp() * 1000)
    tier = _intensity_tier(remaining)
    is_home = _is_home_event(shift)
    verb = "Starts" if is_home else "Leave"
    text = f"{verb} now" if remaining <= 0 else f"{verb} in {_format_clock(remaining)}"
    if not is_home:
        result = _hybrid_route_for_shift(shift)
        route = result[0] if result else None
        if route and route.get("incident"):
            text += f" — {route['incident']}"
        elif route and route.get("predicted") and is_congested(route):
            # No named incident (see _incident_label — TomTom doesn't
            # always have one), but the predictive call still won on a
            # real delay: a recurring pattern rather than a fresh
            # named event, worth saying differently than a silent
            # number would.
            text += " — predicted delay ahead"
    return target_ms, tier, text, is_home


# Session request: "make it so all the red headlines within the last 2
# hours cycle at the top of the screen with a cool animation when it
# swaps" — headline_rotation.py's own unified rotation needs this same
# (target_ms, tier, text) info but in the normalized shape it shares
# with the other 3 "red headline" sources (storm proximity, the
# weather-statement banner, breaking news), and mapped onto a single
# shared color-tier scale rather than leave-headline's own 5-tier one,
# since the rotation only has 4 shared tiers (see theme.py's own
# .headline-rotation rules) — a plain public wrapper around
# _countdown_info rather than exposing that private helper directly.
_TIER_TO_ROTATION_CLASS = {
    "calm": "rotation-calm",
    "aware": "rotation-notice",
    "urgent": "rotation-warning",
    "critical": "rotation-critical",
    "overdue": "rotation-critical",
}


def leave_headline_candidate(now: datetime) -> dict | None:
    info = _countdown_info(now)
    if info is None:
        return None
    target_ms, tier, text, is_home = info
    verb = "Starts" if is_home else "Leave"
    return {
        "text": text,
        "css_class": _TIER_TO_ROTATION_CLASS[tier],
        "target_ms": target_ms,
        "template": f"{verb} in {{}}",
        "zero_text": f"{verb} now",
    }


def render_ticker_leave_bar(now: datetime) -> None:
    """Compact countdown for the bottom ticker-bar slot (see ticker.py's
    own .ticker-bar) — session report: today's the exact conflict this
    was built for, a golf tee time (leave-in window) landing during a
    Jays game: "can we format it differently so it doesn't take up the
    same space since that space is crucial for the jumbotron... replace
    the bottom scroll bar with a timer... game alerts and breaking news
    is allowed to trump the timer but at least its still there." The
    big red .leave-headline (shown via headline_rotation.py's unified
    rotation now) already skips itself during a jumbotron takeover
    entirely — there's no room for it
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
    target_ms, tier, text, is_home = info
    verb = "Starts" if is_home else "Leave"
    st.markdown(
        f'<div class="jumbo-leave-ticker intensity-{tier}"><span class="live-countdown" data-intensity '
        f'data-target-ms="{target_ms}" data-format="clock" data-template="{verb} in {{}}" '
        f'data-zero-text="{verb} now">{text}</span></div>',
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
    # _leave_text() only ever produces plain internally-generated text
    # ("Leave now", "Leave in 15 min") today, so this was never the live
    # bug — escaped anyway for the same reason news.render_alert_bar's
    # headline now is, to remove the assumption rather than rely on it.
    headline = html.escape(alert.get("headline", ""))
    # data-audio-b64 is the Piper-rendered voice line (kiosk_tts.py,
    # text built by _leave_spoken_text) app.py's kioskPlayLeaveVoice
    # plays directly; data-summary keeps the same text around as the
    # speechSynthesis fallback if synthesis itself ever fails.
    spoken_text = alert.get("summary", "")
    summary_attr = html.escape(spoken_text)
    # Session request, specifically about the (much longer than any
    # normal leave-timer line) morning-brief readout: "it talks a
    # little fast... like it's just trying to get it over with." An
    # explicit flag (app.py sets it only when it swaps in the spoken
    # brief), not a length heuristic on spoken_text itself — keeps this
    # a deliberate choice for that one genuinely long passage rather
    # than something that could quietly flip on for an ordinary leave
    # line that just happens to run a bit long. See kiosk_tts.
    # synthesize_base64's own length_scale comment for why the normal,
    # already-tuned rate stays untouched for every other alert.
    # Skipped entirely (not just muted client-side) when this milestone
    # is in the silent tier (see LEAVE_ALERT_SILENT_ABOVE_MINUTES) —
    # kioskPlayLeaveVoice below never plays it either way, so there's no
    # reason to pay for a real Piper synthesis call on text no one will
    # ever hear.
    is_silent = bool(alert.get("silent"))
    audio_length_scale = 1.2 if alert.get("long_form_audio") else None
    audio_b64 = (
        kiosk_tts.synthesize_base64(spoken_text, length_scale=audio_length_scale) if spoken_text and not is_silent else None
    )
    audio_attr = f' data-audio-b64="{audio_b64}"' if audio_b64 else ""
    # data-volume is the ceiling for THIS shift's leave-by time (see
    # _leave_volume_ceiling) — app.py's kioskPlayLeaveVoice reads it
    # instead of always forcing full volume, so an early-morning shift
    # stays quiet without needing to touch the wall-clock schedule at
    # all.
    volume_attr = f' data-volume="{alert.get("volume", 1.0):.3f}"'
    # data-silent — see LEAVE_ALERT_SILENT_ABOVE_MINUTES. app.py's
    # kioskPlayLeaveVoice checks this before making any sound at all
    # (chime included, not just the spoken line) — the toast/headline/
    # countdown all still show normally either way, this only affects
    # whether it makes noise.
    silent_attr = ' data-silent="true"' if is_silent else ""
    st.markdown(
        f"""<div class="commute-alert-bar" data-summary="{summary_attr}"{audio_attr}{volume_attr}{silent_attr}>
            <span class="news-breaking-label">{label}</span>
            <span class="news-alert-headline">{headline}</span>
        </div>""",
        unsafe_allow_html=True,
    )
