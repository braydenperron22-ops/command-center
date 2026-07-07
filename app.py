"""Personal command-center dashboard: ambient rotation across Home (macro
data), Conflicts, News, Markets, and Watchlist — clock/weather header
stays constant."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import news
import pages_conflicts
import pages_home
import pages_markets
import pages_news
import pages_watchlist
import theme
import weather_alerts_bar
from config import MAX_BURST_ALERTS, PAGE_ROTATION_SECONDS, PAGES, TIMEZONE, UV_HIGH_THRESHOLD
from icons import icon_for, label_for
from scenery import FADE_SECONDS, condition_category, phase_for, scene_html, sky_style
import ticker
from weather_client import fetch_weather

st.set_page_config(page_title="Command Center", layout="wide")
theme.inject()

FRED_API_KEY = st.secrets.get("FRED_API_KEY")

# Ticking clock every second; rotation derived from elapsed real time so it
# survives Streamlit Cloud sleep/wake without drifting into a fast-forward.
st_autorefresh(interval=1000, key="clock_tick")

# Hosted deployments (Streamlit Cloud) run on the server's own timezone
# (typically UTC), not North Bay's — pin explicitly rather than trusting
# datetime.now(), then drop tzinfo so it stays comparable with the naive
# sunrise/sunset values Open-Meteo returns for the same zone.
now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)

try:
    weather = fetch_weather()
except Exception:
    weather = None

if weather:
    phase = phase_for(now, weather["sunrise"], weather["sunset"])
    category = condition_category(weather["weather_code"])
else:
    phase = "day" if 6 <= now.hour < 20 else "night"
    category = "cloudy"

# Background/scenery rendering never touches the network (weather is
# already fetched above), but this whole block still runs before any page
# content — wrapped so a bug here can't blank the entire dashboard, only
# lose the decorative background for that one render.
try:
    # The sky fade is computed here (not left to a CSS transition, which
    # can't survive this app's 1-second autorefresh — confirmed it snaps
    # instantly rather than animating, the same class of bug as the
    # country-fade one). Track when the phase last changed and blend
    # server-side by elapsed time.
    if phase != st.session_state.get("bg_phase"):
        st.session_state["bg_fade_from"] = st.session_state.get("bg_phase", phase)
        st.session_state["bg_phase_changed_at"] = time.time()
        st.session_state["bg_phase"] = phase

    bg_fade_from = st.session_state.get("bg_fade_from", phase)
    bg_blend = min((time.time() - st.session_state.get("bg_phase_changed_at", 0)) / FADE_SECONDS, 1.0)

    st.markdown(
        sky_style(weather["weather_code"] if weather else 0, phase, bg_fade_from, bg_blend),
        unsafe_allow_html=True,
    )
    st.markdown(
        scene_html(weather["weather_code"] if weather else 0, phase),
        unsafe_allow_html=True,
    )

    # Dim the whole UI at night — not just the background, since bright
    # white tile text/badges in a pitch-black room is still harsh even
    # with a black sky behind them. Ramps with the same fade progress
    # already tracked above rather than snapping dim on/off at the phase
    # boundary.
    if phase == "night" and bg_fade_from == "night":
        night_dim = 1.0
    elif phase == "night":
        night_dim = bg_blend
    elif bg_fade_from == "night":
        night_dim = 1.0 - bg_blend
    else:
        night_dim = 0.0

    if night_dim > 0:
        # This runs 24/7 in a bedroom — night needs to be genuinely dim
        # enough to sleep next to, not just "a bit darker."
        brightness = 1 - night_dim * 0.82
        st.markdown(
            f'<style>[data-testid="stMain"] {{ filter: brightness({brightness:.3f}); }}</style>',
            unsafe_allow_html=True,
        )
except Exception:
    pass

# Fetched once per rerun and reused below both to update/render the
# persistent top banner and to feed the bottom rotating alert bar —
# get_new_alerts() marks headlines as seen as a side effect, so it must
# only be called once per script run. Wrapped since a bug in either the
# top-alert or weather-statement logic shouldn't stop the clock/hero row
# and every page below it from rendering.
new_alerts = []
try:
    new_alerts = news.get_new_alerts()
    news.update_top_alert(new_alerts)
    news.render_top_alert_bar()
except Exception:
    pass

try:
    weather_alerts_bar.render(weather)
except Exception:
    pass

weather_block = ""
if weather:
    icon_svg = icon_for(category, phase)
    condition_label = label_for(weather["weather_code"])

    hilo_html = ""
    high, low = weather.get("forecast_high_c"), weather.get("forecast_low_c")
    if high is not None and low is not None:
        hilo_html = f' · <span class="weather-hilo">H:{high:.0f}° L:{low:.0f}°</span>'

    extras = []
    if weather["rain_in_hours"] is not None:
        h = weather["rain_in_hours"]
        label = f"{int(h * 60)}m" if h < 1 else f"{h:.0f}h"
        extras.append(f'<span class="weather-extra weather-rain">Rain in {label}</span>')
    if weather["uv_index"] is not None and weather["uv_index"] > UV_HIGH_THRESHOLD:
        extras.append(f'<span class="weather-extra weather-uv">UV {weather["uv_index"]:.0f}</span>')
    extras_html = f'<div class="weather-extras">{"".join(extras)}</div>' if extras else ""

    weather_block = f"""<div class="hero-weather">
        <div class="clock weather-condition"><span class="weather-icon">{icon_svg}</span>{weather['temp_c']:.0f}°C</div>
        <div class="weather-condition-label">{condition_label}</div>
        <div class="date-sub">North Bay{hilo_html}</div>{extras_html}
    </div>"""

st.markdown(
    f"""<div class="hero-row">
        <div class="hero-time">
            <div class="clock">{now.strftime('%I:%M %p').lstrip('0')}</div>
            <div class="date-sub">{now.strftime('%A, %B %d')}</div>
        </div>{weather_block}
    </div>""",
    unsafe_allow_html=True,
)

def _safe_render(render_fn, *args) -> None:
    """Runs a page's render function, catching anything unexpected rather
    than letting it crash the whole script. The individual data clients
    already fall back to last-known-good values on network errors, but
    this is the last line of defense for a genuine bug — a bad page
    should never blank the entire dashboard (clock, weather, ticker all
    keep working) when it runs unattended 24/7.
    """
    try:
        render_fn(*args)
    except Exception:
        st.markdown(
            '<div class="tile"><div class="tile-prev">'
            "This page hit an unexpected error and will retry automatically."
            "</div></div>",
            unsafe_allow_html=True,
        )


# The release-calendar ticker at the bottom is global (useful regardless of
# which page is showing), so macro readings are fetched unconditionally.
readings, new_flags = ({}, {})
if FRED_API_KEY:
    try:
        readings, new_flags = pages_home.fetch_readings(FRED_API_KEY)
    except Exception:
        pass

page_index = int(time.time() // PAGE_ROTATION_SECONDS) % len(PAGES)
page = PAGES[page_index]

with st.container(key="page_body"):
    if page == "home":
        if not FRED_API_KEY:
            st.error("FRED_API_KEY is not set in Streamlit secrets.")
        else:
            _safe_render(pages_home.render, FRED_API_KEY, readings, new_flags)
    elif page == "conflicts":
        _safe_render(pages_conflicts.render)
    elif page == "news":
        _safe_render(pages_news.render)
    elif page == "markets":
        _safe_render(pages_markets.render)
    elif page == "watchlist":
        _safe_render(pages_watchlist.render)

# News alerts: strictly-filtered items queue up and take over the bottom
# bar (normally the release calendar) for TOAST_SECONDS each, breaking-news
# style, before control returns to the calendar ticker. This happens
# regardless of which page is active.
#
# A feed outage that recovers can surface dozens of headlines in one
# batch (everything that was never marked "seen" while it was down) —
# capped to the most recent MAX_BURST_ALERTS so that doesn't turn into
# hours of backlog playing through this bar one at a time.
try:
    news_queue = st.session_state.setdefault("news_queue", [])
    if len(new_alerts) > MAX_BURST_ALERTS:
        new_alerts = new_alerts[-MAX_BURST_ALERTS:]
    news_queue.extend(new_alerts)

    now_ts = time.time()
    current_alert, elapsed = None, None
    if news_queue:
        current_alert = news_queue[0]
        if "shown_at" not in current_alert:
            current_alert["shown_at"] = now_ts
        elapsed = now_ts - current_alert["shown_at"]
        if elapsed > news.TOAST_SECONDS:
            news_queue.pop(0)
            current_alert, elapsed = None, None

    if current_alert:
        news.render_alert_bar(current_alert, elapsed)
    elif FRED_API_KEY and readings:
        schedule = ticker.build_schedule(readings, FRED_API_KEY)
        st.markdown(ticker.render_html(schedule, now), unsafe_allow_html=True)
except Exception:
    pass
