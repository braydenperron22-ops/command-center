"""Today page: a personal day-to-day panel — today's calendar agenda
(merged from one or more published/private ICS feeds, see
calendar_client.py) and a commute-time estimate. Everything here is
pulled from live sources rather than hand-maintained, on purpose —
nothing on this page needs manual upkeep to stay useful.
"""

import time
from datetime import datetime, timedelta

import streamlit as st

import calendar_client
import commute_client
import commute_history
import commute_reminder
import fuel_price_client
import local_news_client
import waste_schedule
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN

# From this hour onward, the agenda switches from today's remaining
# events to tomorrow's full day — checking the dashboard in the evening
# is more useful as "what does tomorrow look like" than "what's left
# today" (usually nothing, by 7pm).
AGENDA_SWITCH_HOUR = 19

# How far back the commute trend looks, and how big a change has to be
# before it's worth surfacing rather than just noise — TomTom's own
# estimate jitters by a minute or two between calls even with nothing
# really changing.
COMMUTE_TREND_LOOKBACK_SECONDS = 30 * 60
COMMUTE_TREND_MIN_DELTA_MINUTES = 3


def _time_range(event: dict) -> str:
    if event["all_day"]:
        return "All day"
    start_text = event["start"].strftime("%I:%M %p").lstrip("0")
    if not event["show_end_time"]:
        return start_text
    return f"{start_text} – {event['end'].strftime('%I:%M %p').lstrip('0')}"


def _row_class(event: dict, now: datetime, is_next: bool) -> str:
    if event["all_day"]:
        return ""
    # `now` arrives naive but already IN the local zone (app.py pins it
    # to TIMEZONE and strips tzinfo) — .replace() to reinterpret it as
    # that same zone, not .astimezone(), which would instead assume
    # `now` is in the *system's* zone and convert from there. Streamlit
    # Cloud runs in UTC, so that would silently compare against the
    # wrong wall-clock time.
    now_aware = now.replace(tzinfo=event["start"].tzinfo)
    if not event["show_end_time"]:
        # The end time isn't trustworthy for these (see calendar_client's
        # show_end_time), so it can't be used to decide "past" either —
        # a shift still actually in progress would otherwise fade out
        # the moment its bogus 1-hour placeholder end passes. Just
        # reflect whether it's started.
        if event["start"] <= now_aware:
            return "agenda-row-now"
        return "agenda-row-next" if is_next else ""
    if event["start"] <= now_aware < event["end"]:
        return "agenda-row-now"
    if event["end"] <= now_aware:
        return "agenda-row-past"
    return "agenda-row-next" if is_next else ""


def _next_event_id(events: list[dict], now: datetime) -> int | None:
    """id() of the earliest not-yet-started, non-all-day event — the one
    _render_agenda highlights as "up next", distinct from one already
    underway ("now") or further out in the list. Safe to compare by
    id() here since `events` is freshly built this render — nothing
    persists across reruns."""
    for e in events:
        if e["all_day"]:
            continue
        now_aware = now.replace(tzinfo=e["start"].tzinfo)
        if e["start"] > now_aware:
            return id(e)
    return None


def _render_agenda(now: datetime) -> None:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return

    showing_tomorrow = now.hour >= AGENDA_SWITCH_HOUR
    agenda_date = now.date() + timedelta(days=1) if showing_tomorrow else now.date()
    day_word = "tomorrow" if showing_tomorrow else "today"

    st.markdown(f'<div class="tile-label compact">{day_word.upper()}</div>', unsafe_allow_html=True)

    # Events are always in the future (or, before the switch, still in
    # progress) relative to `now` here on — no special-casing needed for
    # the tomorrow view: _row_class's date comparisons already can't mark
    # a tomorrow event "now" or "past" while `now` is still today.
    events = calendar_client.todays_events(calendars, agenda_date)
    if not events:
        st.markdown(
            f'<div class="tile compact"><div class="tile-prev">Nothing on the calendar {day_word}.</div></div>',
            unsafe_allow_html=True,
        )
        return

    next_id = _next_event_id(events, now)
    rows = "".join(
        f"""<div class="news-feed-row {_row_class(e, now, id(e) == next_id)}">
            <div class="news-feed-headline">{e['summary']}{
                # Venue name only, not the full street address — the
                # commute tile below already shows the same place this
                # way, and the full address wrapping to 2-3 lines here
                # (see commute_reminder._destination_for_shift for the
                # matching truncation) was a big chunk of why this page
                # was overrunning when the global banners stack up top.
                f'<div class="news-feed-meta">{e["location"].splitlines()[0].split(",")[0].strip()}</div>'
                if e['location'] else ''
            }</div>
            <div class="news-feed-meta">{_time_range(e)}</div>
        </div>"""
        for e in events
    )
    # agenda-feed-list scopes the bigger type up ahead in theme.py to
    # just this page — the News page reuses these same news-feed-*
    # classes at their normal size for its much longer list.
    st.markdown(f'<div class="news-feed-list agenda-feed-list">{rows}</div>', unsafe_allow_html=True)


