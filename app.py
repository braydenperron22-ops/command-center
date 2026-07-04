"""Brayden's Command Center — always-on personal dashboard."""
from datetime import datetime, timedelta

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from alerts import render_alert_bar
from config import DASHBOARD_REFRESH_SECONDS, LOCATION_NAME, SYNC_INTERVAL_MINUTES
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
    weather_html = f"""
    <div class="cc-weather-inline">
        <div class="cc-weather-icon">{icon_svg}</div>
        <div>
            <div class="cc-weather-temp">{weather.get('temp_now', '—')}°</div>
            <div class="cc-weather-meta">{weather.get('condition_now', '')}</div>
            <div class="cc-weather-range">H {weather.get('temp_high', '—')}° · L {weather.get('temp_low', '—')}°</div>
        </div>
    </div>
    """
else:
    weather_html = '<div class="cc-empty">No weather yet</div>'

commute = state.get("commute")
commute_str = f" · {commute['minutes']} min to {commute['destination']}" if commute else ""

st.markdown(
    f"""
    <div class="cc-hero">
        <div>
            <div class="cc-clock">{now.strftime('%-I:%M')}</div>
            <div class="cc-date">{now.strftime('%A, %B %-d')}</div>
            <div class="cc-synced">{synced_caption} · {LOCATION_NAME}{commute_str}</div>
        </div>
        {weather_html}
    </div>
    """,
    unsafe_allow_html=True,
)

render_alert_bar(state.get("alerts", []))

st.markdown("<hr/>", unsafe_allow_html=True)

col_agenda, col_email = st.columns(2, gap="medium")

def _day_label(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        d = datetime.fromisoformat(date_str).date()
    except ValueError:
        return ""
    today = now.date()
    if d == today:
        return ""
    if d == today + timedelta(days=1):
        return "Tomorrow · "
    return d.strftime("%a %b %-d · ")


with col_agenda:
    with st.container(border=True, key="agenda_card"):
        st.markdown('<div class="cc-section-label">Agenda</div>', unsafe_allow_html=True)
        events = state.get("calendar_events", [])
        if events:
            rows = "".join(
                f'<div class="cc-row"><span class="cc-row-title">{e.get("title","")}</span>'
                f'<span class="cc-row-meta">{_day_label(e.get("date"))}{e.get("time","")}'
                + (f' · leave by {e["leave_by"]}' if e.get("leave_by") else '')
                + '</span></div>'
                for e in events
            )
            st.markdown(rows, unsafe_allow_html=True)
        else:
            st.markdown('<div class="cc-empty">Nothing on the calendar</div>', unsafe_allow_html=True)

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
