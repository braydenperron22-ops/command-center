"""Today page: a personal day-to-day panel — today's calendar agenda
(merged from one or more published/private ICS feeds, see
calendar_client.py), a commute-time estimate, and a to-do list
persisted to a shared JSON file rather than session state, so an edit
from your laptop shows up on the always-on kiosk — a separate browser
session entirely.
"""

import hashlib
import time
from datetime import datetime, timedelta

import streamlit as st

import calendar_client
import commute_client
import commute_history
import todo_store
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN, MAX_TODO_ITEMS

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


def _row_class(event: dict, now: datetime) -> str:
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
        return "agenda-row-now" if event["start"] <= now_aware else ""
    if event["start"] <= now_aware < event["end"]:
        return "agenda-row-now"
    if event["end"] <= now_aware:
        return "agenda-row-past"
    return ""


def _render_agenda(now: datetime) -> None:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return

    showing_tomorrow = now.hour >= AGENDA_SWITCH_HOUR
    agenda_date = now.date() + timedelta(days=1) if showing_tomorrow else now.date()
    day_word = "tomorrow" if showing_tomorrow else "today"

    st.markdown(f'<div class="tile-label">{day_word.upper()}</div>', unsafe_allow_html=True)

    # Events are always in the future (or, before the switch, still in
    # progress) relative to `now` here on — no special-casing needed for
    # the tomorrow view: _row_class's date comparisons already can't mark
    # a tomorrow event "now" or "past" while `now` is still today.
    events = calendar_client.todays_events(calendars, agenda_date)
    if not events:
        st.markdown(
            f'<div class="tile"><div class="tile-prev">Nothing on the calendar {day_word}.</div></div>',
            unsafe_allow_html=True,
        )
        return

    rows = "".join(
        f"""<div class="news-feed-row {_row_class(e, now)}">
            <div class="news-feed-headline">{e['summary']}{
                f'<div class="news-feed-meta">{e["location"].splitlines()[0]}</div>' if e['location'] else ''
            }</div>
            <div class="news-feed-meta">{_time_range(e)}</div>
        </div>"""
        for e in events
    )
    st.markdown(f'<div class="news-feed-list">{rows}</div>', unsafe_allow_html=True)


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
        f'<div class="severity-caption"><span class="{css_class}">'
        f"{arrow} {abs(delta_minutes)} min in the last {elapsed_minutes} min</span></div>"
    )


def _render_commute() -> None:
    data = commute_client.route()
    if not data:
        return

    minutes = round(data["duration_seconds"] / 60)
    delay_minutes = round(data["delay_seconds"] / 60)
    if delay_minutes >= 1:
        delay_text, delay_class = f"+{delay_minutes} min from traffic", "market-down"
    else:
        delay_text, delay_class = "no delays", "market-up"

    st.markdown(
        f"""<div class="tile">
            <div class="tile-label">{COMMUTE_ORIGIN['label'].upper()} → {COMMUTE_DESTINATION['label'].upper()}</div>
            <div class="tile-value">{minutes} min</div>
            <div class="tile-prev">{data['distance_km']:.1f} km · <span class="{delay_class}">{delay_text}</span></div>
            {_commute_trend_html(data['duration_seconds'])}
        </div>""",
        unsafe_allow_html=True,
    )


def _render_todo() -> None:
    items = todo_store.load()

    with st.form("todo_add_form", clear_on_submit=True):
        new_text = st.text_input(
            "Add a to-do", key="todo_input", label_visibility="collapsed", placeholder="Add a to-do…"
        )
        submitted = st.form_submit_button("Add")
    if submitted and new_text.strip():
        items.append({"text": new_text.strip(), "done": False})
        todo_store.save(items)

    if not items:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Nothing on your list — add something above.</div></div>',
            unsafe_allow_html=True,
        )
        return

    items = items[:MAX_TODO_ITEMS]
    changed = False
    for item in items:
        # Keyed by content hash, not list position — a position-based key
        # would let stale checkbox state from a since-removed item bleed
        # onto whatever item now occupies that slot after the list shifts
        # (e.g. right after "Clear completed").
        key = f"todo_{hashlib.sha1(item['text'].encode()).hexdigest()}"
        checked = st.checkbox(item["text"], value=item["done"], key=key)
        if checked != item["done"]:
            item["done"] = checked
            changed = True
    if changed:
        todo_store.save(items)

    if any(item["done"] for item in items):
        if st.button("Clear completed"):
            todo_store.save([item for item in items if not item["done"]])
            st.rerun()


def render(now: datetime) -> None:
    st.markdown('<div class="page-title page-title-today">Today</div>', unsafe_allow_html=True)
    _render_agenda(now)
    st.markdown('<div style="height: 0.9rem;"></div>', unsafe_allow_html=True)
    _render_commute()
    st.markdown('<div style="height: 0.9rem;"></div>', unsafe_allow_html=True)
    _render_todo()
