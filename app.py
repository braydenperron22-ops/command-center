"""Personal command-center dashboard: rotating US/Canada macro data, clock, weather."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import fred_client
import statcan_client
import theme
from config import COUNTRY_META, INDICATORS, MARKET_INDEX, ROTATION_SECONDS, TIMEZONE
from flags import flag_for
from icons import icon_for
import market_client
import news
from scenery import background_css_and_html, condition_category, phase_for
import ticker
from tiles import render_tile
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

rotation_index = int(time.time() // ROTATION_SECONDS) % 2
country = "us" if rotation_index == 0 else "ca"
meta = COUNTRY_META[country]

# Only play the crossfade when the country actually changes — the whole
# script reruns every second for the clock tick, so without this the fade
# animation was restarting every single second instead of just on rotation.
country_changed = st.session_state.get("last_country") != country
st.session_state["last_country"] = country
country_anim_class = "fade-wrap" if country_changed else ""

weather = fetch_weather()

if weather:
    phase = phase_for(now, weather["sunrise"], weather["sunset"])
    category = condition_category(weather["weather_code"])
else:
    phase = "day" if 6 <= now.hour < 20 else "night"
    category = "cloudy"

st.markdown(background_css_and_html(weather["weather_code"] if weather else 0, phase), unsafe_allow_html=True)

weather_block = ""
if weather:
    icon_svg = icon_for(category, phase)
    weather_block = f"""<div class="hero-weather">
        <div class="clock weather-condition"><span class="weather-icon">{icon_svg}</span>{weather['temp_c']:.0f}°C</div>
        <div class="date-sub">North Bay</div>
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

market_html = ""
if FRED_API_KEY:
    market = market_client.fetch_ytd_return(MARKET_INDEX[country]["series_id"], FRED_API_KEY)
    if market:
        direction_class = "market-up" if market["ytd_pct"] >= 0 else "market-down"
        sign = "+" if market["ytd_pct"] >= 0 else ""
        market_html = (
            f'<div class="market-pill"><span class="market-pill-label">{MARKET_INDEX[country]["label"]} YTD</span>'
            f'<span class="market-pill-value {direction_class}">{sign}{market["ytd_pct"]:.1f}%</span></div>'
        )

st.markdown(
    f"""<div class="{country_anim_class}" style="text-align:center; margin: 0.8rem 0 1.2rem;">
        <div class="flag-badge">{flag_for(country)}</div>
        <div class="country-name">{meta['name']}</div>{market_html}
    </div>""",
    unsafe_allow_html=True,
)

if not FRED_API_KEY:
    st.error("FRED_API_KEY is not set in Streamlit secrets.")
else:
    seen_as_of = st.session_state.setdefault("seen_as_of", {})

    readings = {}
    new_flags = {}
    for c, indicators in INDICATORS.items():
        for ind in indicators:
            if ind.get("source") == "statcan":
                reading = statcan_client.build_indicator_reading(ind["vector_id"], ind["transform"])
            else:
                reading = fred_client.build_indicator_reading(ind["series_id"], FRED_API_KEY, ind["transform"])
            key = (c, ind["key"])
            readings[key] = reading

            # Flag as "new" only if this session already had a prior value for
            # this indicator and it just changed — first-ever load establishes
            # the baseline instead of flashing everything as new.
            is_new = False
            if reading:
                prior = seen_as_of.get(key)
                if prior is not None and prior != reading["as_of"]:
                    is_new = True
                seen_as_of[key] = reading["as_of"]
            new_flags[key] = is_new

    cols = st.columns(len(INDICATORS[country]))
    for i, ind in enumerate(INDICATORS[country]):
        key = (country, ind["key"])
        with cols[i]:
            render_tile(ind["label"], ind["unit"], readings[key], is_new=new_flags[key])

    schedule = ticker.build_schedule(readings, FRED_API_KEY)

# News alerts: strictly-filtered items queue up and take over the bottom
# bar (normally the release calendar) for TOAST_SECONDS each, breaking-news
# style, before control returns to the calendar ticker.
news_queue = st.session_state.setdefault("news_queue", [])
news_queue.extend(news.get_new_alerts())

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
elif FRED_API_KEY:
    st.markdown(ticker.render_html(schedule, now), unsafe_allow_html=True)