def _commute_trend_html(current_duration_seconds: float) -> str:
    """A line like "↑ 4 min in the last 32 min" — "" if there's no
    comparison data yet (e.g. right after a fresh deploy) or the change
    is too small to be worth showing."""
    comparison = commute_history.reading_from_before(COMMUTE_TREND_LOOKBACK_SECONDS)
    if not comparison:
        return ""

    delta_minutes = round((current_duration_seconds - comparison["duration_seconds"]) / 60)
    if abs(delta_minutes) < COMMUTE_TREND_MIN_DELTA_MINUTES:
        return ""

    elapsed_minutes = round((time.time() - comparison["timestamp"]) / 60)
    arrow, css_class = ("↑", "market-down") if delta_minutes > 0 else ("↓", "market-up")
    return (
        f'<div class="severity-caption compact"><span class="{css_class}">'
        f"{arrow} {abs(delta_minutes)} min in the last {elapsed_minutes} min</span></div>"
    )


def _render_commute(now: datetime) -> None:
    # Same destination resolution the leave headline uses (see
    # commute_reminder.todays_destination) — today's shift's own
    # calendar location if it has one, else the default commute. Keeps
    # this tile and the headline always pointed at the same place
    # rather than the tile silently still assuming Work.
    destination = commute_reminder.todays_destination(now)
    using_default = destination is COMMUTE_DESTINATION
    data = commute_client.route(None if using_default else destination)
    if not data:
        return

    minutes = round(data["duration_seconds"] / 60)
    delay_minutes = round(data["delay_seconds"] / 60)
    if delay_minutes >= 1:
        # "why", not just "how much" — TomTom's traffic sections say
        # what's actually causing the delay (accident, road work, ...)
        # when it has that detail, not just the aggregate minutes.
        reason = f" ({data['incident']})" if data.get("incident") else ""
        delay_text, delay_class = f"+{delay_minutes} min from traffic{reason}", "market-down"
    else:
        delay_text, delay_class = "no delays", "market-up"

    # Trend is only meaningful against the default route's own history
    # — comparing today's drive to a one-off shift location against the
    # usual commute's history would be comparing two different routes.
    trend_html = _commute_trend_html(data["duration_seconds"]) if using_default else ""
    # trend_html folded onto the closing tag's line rather than given its
    # own — when it's "" (no comparison data yet), a lone whitespace line
    # ahead of an indented "</div>" reads to the markdown parser as a
    # blank line followed by an indented code block, and it renders that
    # closing tag as literal text instead of parsing it as HTML.
    st.markdown(
        f"""<div class="tile compact">
            <div class="tile-label compact">{COMMUTE_ORIGIN['label'].upper()} → {destination['label'].upper()}</div>
            <div class="tile-value">{minutes} min</div>
            <div class="tile-prev">{data['distance_km']:.1f} km · <span class="{delay_class}">{delay_text}</span></div>
            {trend_html}</div>""",
        unsafe_allow_html=True,
    )


