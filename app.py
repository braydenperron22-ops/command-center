"""Brayden's Command Center — always-on personal dashboard."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from alerts import render_alert_bar
from config import DASHBOARD_REFRESH_SECONDS, LEAVE_SOON_MINUTES, LOCATION_NAME, SYNC_INTERVAL_MINUTES, TIMEZONE
from data_store import load_state
from icons import icon_for
from scenery import background_css_and_html, condition_category
from theme import inject_theme

st.set_page_config(page_title="Command Center", layout="wide")
st_autorefresh(interval=DASHBOARD_REFRESH_SECONDS * 1000, key="dashboard_refresh")

inject_theme()

state = load_state()
# Hosted deployments (Streamlit Cloud) don't run on Eastern time like the
# local laptop setup did — datetime.now() would silently use the server's
# own timezone instead. Pin explicitly to Toronto, then drop tzinfo so it
# stays comparable with the naive datetimes parsed from state.json below.
now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
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
    if e.get("weather_note"):
        meta += f' · {e["weather_note"]}'
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

st.markdown(
    '<div class="cc-hero">'
    '<div>'
    f'<div class="cc-clock">{now.strftime("%-I:%M")}</div>'
    f'<div class="cc-date">{now.strftime("%A, %B %-d")}</div>'
    f'<div class="cc-synced">{synced_caption} · {LOCATION_NAME}</div>'
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

commute = state.get("commute")
indices = state.get("indices", [])

if commute or indices:
    col_commute, col_indices = st.columns([1, 2], gap="medium")

    with col_commute:
        with st.container(border=True, key="commute_card"):
            st.markdown('<div class="cc-section-label">Commute to North Bay</div>', unsafe_allow_html=True)
            if commute:
                st.markdown(
                    f'<div class="cc-stat-value">{commute["minutes"]} min</div>'
                    f'<div class="cc-stat-sub">{commute["destination"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown('<div class="cc-empty">No commute data yet</div>', unsafe_allow_html=True)

    with col_indices:
        with st.container(border=True, key="indices_card"):
            st.markdown('<div class="cc-section-label">Markets</div>', unsafe_allow_html=True)
            if indices:
                rows = "".join(
                    f'<div class="cc-index-row"><span class="cc-index-name">{i.get("name","")}</span>'
                    f'<span class="cc-index-price">{i.get("price","—")}</span>'
                    f'<span class="cc-index-change {"cc-up" if i.get("change_pct", 0) >= 0 else "cc-down"}">'
                    f'{"+" if i.get("change_pct", 0) >= 0 else ""}{i.get("change_pct", "—")}%</span></div>'
                    for i in indices
                )
                st.markdown(rows, unsafe_allow_html=True)
            else:
                st.markdown('<div class="cc-empty">No market data yet</div>', unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)

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
