"""Brayden's Command Center — always-on personal dashboard."""
from datetime import datetime, timedelta

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from alerts import render_alert_bar
from config import (
    DASHBOARD_REFRESH_SECONDS,
    LEAVE_SOON_MINUTES,
    LOCATION_NAME,
    ROTATION_CYCLE_SECONDS,
    ROTATION_EXTRAS_SECONDS,
    SYNC_INTERVAL_MINUTES,
)
from data_store import add_task, delete_task, load_state, load_tasks, toggle_task
from icons import icon_for
from scenery import background_css_and_html, condition_category
from theme import inject_theme

st.set_page_config(page_title="Command Center", layout="wide")
st_autorefresh(interval=DASHBOARD_REFRESH_SECONDS * 1000, key="dashboard_refresh")

inject_theme()

state = load_state()
now = datetime.now()
weather = state.get("weather") or {}


def _event_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).date()
    except ValueError:
        return None


def _upcoming_label(d) -> str:
    today = now.date()
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return d.strftime("%a, %b %-d")


def _row_html(e: dict, meta_prefix: str = "") -> str:
    meta = f"{meta_prefix}{e.get('time','')}"
    if e.get("leave_by"):
        meta += f' · leave by {e["leave_by"]}'
    return (
        f'<div class="cc-row"><span class="cc-row-title">{e.get("title","")}</span>'
        f'<span class="cc-row-meta">{meta}</span></div>'
    )


def _parse_leave_by(event: dict):
    date_str, leave_by = event.get("date"), event.get("leave_by")
    if not date_str or not leave_by:
        return None
    d = _event_date(date_str)
    if not d:
        return None
    try:
        parsed = datetime.strptime(leave_by.strip(), "%I:%M %p")
    except ValueError:
        return None
    return datetime.combine(d, parsed.time())


st.markdown(
    background_css_and_html(weather.get("code", 0), weather.get("is_day", True)),
    unsafe_allow_html=True,
)

last_synced = state.get("last_synced")
synced_caption = "Waiting on first sync…"
if last_synced:
    synced_dt = datetime.fromisoformat(last_synced)
    stale_minutes = (now - synced_dt.replace(tzinfo=None)).total_seconds() / 60
    if stale_minutes > SYNC_INTERVAL_MINUTES * 2:
        synced_caption = f"Sync stalled — last update {int(stale_minutes)} min ago"
    else:
        synced_caption = f"Synced {synced_dt.strftime('%-I:%M %p')}"

if weather:
    category = condition_category(weather.get("code", 0))
    icon_svg = icon_for(category, weather.get("is_day", True))
    precip_note = f'<div class="cc-weather-range">{weather["precip_soon"]}</div>' if weather.get("precip_soon") else ""
    weather_html = (
        '<div class="cc-weather-inline">'
        f'<div class="cc-weather-icon">{icon_svg}</div>'
        '<div>'
        f'<div class="cc-weather-temp">{weather.get("temp_now", "—")}°</div>'
        f'<div class="cc-weather-meta">{weather.get("condition_now", "")}</div>'
        f'<div class="cc-weather-range">H {weather.get("temp_high", "—")}° · L {weather.get("temp_low", "—")}°</div>'
        f'{precip_note}'
        '</div>'
        '</div>'
    )
else:
    weather_html = '<div class="cc-empty">No weather yet</div>'

commute = state.get("commute")
commute_str = f" · {commute['minutes']} min to {commute['destination']}" if commute else ""

st.markdown(
    '<div class="cc-hero">'
    '<div>'
    f'<div class="cc-clock">{now.strftime("%-I:%M")}</div>'
    f'<div class="cc-date">{now.strftime("%A, %B %-d")}</div>'
    f'<div class="cc-synced">{synced_caption} · {LOCATION_NAME}{commute_str}</div>'
    '</div>'
    f'{weather_html}'
    '</div>',
    unsafe_allow_html=True,
)

render_alert_bar(state.get("alerts", []))

# "Leave now" — surfaces the nearest event whose leave_by time is imminent.
all_events = state.get("calendar_events", [])
leave_candidates = []
for e in all_events:
    leave_dt = _parse_leave_by(e)
    if leave_dt:
        minutes_until = (leave_dt - now).total_seconds() / 60
        if -20 <= minutes_until <= LEAVE_SOON_MINUTES:
            leave_candidates.append((minutes_until, e))

if leave_candidates:
    minutes_until, event = min(leave_candidates, key=lambda x: x[0])
    if minutes_until <= 0:
        urgency, label = "red", "Leave now"
    elif minutes_until <= 5:
        urgency, label = "red", f"Leave in {int(minutes_until)} min"
    else:
        urgency, label = "yellow", f"Leave in {int(minutes_until)} min"
    render_alert_bar([{"severity": urgency, "message": f"{label} — {event.get('title','')}"}])

st.markdown("<hr/>", unsafe_allow_html=True)

# Rotate the content column between the main agenda/inbox/tasks view and a
# lighter-weight "extras" view (3-day outlook, deliveries) so the primary
# screen never gets crowded with secondary information.
cycle_position = int(now.timestamp()) % ROTATION_CYCLE_SECONDS
showing_extras = cycle_position >= (ROTATION_CYCLE_SECONDS - ROTATION_EXTRAS_SECONDS)