def _render_fuel_price(now: datetime) -> None:
    """North Bay gas price vs. its own recent trend (see
    fuel_price_client.eco_mode_status) — built specifically to answer
    "should I bother driving in eco mode today," not just to display a
    number. Silent if the feed hasn't returned anything yet rather than
    an empty tile."""
    status = fuel_price_client.eco_mode_status()
    if not status:
        return
    if status["eco_recommended"]:
        badge_class, badge_text = "badge-bad", "Eco mode recommended"
    else:
        badge_class, badge_text = "badge-good", "Eco mode not needed"
    as_of = f"{status['as_of'].strftime('%b')} {status['as_of'].day}"
    # Day-granularity only, not a specific time — the survey publishes
    # "before end of business" on its update day, not at a fixed hour,
    # so anything more precise than "today" would be a made-up promise.
    days_until_update = (status["next_update"] - now.date()).days
    update_text = "updates today" if days_until_update <= 0 else f"next update in {days_until_update}d"
    st.markdown(
        f"""<div class="tile compact">
            <div class="tile-label compact">NORTH BAY GAS</div>
            <div class="tile-value">{status['price']:.1f}¢/L</div>
            <div class="tile-prev">vs {status['baseline']:.1f}¢ 12wk avg · as of {as_of} · {update_text}</div>
            <div class="badge {badge_class}">{badge_text}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _render_garbage(now: datetime) -> None:
    """Next bin day — garbage every Monday, recycling the 2nd/4th
    Wednesday of the month (see waste_schedule.py). No API here: this
    is a fixed schedule, and the person who gave it to me said
    "typically", so a stat holiday shifting a real pickup by a day
    isn't accounted for."""
    pickup = waste_schedule.next_pickup(now.date())
    if pickup["days_until"] == 0:
        when = "Today"
    elif pickup["days_until"] == 1:
        when = "Tomorrow"
    else:
        when = f"{pickup['date'].strftime('%a %b')} {pickup['date'].day}"
    badge_class = "badge-bad" if pickup["days_until"] == 0 else "badge-good"
    st.markdown(
        f"""<div class="tile compact">
            <div class="tile-label compact">{pickup['kind'].upper()} DAY</div>
            <div class="tile-value">{when}</div>
            <div class="badge {badge_class}">{pickup['kind']}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _relative_time(seconds_ago: float) -> str:
    minutes = int(seconds_ago / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


NEARBY_ROTATION_SECONDS = 10


def _render_local_news() -> None:
    """Real, nearby stuff only — police/OPP incident beats and
    road-closure/construction items (see local_news_client), not
    general local news. One headline at a time, rotating — same
    time-based pattern pages_home.py uses for its country rotation
    (int(time.time() // interval) % n, so it's driven by wall-clock
    time and needs nothing stored in session state). 10s rather than
    something longer: Today only gets one slot in the page rotation every
    PAGE_ROTATION_SECONDS * len(PAGES), and a slow interval would mean rarely seeing more
    than one of these per visit. Silent if nothing currently qualifies
    rather than an empty-state tile — a quiet day locally isn't worth
    taking up space to announce."""
    items = local_news_client.fetch_items()
    if not items:
        return
    now_ts = time.time()
    index = int(now_ts // NEARBY_ROTATION_SECONDS) % len(items)
    item = items[index]
    st.markdown(f'<div class="tile-label compact">NEARBY · {index + 1}/{len(items)}</div>', unsafe_allow_html=True)
    meta = item["source"]
    if item["published"]:
        meta += f' · {_relative_time(now_ts - item["published"].timestamp())}'
    row = f"""<div class="news-feed-row news-cat-local compact">
        <div class="news-feed-headline">{item['headline']}</div>
        <div class="news-feed-meta">{meta}</div>
    </div>"""
    # Normal news-feed-list sizing, not agenda-feed-list — that scoping
    # is tuned for the agenda's 1-3 short calendar-event titles, and
    # blows real headline-length text up to one word per line.
    st.markdown(f'<div class="news-feed-list">{row}</div>', unsafe_allow_html=True)


def render(now: datetime) -> None:
    st.markdown('<div class="page-title page-title-today">Today</div>', unsafe_allow_html=True)
    _render_agenda(now)
    st.markdown('<div style="height: 0.25rem;"></div>', unsafe_allow_html=True)
    _render_commute(now)
    st.markdown('<div style="height: 0.25rem;"></div>', unsafe_allow_html=True)
    _render_fuel_price(now)
    st.markdown('<div style="height: 0.25rem;"></div>', unsafe_allow_html=True)
    _render_garbage(now)
    st.markdown('<div style="height: 0.25rem;"></div>', unsafe_allow_html=True)
    _render_local_news()
