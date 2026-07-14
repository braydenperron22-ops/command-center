"""Personal command-center dashboard: ambient rotation across Home (macro
data), Conflicts, News, Markets, Internals, and Today — clock/weather
header stays constant."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import air_quality_client
import commute_reminder
import ec_radar
import govee_lighting
import market_yf_client
import news
import pages_conflicts
import pages_home
import pages_internals
import pages_markets
import pages_news
import pages_sports
import pages_today
import pages_weather
import theme
import weather_alerts_bar
from config import (
    AQI_EXTREME,
    AQI_SHOW_THRESHOLD,
    MAX_BURST_ALERTS,
    PAGE_ROTATION_SECONDS,
    PAGES,
    RAIN_LOOKAHEAD_HOURS,
    TIMEZONE,
    UV_HIGH_THRESHOLD,
)
from icons import icon_for, label_for
from scenery import FADE_SECONDS, condition_category, phase_for, scene_html, sky_style
import ticker
from weather_client import fetch_weather

st.set_page_config(page_title="Command Center", layout="wide")
theme.inject()

FRED_API_KEY = st.secrets.get("FRED_API_KEY")

# Rotation is derived from elapsed real time (not a counter), so it
# survives Streamlit Cloud sleep/wake without drifting into a
# fast-forward regardless of this interval. Was 1000ms — a full script
# rerun every second, 86,400 times a day, unattended — but nothing on
# the page actually needs second-level precision anymore: the clock
# only displays minutes, and both the leave and rain countdowns were
# switched to minute granularity for readability reasons (see recent
# history), not just refresh cost. Bumped further to 5000ms (was briefly
# 3000ms) after the app kept crash-looping (segfault) on this free-tier
# container's memory cap even at 3s — erring conservative here rather
# than tuning down in small steps while it's actively unstable. The
# only thing that benefits from a fast interval is the ~3s toast-alert
# intro animation, which is brief and rare; a bit less smooth there is
# a clearly better trade than the app crash-looping and burning through
# every external API's rate limit on each cold restart.
st_autorefresh(interval=5000, key="clock_tick")

# Hosted deployments (Streamlit Cloud) run on the server's own timezone
# (typically UTC), not North Bay's — pin explicitly rather than trusting
# datetime.now(), then drop tzinfo so it stays comparable with the naive
# sunrise/sunset values Open-Meteo returns for the same zone.
now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)

try:
    weather = fetch_weather()
except Exception:
    weather = None

try:
    air_quality = air_quality_client.fetch_air_quality()
except Exception:
    air_quality = None

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

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lerp_hex(a: str, b: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def _format_countdown(remaining_seconds: float) -> str:
    # Minute granularity with worded units ("1h 26m"/"45 min"), not a
    # colon-separated clock face ticking every second — that read as a
    # live stopwatch, so at 1s autorefresh it either looked like it was
    # constantly refreshing (seconds precision) or stuck/broken (a colon
    # format that only moves once a minute). Words don't carry that
    # "should be actively ticking" expectation, and this also means most
    # reruns produce byte-identical HTML here instead of changing every
    # single tick (same fix as pages_today's leave countdown).
    total_minutes = max(0, int(remaining_seconds) // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes} min"


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha:.2f})"


UV_EXTREME = 11  # UV index at which the badge reaches full vibrant red
RAIN_LOOKAHEAD_SECONDS = RAIN_LOOKAHEAD_HOURS * 3600

weather_block = ""
if weather:
    icon_svg = icon_for(category, phase)
    condition_label = label_for(weather["weather_code"])

    hilo_html = ""
    high, low = weather.get("forecast_high_c"), weather.get("forecast_low_c")
    if high is not None and low is not None:
        hilo_html = f' · <span class="weather-hilo">H:{high:.0f}° L:{low:.0f}°</span>'

    extras = []
    precip_at = weather.get("rain_at")
    if precip_at is not None:
        remaining = (precip_at - now).total_seconds()
        if remaining > 0:
            # Ticks down every second between weather refreshes since
            # precip_at is a fixed target timestamp, not a relative
            # "hours from now" that would otherwise sit frozen (or go
            # stale) for the full 15-minute cache window. Background
            # darkens as it gets closer — pale and airy when it's hours
            # off, heavy and imminent right before it hits — but the
            # text stays a fixed bright color rather than darkening
            # along with it: that used to mean the badge nearly
            # vanished (dark-on-dark) right when it mattered most.
            # Snow gets its own icier palette rather than reusing rain's
            # blue for everything — this location gets real winter
            # weather (see weather_client._next_precip_at), and the
            # color is a second, glance-only signal alongside the word
            # itself for which one it actually is.
            is_snow = weather.get("precip_kind") == "snow"
            label = "Snow" if is_snow else "Rain"
            fill_start = "#EAF6FF" if is_snow else "#64D2FF"
            fill_end = "#243449" if is_snow else "#0A2472"
            closeness = 1 - min(remaining / RAIN_LOOKAHEAD_SECONDS, 1.0)
            precip_fill = _lerp_hex(fill_start, fill_end, closeness)
            precip_bg = _rgba(precip_fill, 0.22 + closeness * 0.5)
            countdown = _format_countdown(remaining)
            # The chance rides along rather than a bare "Rain in Xh" —
            # this is EC's own forecast probability, not a promise, and
            # EC's own number can (and does) get revised before the
            # hour it named actually arrives. Showing it honestly beats
            # a flat statement that reads as certain when it isn't.
            chance = weather.get("precip_chance")
            chance_html = f' · {chance}%' if chance is not None else ""
            extras.append(
                f'<span class="weather-extra" style="color:{fill_start}; '
                f'background:{precip_bg}; border-color:{precip_fill};">{label} in {countdown}{chance_html}</span>'
            )
    # A second, independent signal alongside the forecast-percentage
    # badge above: real precipitation actually detected on EC's own
    # live radar right now, sampled directly from the same image the
    # Weather page's radar tile shows (see ec_radar.nearby_precip_km).
    # This can catch a real nearby cell EC's area-wide forecast
    # percentage doesn't — the exact gap that had this dashboard
    # showing nothing while a phone's radar-based nowcast (Apple/Dark
    # Sky) already knew better. Independent of the badge above: can
    # show even when that one doesn't, or alongside it.
    nearby_km = ec_radar.nearby_precip_km("snow" if category == "snow" else "rain")
    if nearby_km is not None:
        nearby_label = "Snow" if category == "snow" else "Rain"
        nearby_text = "on you now" if nearby_km < 1 else f"{nearby_km:.0f} km away"
        extras.append(
            f'<span class="weather-extra" style="color:#64D2FF; '
            f'background:rgba(100,210,255,0.22); border-color:#64D2FF;">{nearby_label} nearby · {nearby_text}</span>'
        )
    if weather["uv_index"] is not None and weather["uv_index"] > UV_HIGH_THRESHOLD:
        uv = weather["uv_index"]
        intensity = min((uv - UV_HIGH_THRESHOLD) / (UV_EXTREME - UV_HIGH_THRESHOLD), 1.0)
        uv_color = _lerp_hex("#FFB340", "#FF3B30", intensity)
        uv_bg = _rgba(uv_color, 0.22 + intensity * 0.25)
        extras.append(
            f'<span class="weather-extra" style="color:{uv_color}; '
            f'background:{uv_bg}; border-color:{uv_color};">UV {uv:.0f}</span>'
        )
    # Wildfire smoke is a real recurring issue for this region — same
    # provider as the weather call above (Open-Meteo's Air Quality
    # API), no new vendor/key. Yellow->purple rather than UV's
    # orange->red so the two badges read as distinct signals even at a
    # glance, not "two UV badges."
    aqi = air_quality.get("us_aqi") if air_quality else None
    if aqi is not None and aqi > AQI_SHOW_THRESHOLD:
        intensity = min((aqi - AQI_SHOW_THRESHOLD) / (AQI_EXTREME - AQI_SHOW_THRESHOLD), 1.0)
        aqi_color = _lerp_hex("#FFD60A", "#8B008B", intensity)
        aqi_bg = _rgba(aqi_color, 0.22 + intensity * 0.25)
        extras.append(
            f'<span class="weather-extra" style="color:{aqi_color}; '
            f'background:{aqi_bg}; border-color:{aqi_color};">AQI {aqi:.0f}</span>'
        )
    extras_html = f'<div class="weather-extras">{"".join(extras)}</div>' if extras else ""

    weather_block = f"""<div class="hero-weather">
        <div class="clock weather-condition"><span class="weather-icon">{icon_svg}</span>{weather['temp_c']:.0f}°C</div>
        <div class="weather-condition-label">{condition_label}</div>
        <div class="date-sub">Corbeil{hilo_html}</div>{extras_html}
    </div>"""

# Directly above the clock, page-independent — see
# commute_reminder.render_leave_headline for why (visible regardless of
# which of the 6 rotating pages is up, unlike Today's own content).
try:
    commute_reminder.render_leave_headline(now)
except Exception:
    pass

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

# Intraday change of whatever instrument best represents "the market"
# right now drives the Govee light's base color below — same open/
# closed/weekend swap (index / futures / crypto) as the Markets page
# itself, via market_yf_client.primary_symbol(). Fetched unconditionally
# like the FRED readings above, but this reuses quote_for's own 5-minute
# cache (the same cache the Markets page itself hits), so it's free
# network-wise once anything has warmed it.
try:
    market_status = market_yf_client.market_status()
    _primary_quote = market_yf_client.quote_for(market_yf_client.primary_symbol(market_status))
    market_intraday_pct = _primary_quote["intraday"] if _primary_quote else None
except Exception:
    market_status = None
    market_intraday_pct = None

# The one gap between the hero row above and the page content below
# that wasn't wrapped in a try/except — everything else on either side
# of it already is, so a bug here was the one way the whole page body
# (and everything after it: ticker, Govee sync) could go missing while
# the hero row/leave headline (rendered earlier) stayed up. Extremely
# unlikely to actually throw (PAGES/PAGE_ROTATION_SECONDS are static
# config), but there's no reason to leave it as the one unguarded seam.
try:
    page_index = int(time.time() // PAGE_ROTATION_SECONDS) % len(PAGES)
    page = PAGES[page_index]
except Exception:
    page = "today"

with st.container(key="page_body"):
    if page == "home":
        if not FRED_API_KEY:
            # Themed to match the rest of the app rather than Streamlit's
            # default red alert box, which would otherwise be the one
            # element on screen that doesn't look like it belongs here.
            st.markdown(
                '<div class="tile"><div class="tile-prev">FRED_API_KEY is not set in Streamlit secrets.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            _safe_render(pages_home.render, FRED_API_KEY, readings, new_flags)
    elif page == "conflicts":
        _safe_render(pages_conflicts.render)
    elif page == "news":
        _safe_render(pages_news.render)
    elif page == "markets":
        _safe_render(pages_markets.render)
    elif page == "internals":
        _safe_render(pages_internals.render)
    elif page == "today":
        _safe_render(pages_today.render, now)
    elif page == "weather":
        _safe_render(pages_weather.render)
    elif page == "sports":
        _safe_render(pages_sports.render)
    else:
        # Every other branch above has a fallback (a real page render,
        # or _safe_render's own error tile) — this is the one path with
        # none: if `page` somehow doesn't match any of PAGES, the
        # container would otherwise render completely empty with zero
        # indication why, for as long as that state persists. Silent
        # blank content with no error and no crash is exactly what was
        # reported after a morning of rapid redeploys, so this is here
        # to turn that into something visible/diagnosable if it recurs.
        st.markdown(
            f'<div class="tile"><div class="tile-prev">Unexpected page state ({page!r}) — will retry automatically.</div></div>',
            unsafe_allow_html=True,
        )

# Leave-for-work reminder: drops into the same bottom-bar queue as
# breaking news (below), rather than a separate UI element — see
# commute_reminder.py. Wrapped separately from that queue's own
# try/except so a bug here can't also take down real breaking-news
# alerts, and appended to new_alerts before that block runs so a
# freshly-due milestone gets picked up in this same rerun.
try:
    commute_alert = commute_reminder.check(now)
    if commute_alert:
        new_alerts.append(commute_alert)
except Exception:
    pass

# News alerts: strictly-filtered items queue up and take over the bottom
# bar (normally the release calendar) for TOAST_SECONDS each, breaking-news
# style, before control returns to the calendar ticker. This happens
# regardless of which page is active.
#
# A feed outage that recovers can surface dozens of headlines in one
# batch (everything that was never marked "seen" while it was down) —
# capped to the most recent MAX_BURST_ALERTS so that doesn't turn into
# hours of backlog playing through this bar one at a time. The commute
# reminder appended above is always the last element of new_alerts at
# that point, so this trim (which keeps the most recent items) can
# never drop it even during a real burst.
#
# Defined here (not just inside the try) so the Govee block below always
# has a real value to check even if this try body fails before reaching
# the assignment further down — it has its own try/except too, but there's
# no reason to make it depend on this block's internals for a safe default.
current_alert, elapsed = None, None
try:
    news_queue = st.session_state.setdefault("news_queue", [])
    if len(new_alerts) > MAX_BURST_ALERTS:
        new_alerts = new_alerts[-MAX_BURST_ALERTS:]
    news_queue.extend(new_alerts)

    now_ts = time.time()
    if news_queue:
        current_alert = news_queue[0]
        if "shown_at" not in current_alert:
            current_alert["shown_at"] = now_ts
        elapsed = now_ts - current_alert["shown_at"]
        if elapsed > news.TOAST_SECONDS:
            news_queue.pop(0)
            current_alert, elapsed = None, None

    if current_alert:
        if current_alert.get("kind") == "commute":
            commute_reminder.render_bar(current_alert, elapsed)
        else:
            news.render_alert_bar(current_alert, elapsed)
    elif FRED_API_KEY and readings:
        schedule = ticker.build_schedule(readings, FRED_API_KEY)
        st.markdown(ticker.render_html(schedule, now), unsafe_allow_html=True)
except Exception:
    pass

# Bedroom Govee light/plug: reactive to the same phase/market/news signals
# already driving the dashboard's own visuals above. Wrapped like every
# other side-effect block here — a Govee outage or API hiccup should never
# affect the dashboard itself.
try:
    breaking_elapsed = None
    if current_alert and current_alert.get("important") and elapsed is not None and elapsed < govee_lighting.FLASH_SECONDS:
        breaking_elapsed = elapsed
    govee_lighting.sync_lights(phase, market_intraday_pct, breaking_elapsed, now, weather["sunset"] if weather else None)
    govee_lighting.sync_plug(now, weather["first_light"] if weather else None, weather["last_light"] if weather else None)
except Exception:
    pass