if not showing_extras:
    col_agenda, col_email = st.columns(2, gap="medium")

    with col_agenda:
        with st.container(border=True, key="agenda_card"):
            st.markdown('<div class="cc-section-label">Today</div>', unsafe_allow_html=True)
            events = state.get("calendar_events", [])
            today_events = [e for e in events if _event_date(e.get("date")) == now.date()]
            upcoming_events = sorted(
                (e for e in events if (d := _event_date(e.get("date"))) and d > now.date()),
                key=lambda e: (e.get("date"), e.get("time") or ""),
            )

            if today_events:
                st.markdown("".join(_row_html(e) for e in today_events), unsafe_allow_html=True)
            else:
                st.markdown('<div class="cc-empty">Nothing today</div>', unsafe_allow_html=True)

            if upcoming_events:
                upcoming_rows = "".join(
                    _row_html(e, meta_prefix=f"{_upcoming_label(_event_date(e['date']))} · ")
                    for e in upcoming_events
                )
                st.markdown(
                    f'<div class="cc-upcoming"><div class="cc-upcoming-label">Upcoming</div>{upcoming_rows}</div>',
                    unsafe_allow_html=True,
                )

    with col_email:
        with st.container(border=True, key="email_card"):
            st.markdown('<div class="cc-section-label">Needs a look</div>', unsafe_allow_html=True)
            emails = state.get("email_highlights", [])
            if emails:
                rows = "".join(
                    f'<div class="cc-row"><span class="cc-row-title">{e.get("subject","")}</span>'
                    f'<span class="cc-row-meta">{e.get("from","")}</span></div>'
                    for e in emails
                )
                st.markdown(rows, unsafe_allow_html=True)
            else:
                st.markdown('<div class="cc-empty">Inbox is clear</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    with st.container(border=True, key="tasks_card"):
        st.markdown('<div class="cc-section-label">Tasks & Reminders</div>', unsafe_allow_html=True)

        with st.form("add_task_form", clear_on_submit=True):
            t_col1, t_col2, t_col3 = st.columns([3, 1, 1])
            text = t_col1.text_input("New task", label_visibility="collapsed", placeholder="Add a task or reminder…")
            due = t_col2.date_input("Due (optional)", value=None, label_visibility="collapsed")
            submitted = t_col3.form_submit_button("Add")
            if submitted and text.strip():
                add_task(text.strip(), due.isoformat() if due else None)
                st.rerun()

        tasks = load_tasks()
        open_tasks = [t for t in tasks if not t["done"]]
        done_tasks = [t for t in tasks if t["done"]]

        if not open_tasks:
            st.markdown('<div class="cc-empty">Nothing pending</div>', unsafe_allow_html=True)

        for t in sorted(open_tasks, key=lambda x: x.get("due") or "9999"):
            c1, c2, c3 = st.columns([0.5, 4, 0.5])
            checked = c1.checkbox("", value=False, key=f"chk_{t['id']}", label_visibility="collapsed")
            due_str = f" · due {t['due']}" if t.get("due") else ""
            c2.markdown(f'<div class="cc-row-title" style="padding:6px 0;">{t["text"]}{due_str}</div>', unsafe_allow_html=True)
            if c3.button("✕", key=f"del_{t['id']}"):
                delete_task(t["id"])
                st.rerun()
            if checked:
                toggle_task(t["id"])
                st.rerun()

        if done_tasks:
            with st.expander(f"Completed ({len(done_tasks)})"):
                for t in done_tasks:
                    c1, c2 = st.columns([4, 0.5])
                    c1.write(f"~~{t['text']}~~")
                    if c2.button("Undo", key=f"undo_{t['id']}"):
                        toggle_task(t["id"])
                        st.rerun()
else:
    col_outlook, col_deliveries = st.columns(2, gap="medium")

    with col_outlook:
        with st.container(border=True, key="outlook_card"):
            st.markdown('<div class="cc-section-label">3-Day Outlook</div>', unsafe_allow_html=True)
            outlook = state.get("outlook", [])
            if outlook:
                rows = "".join(
                    f'<div class="cc-row"><span class="cc-row-title">{d.get("day","")}</span>'
                    f'<span class="cc-row-meta">{d.get("condition","")} · H {d.get("high","—")}° · L {d.get("low","—")}°</span></div>'
                    for d in outlook
                )
                st.markdown(rows, unsafe_allow_html=True)
            else:
                st.markdown('<div class="cc-empty">No forecast yet</div>', unsafe_allow_html=True)

    with col_deliveries:
        with st.container(border=True, key="deliveries_card"):
            st.markdown('<div class="cc-section-label">Deliveries</div>', unsafe_allow_html=True)
            deliveries = state.get("deliveries", [])
            if deliveries:
                rows = "".join(
                    f'<div class="cc-row"><span class="cc-row-title">{d.get("label","")}</span>'
                    f'<span class="cc-row-meta">{d.get("eta","")}</span></div>'
                    for d in deliveries
                )
                st.markdown(rows, unsafe_allow_html=True)
            else:
                st.markdown('<div class="cc-empty">Nothing in transit</div>', unsafe_allow_html=True)
