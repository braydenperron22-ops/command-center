"""Brayden's Command Center — always-on personal dashboard."""
from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from alerts import render_alert_bar
from config import DASHBOARD_REFRESH_SECONDS, LOCATION_NAME, SYNC_INTERVAL_MINUTES
from data_store import add_task, delete_task, load_state, load_tasks, toggle_task
from scenery import background_css_and_html

st.set_page_config(page_title="Command Center", layout="wide")
st_autorefresh(interval=DASHBOARD_REFRESH_SECONDS * 1000, key="dashboard_refresh")

state = load_state()
now = datetime.now()

weather = state.get("weather") or {}
st.markdown(
    background_css_and_html(weather.get("code", 0), weather.get("is_day", True)),
    unsafe_allow_html=True,
)

render_alert_bar(state.get("alerts", []))

st.title("Brayden's Command Center")
st.caption(now.strftime("%A, %B %d, %Y — %I:%M %p"))

last_synced = state.get("last_synced")
if last_synced:
    synced_dt = datetime.fromisoformat(last_synced)
    stale_minutes = (now - synced_dt.replace(tzinfo=None)).total_seconds() / 60
    if stale_minutes > SYNC_INTERVAL_MINUTES * 2:
        st.warning(f"Data last synced {int(stale_minutes)} min ago — sync may be stalled.")
    else:
        st.caption(f"Last synced: {synced_dt.strftime('%I:%M %p')}")
else:
    st.info("No sync data yet — waiting on the first scheduled sync to run.")

st.divider()

col_weather, col_agenda, col_email = st.columns([1, 1.5, 1.5])

with col_weather:
    with st.container(border=True, key="weather_card"):
        st.subheader(f"Weather — {LOCATION_NAME}")
        if weather:
            st.metric("Now", f"{weather.get('temp_now', '—')}°C", weather.get("condition_now", ""))
            st.write(f"High {weather.get('temp_high', '—')}°C / Low {weather.get('temp_low', '—')}°C")
        else:
            st.write("No weather data yet.")

with col_agenda:
    with st.container(border=True, key="agenda_card"):
        st.subheader("Today's Agenda")
        events = state.get("calendar_events", [])
        if events:
            for e in events:
                st.markdown(f"**{e.get('time', '')}** — {e.get('title', '')}")
        else:
            st.write("Nothing on the calendar.")

with col_email:
    with st.container(border=True, key="email_card"):
        st.subheader("Email Highlights")
        emails = state.get("email_highlights", [])
        if emails:
            for e in emails:
                st.markdown(f"**{e.get('from', '')}** — {e.get('subject', '')}")
        else:
            st.write("No flagged emails.")

st.divider()

with st.container(border=True, key="tasks_card"):
    st.subheader("Tasks & Reminders")

    with st.form("add_task_form", clear_on_submit=True):
        t_col1, t_col2, t_col3 = st.columns([3, 1, 1])
        text = t_col1.text_input("New task", label_visibility="collapsed", placeholder="Add a task or reminder...")
        due = t_col2.date_input("Due (optional)", value=None, label_visibility="collapsed")
        submitted = t_col3.form_submit_button("Add")
        if submitted and text.strip():
            add_task(text.strip(), due.isoformat() if due else None)
            st.rerun()

    tasks = load_tasks()
    open_tasks = [t for t in tasks if not t["done"]]
    done_tasks = [t for t in tasks if t["done"]]

    for t in sorted(open_tasks, key=lambda x: x.get("due") or "9999"):
        c1, c2, c3 = st.columns([0.5, 4, 0.5])
        checked = c1.checkbox("", value=False, key=f"chk_{t['id']}")
        due_str = f" (due {t['due']})" if t.get("due") else ""
        c2.write(f"{t['text']}{due_str}")
        if c3.button("🗑", key=f"del_{t['id']}"):
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
