"""Today page: a personal day-to-day panel — today's calendar agenda
(from a published, read-only iCloud ICS feed), a commute-time estimate,
and a to-do list persisted to a shared JSON file rather than session
state, so an edit from your laptop shows up on the always-on kiosk — a
separate browser session entirely.
"""

import hashlib
from datetime import datetime

import streamlit as st

import calendar_client
import commute_client
import todo_store
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN, MAX_TODO_ITEMS


def _time_range(event: dict) -> str:
    if event["all_day"]:
        return "All day"
    return f"{event['start'].strftime('%I:%M %p').lstrip('0')} – {event['end'].strftime('%I:%M %p').lstrip('0')}"


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
    if event["start"] <= now_aware < event["end"]:
        return "agenda-row-now"
    if event["end"] <= now_aware:
        return "agenda-row-past"
    return ""


def _render_agenda(now: datetime) -> None:
    ics_url = st.secrets.get("CALENDAR_ICS_URL")
    if not ics_url:
        return

    events = calendar_client.todays_events(ics_url, now.date())
    if not events:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Nothing on the calendar today.</div></div>',
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
