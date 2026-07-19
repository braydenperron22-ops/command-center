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
import morning_briefing
import news
import pages_conflicts
import pages_home
import pages_household
import pages_internals
import pages_markets
import pages_news
import pages_radar
import pages_recovery
import pages_scores
import pages_sports
import pages_today
import pages_weather
import payday_schedule
import theme
import waste_schedule
import weather_alerts_bar
import weather_records_client
import wildfire_client
from config import (
    AQI_EXTREME,
    AQI_SHOW_THRESHOLD,
    FEELS_LIKE_DIVERGENCE_THRESHOLD_C,
    MAX_BURST_ALERTS,
    PAGE_DURATION_OVERRIDES,
    PAGE_ROTATION_SECONDS,
    PAGES,
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

# Resolved early (not down by the page-routing block that used to live
# near the bottom of this file) so the mobile nav bar below can render
# immediately, before any hero content — a phone picking up this page
# shouldn't have to wait through the hero row just to see a nav. A
# ?page= query param always wins over the rotation timer: that's what
# lets a phone hitting the same public URL jump straight to a page
# instead of sitting through the kiosk's 5-minute rotation the way the
# actual monitor does. The kiosk's own browser tab never sets this
# param, so its rotation is completely untouched by any of this.
# Captured once and reused for every rotation-timer computation this
# run (page selection here, and pages_home's own US/Canada rotation
# later) — confirmed live this was a real bug, not a hypothetical: with
# each module independently calling time.time() at a slightly different
# instant, a rerun landing right on a 300-second boundary could compute
# page_index from the OLD bucket (still "home") while pages_home
# computed its country from the NEW bucket, flashing the wrong country
# for one rerun before the page itself rotated away — which is exactly
# what "Canada shows for ~5 seconds then jumps to Conflicts" was.
def _scheduled_page(epoch_seconds: float) -> tuple[str, float, float]:
    """Which page is up right now, plus how far into its own window
    (seconds) and how long that window is. Most pages share the uniform
    PAGE_ROTATION_SECONDS, but PAGE_DURATION_OVERRIDES (config.py, empty
    by default) can give a specific page more than one slot's worth of
    time without disturbing the plain modulo math the uniform pages
    still rely on elsewhere (pages_home's own US/Canada rotation,
    pages_scores' league rotation) since those aren't derived from this
    cumulative schedule at all.
    """
    durations = [PAGE_DURATION_OVERRIDES.get(p, PAGE_ROTATION_SECONDS) for p in PAGES]
    position = epoch_seconds % sum(durations)
    for p, d in zip(PAGES, durations):
        if position < d:
            return p, position, d
        position -= d
    return PAGES[-1], 0.0, durations[-1]  # unreachable: position < sum(durations) always


_rotation_epoch = time.time()
_requested_page = None
try:
    _requested_page = st.query_params.get("page")
    if _requested_page in PAGES:
        page = _requested_page
    else:
        page, _, _ = _scheduled_page(_rotation_epoch)
except Exception:
    page = "today"

_PAGE_LABELS = {
    "home": "Home", "conflicts": "Conflicts", "news": "News", "markets": "Markets",
    "internals": "Internals", "today": "Today", "household": "Household",
    "weather": "Weather", "radar": "Radar", "sports": "Sports", "scores": "Scores",
}

# Invisible on the kiosk monitor — theme.py hides .mobile-nav entirely
# above its phone-width breakpoint, so this only ever actually shows up
# on a phone-sized browser. "Auto" clears the override and resumes the
# timer-based rotation on that same phone tab. Per-page color comes from
# a mobile-nav-item-{key} class (theme.py) rather than an inline style —
# confirmed live that Streamlit strips style="" from <a> tags even with
# unsafe_allow_html=True.
_nav_items = "".join(
    f'<a class="mobile-nav-item mobile-nav-item-{key}{" mobile-nav-item-active" if key == page else ""}" '
    f'href="?page={key}">{_PAGE_LABELS[key]}</a>'
    for key in PAGES
)
_auto_active = " mobile-nav-item-active" if _requested_page not in PAGES else ""
st.markdown(
    f'<div class="mobile-nav"><a class="mobile-nav-item mobile-nav-item-auto{_auto_active}" href="?">Auto</a>{_nav_items}</div>',
    unsafe_allow_html=True,
)

# Slim progress bar at the very top showing how far through the current
# 5-minute window this page is, filling up toward the next rotation.
# Only shown while real auto-rotation is actually driving the page — a
# manual ?page= override (see above) pins the page regardless of this
# timer, so a countdown then would be advertising a change that isn't
# coming. A flat width:X% set fresh each rerun only ever jumps in
# discrete 5-second steps — same reason CSS transition doesn't survive
# this app's autorefresh (see scenery.py's own notes): each rerun
# re-emits the element already at its new value, with nothing to
# interpolate from.
#
# A server-computed *negative* animation-delay alone isn't enough here
# (confirmed live: the bar would drift off the real rotation clock and
# stop lining up with the actual page flip) — Streamlit patches this
# element's style attribute on the SAME persisted DOM node across
# reruns rather than replacing it, and mutating animation-delay on an
# already-running animation is a no-op per the CSS spec; only a
# genuinely new animation instance respects a new delay. So the class
# is alternated every rerun between two functionally identical
# keyframe animations (rotation-timer-fill-a/-b, theme.py) — changing
# animation-name always forces a real restart even on the same node,
# which makes the freshly computed delay actually take effect each
# time, while the browser still tweens smoothly in between reruns.
if _requested_page not in PAGES:
    _, _rotation_elapsed, _rotation_page_seconds = _scheduled_page(_rotation_epoch)
    st.session_state["_rotation_bar_tick"] = st.session_state.get("_rotation_bar_tick", 0) + 1
    _bar_variant = "a" if st.session_state["_rotation_bar_tick"] % 2 == 0 else "b"
    # animation-duration set inline (longhand) alongside animation-delay
    # so a page with a PAGE_DURATION_OVERRIDES entry fills over its own
    # real window instead of the CSS class's plain 300s — inline
    # longhand wins over the shorthand's duration component without
    # touching animation-name/timing-function/iteration-count, which
    # still need to come from the class for the a/b restart trick above
    # to work.
    st.markdown(
        f'<div class="rotation-timer-track">'
        f'<div class="rotation-timer-fill-{_bar_variant}" '
        f'style="animation-delay:-{_rotation_elapsed:.2f}s; animation-duration:{_rotation_page_seconds:.0f}s;"></div></div>',
        unsafe_allow_html=True,
    )

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

# Genuinely extreme AQI (real wildfire smoke, not routine haze) takes
# over the sky's own color instead of whatever the weather condition
# would normally show — the same on-screen counterpart to the Govee
# light's SMOKE_COLOR override, but actually visible on the dashboard
# itself. Only matters while phase isn't "night" (scenery.py's night
# stops are pure black regardless of category, same as every other
# weather condition already), which is fine — the screen dims heavily
# overnight anyway.
if air_quality and (air_quality.get("us_aqi") or 0) >= AQI_EXTREME:
    category = "smoke"

# Same kind resolution the hero badge and the radar-derived alerts
# below all use — EC's snow radar layer isn't itself gated by
# temperature and can show the same reflectivity echo as the rain
# layer regardless of season, so only ever checking the kind that
# actually matches today's real weather avoids a nonsense "heavy snow"
# alert firing in July. Resolved here (rather than down where it's
# first used) so severe_weather_active below can use it too.
_alert_precip_kind = "snow" if category == "snow" else "rain"

# True during EC's own most dangerous hazard tier (tornado/hurricane/
# tsunami, from its official alert feed) OR a real ongoing stretch of
# our own radar-confirmed heavy precipitation (see
# ec_radar.severe_weather_stint_active) — checking EC's feed alone
# isn't enough: confirmed live it had nothing active at all for a real,
# radar-confirmed heavy-rain night, so relying on it by itself would
# miss the actual event entirely. This is the "genuine emergency" tier
# — drives the screen going fully bright (not just dimmed less, see
# night_dim below) rather than the light, which no longer reacts to
# weather at all (session feedback: waking the bedroom light overnight
# was the wrong call). Each half guarded separately so a radar hiccup
# can't also take out the (already reliable) EC-alert half.
try:
    extreme_weather = weather_alerts_bar.current_severity() == "extreme"
except Exception:
    extreme_weather = False
try:
    severe_weather_active = extreme_weather or ec_radar.severe_weather_stint_active(_alert_precip_kind)
except Exception:
    severe_weather_active = extreme_weather

# A softer pair of signals for ordinary (non-severe) rain — session
# request: the screen should still dim overnight during a rain storm,
# just not all the way to the "genuinely dim enough to sleep next to"
# floor. Both feed the screen's own quiet_hours/weather_wake_recent
# logic below; neither reaches the bedroom light anymore (see
# govee_lighting.sync_lights, which no longer takes weather signals at
# all). rain_active covers both approaching and already-arrived
# precipitation (any kind detected at all, see ec_radar.precip_status);
# rain_incoming is specifically the not-arrived-yet subset of that.
try:
    _wake_precip_status = ec_radar.precip_status(_alert_precip_kind)
except Exception:
    _wake_precip_status = None
rain_active = _wake_precip_status is not None
rain_incoming = _wake_precip_status is not None and _wake_precip_status["state"] == "approaching"

# Session request: staying fully bright (or even just less-dim) for an
# entire severe stint or rain approach — which can run for hours — was
# itself keeping the room awake; the actual point was only ever to
# "let me know, then let me go back to sleep." After QUIET_HOURS_START_
# HOUR, the screen now defaults to full sleep-dim regardless of ongoing
# weather, briefly brightening only around when something NEW actually
# starts, not for its whole duration. hour < 12 (rather than a second
# fixed hour) catches every hour from midnight through morning without
# needing its own boundary — phase == "night" already can't extend
# into the afternoon, so this only ever matters for the pre-dawn half
# of the night.
QUIET_HOURS_START_HOUR = 21
quiet_hours = phase == "night" and (now.hour >= QUIET_HOURS_START_HOUR or now.hour < 12)
# How long the brief brightening lasts once triggered — long enough to
# actually wake up, look, and read the badge, short enough that it
# can't turn into "bright all night" the way the previous whole-stint
# override did.
WEATHER_WAKE_WINDOW_SECONDS = 90
weather_worth_waking_for = severe_weather_active or rain_incoming
if weather_worth_waking_for and not st.session_state.get("weather_was_worth_waking_for", False):
    st.session_state["weather_wake_started_at"] = time.time()
st.session_state["weather_was_worth_waking_for"] = weather_worth_waking_for
weather_wake_recent = weather_worth_waking_for and (
    time.time() - st.session_state.get("weather_wake_started_at", 0) < WEATHER_WAKE_WINDOW_SECONDS
)

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
        sky_style(category, phase, bg_fade_from, bg_blend),
        unsafe_allow_html=True,
    )
    st.markdown(
        scene_html(category, phase),
        unsafe_allow_html=True,
    )

    # Dim the whole UI at night — not just the background, since bright
    # white tile text/badges in a pitch-black room is still harsh even
    # with a black sky behind them. Ramps with the same fade progress
    # already tracked above rather than snapping dim on/off at the phase
    # boundary.
    RAIN_NIGHT_DIM_CAP = 0.5  # night_dim ceiling during ordinary rain — dimmer than day, well short of the full sleep-dim floor
    if phase == "night" and bg_fade_from == "night":
        night_dim = 1.0
    elif phase == "night":
        night_dim = bg_blend
    elif bg_fade_from == "night":
        night_dim = 1.0 - bg_blend
    else:
        night_dim = 0.0

    # Past quiet hours, weather only brightens the screen briefly around
    # when something new starts (weather_wake_recent) — otherwise it
    # stays on the full sleep-dim floor no matter how long a stint or
    # approach has been running, which is the whole fix for "this kept
    # me awake." Before quiet hours (still evening, presumably awake
    # anyway), the previous whole-duration behavior still applies:
    # severe weather overrides dimming entirely, ordinary rain only
    # softens it to RAIN_NIGHT_DIM_CAP.
    if quiet_hours and not weather_wake_recent:
        night_dim = 1.0
    elif severe_weather_active:
        night_dim = 0.0
    elif rain_active:
        night_dim = min(night_dim, RAIN_NIGHT_DIM_CAP)

    if night_dim > 0:
        # This runs 24/7 in a bedroom — night needs to be genuinely dim
        # enough to sleep next to, not just "a bit darker." Used to be a
        # `filter: brightness()` on the whole main container, but a CSS
        # `filter` on an ancestor makes any `position: fixed` descendant
        # position itself relative to THAT ancestor instead of the real
        # viewport — confirmed live, this was quietly breaking the
        # bottom ticker and both alert toasts specifically overnight
        # (mis-positioned near the top of a scrolled page), the one
        # window when nobody was looking at the screen to notice. A
        # fixed black overlay dims the same way (and still covers the
        # ticker/alert bars, matching the old filter's behavior — they
        # were dimmed by it too) without touching `filter` on anything,
        # so there's no containing-block side effect. pointer-events:
        # none so it never blocks the phone nav pills underneath it.
        overlay_alpha = night_dim * 0.82
        st.markdown(
            f'<div style="position:fixed; inset:0; background:rgba(0,0,0,{overlay_alpha:.3f}); '
            f'pointer-events:none; z-index:20;"></div>',
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


def _badge_bg(hex_color: str, alpha: float) -> str:
    """A badge's tint layered over the app's own frosted-panel color
    (see .tile in theme.py) rather than the bare tint alone. These
    badges set `color` to the same hue as this background tint (the
    text needs to read as "this is the AQI/UV/etc signal," not just
    "here's some text") — but the tint used to composite directly over
    whatever's actually behind the badge, which is the time-of-day
    scenery gradient (scenery.py), swinging from near-black at night to
    a much lighter sky by day. On a light-sky render, same-hue text and
    background could end up close enough in lightness to be hard to
    read — confirmed live as an actual readability complaint, not just
    a theoretical one. A guaranteed dark base underneath keeps the
    effective background reliably dark regardless of scenery, so the
    text-vs-background contrast this was always meant to have doesn't
    depend on whatever's rendered behind it."""
    r, g, b = _hex_to_rgb(hex_color)
    tint = f"rgba({r},{g},{b},{alpha:.2f})"
    return f"linear-gradient({tint}, {tint}), rgba(12,12,16,0.72)"


def _precip_timing_phrase(status: dict | None) -> str | None:
    """"in 45 min" / "approaching" / "clears in 20 min" / "here now" —
    None if there's no confirmed timing yet at all. Shared by both the
    routine and severe precip badges below so a "Heavy rain" badge
    doesn't drop the ETA a plain "Rain" badge would still show — severe
    intensity and timing are two different questions, and knowing one
    shouldn't cost you the other."""
    if status is None:
        return None
    if status["state"] == "arrived":
        return (
            f"clears in {_format_countdown(status['minutes'] * 60)}"
            if status["minutes"] is not None else "here now"
        )
    return (
        f"in {_format_countdown(status['minutes'] * 60)}"
        if status["minutes"] is not None else "approaching"
    )


UV_EXTREME = 11  # UV index at which the badge reaches full vibrant red

weather_block = ""
if weather:
    icon_svg = icon_for(category, phase)
    condition_label = label_for(weather["weather_code"])

    hilo_html = ""
    high, low = weather.get("forecast_high_c"), weather.get("forecast_low_c")
    if high is not None and low is not None:
        hilo_html = f' · <span class="weather-hilo">H:{high:.0f}° L:{low:.0f}°</span>'

    extras = []
    # One badge, two states — "Rain in ___" while it's inbound, "Clears
    # in ___" once it's here — instead of the two separate, overlapping
    # badges this used to be (an EC forecast-percentage one and a
    # radar-tracking one, which could both be on screen at once). The
    # live radar signal (ec_radar.precip_status) wins whenever it has
    # one — it's real detected precipitation, tracked frame to frame,
    # not a probability — with EC's forecast-percentage countdown as
    # the fallback for when radar hasn't caught anything yet (still
    # further out than radar's own 25km "nearby" cutoff, or further out
    # in time than its 6-min cadence has caught up to).
    is_snow = category == "snow"
    precip_label = "Snow" if is_snow else "Rain"
    precip_kind = "snow" if is_snow else "rain"
    # Checked independent of (and before) the routine approaching/
    # arrived badge below — that classification needs multiple radar
    # samples spaced minutes apart before it'll call something
    # "approaching" (see ec_radar._record_and_trend), but genuinely
    # heavy precipitation (ec_radar.SIGNIFICANT_MM_H) is worth flagging
    # the moment it's detected, not once a trend has had time to
    # establish. Same red as a breaking-news/bad-tile accent, and
    # persists for as long as the condition actually holds
    # (severe_weather_alert's own toast is just a one-time ping when
    # it first starts).
    severe = ec_radar.severe_precip_status(precip_kind)
    status = ec_radar.precip_status(precip_kind)
    if severe is not None:
        # Same timing phrase the routine badge below uses — severity
        # and ETA are two different questions (see
        # _precip_timing_phrase), so "Heavy rain" shouldn't drop the
        # "in 15 min"/"clears in 20 min" part a plain "Rain" badge
        # would still show. None (no confirmed timing yet at all) falls
        # back to the intensity-only text this badge always showed.
        timing = _precip_timing_phrase(status)
        text = (
            f"Heavy {precip_label.lower()} {timing} · {severe['mm_h']:.0f} mm/h"
            if timing else f"Heavy {precip_label.lower()} · {severe['mm_h']:.0f} mm/h"
        )
        # Same "scales with real magnitude" treatment as UV/AQI/wildfire
        # above — this badge used to render every severe reading in the
        # exact same fixed red whether it was 24 mm/h (just over the
        # threshold) or 100+ mm/h (genuinely torrential), flattening a
        # real difference into one color. End color (violet) is EC's
        # own radar-legend color at this same intensity (see
        # ec_radar.SEVERE_BADGE_MAX_MM_H) — this badge and the actual
        # map now agree on what "worse" looks like.
        severe_intensity = min(
            (severe["mm_h"] - ec_radar.SIGNIFICANT_MM_H) / (ec_radar.SEVERE_BADGE_MAX_MM_H - ec_radar.SIGNIFICANT_MM_H),
            1.0,
        )
        severe_color = _lerp_hex("#FF6961", "#BF5AF2", severe_intensity)
        severe_bg = _badge_bg(severe_color, 0.28 + severe_intensity * 0.15)
        extras.append(
            f'<span class="weather-extra" style="color:{severe_color}; '
            f'background:{severe_bg}; border-color:{severe_color};">{text}</span>'
        )
    elif status is not None:
        if status["state"] == "arrived":
            text = (
                f"Clears in {_format_countdown(status['minutes'] * 60)}"
                if status["minutes"] is not None else f"{precip_label} now"
            )
        else:
            # Guarded the same way the "arrived" branch above already
            # is, even though nothing currently reaching this branch
            # constructs a None here — this whole hero row sits at
            # module top level with no enclosing try/except (unlike
            # every page render, which goes through _safe_render), so
            # a crash here takes down the entire app on every rerun,
            # not just one page. Cheap insurance against a catastrophic
            # failure mode is worth it even without a concrete
            # reproduction.
            text = (
                f"{precip_label} in {_format_countdown(status['minutes'] * 60)}"
                if status["minutes"] is not None else f"{precip_label} approaching"
            )
        extras.append(
            f'<span class="weather-extra" style="color:#64D2FF; '
            f'background:{_badge_bg("#64D2FF", 0.22)}; border-color:#64D2FF;">{text}</span>'
        )
    # No EC-forecast fallback here on purpose (there used to be one,
    # using weather["rain_at"]) — EC's hourly forecast timing can be
    # genuinely unreliable, and radar (ec_radar.precip_status, above)
    # is real detected precipitation, not a prediction. Nothing shows
    # here at all until radar itself has something confident to say,
    # rather than falling back to a number that might be hours off.
    if weather["uv_index"] is not None and weather["uv_index"] > UV_HIGH_THRESHOLD:
        uv = weather["uv_index"]
        intensity = min((uv - UV_HIGH_THRESHOLD) / (UV_EXTREME - UV_HIGH_THRESHOLD), 1.0)
        uv_color = _lerp_hex("#FFB340", "#FF3B30", intensity)
        uv_bg = _badge_bg(uv_color, 0.22 + intensity * 0.25)
        extras.append(
            f'<span class="weather-extra" style="color:{uv_color}; '
            f'background:{uv_bg}; border-color:{uv_color};">UV {uv:.0f}</span>'
        )
    # "Feels like" (Open-Meteo's apparent_temperature, same call as the
    # actual temp above — no new fetch) only earns a badge once it
    # genuinely diverges from the real temperature; most of the time
    # it's within a degree and saying so would just be noise. Warmer
    # gets heat's orange-red, colder gets a cold blue — same "color as
    # a second signal alongside the word" convention as rain/snow above.
    feels_like = weather.get("feels_like_c")
    if feels_like is not None:
        feels_diff = feels_like - weather["temp_c"]
        if abs(feels_diff) >= FEELS_LIKE_DIVERGENCE_THRESHOLD_C:
            feels_color = "#FF9F0A" if feels_diff > 0 else "#64D2FF"
            feels_bg = _badge_bg(feels_color, 0.22)
            extras.append(
                f'<span class="weather-extra" style="color:{feels_color}; '
                f'background:{feels_bg}; border-color:{feels_color};">Feels like {feels_like:.0f}°C</span>'
            )
    # The CURRENT actual reading against the historical extreme for
    # this exact calendar date (see weather_records_client) — the
    # day's forecast high/low deliberately isn't used here: showing
    # "Record low" all afternoon because of an 8am forecast reading
    # would be describing a moment that isn't actually happening right
    # now. Only shows up on the rare moment it's genuinely close to or
    # past the record, same "only badge a real threshold crossing"
    # convention as UV/AQI above. Same warm/cool convention as "Feels
    # like" just above: orange for a hot extreme, blue for a cold one.
    record = weather_records_client.record_context(weather["temp_c"])
    if record is not None:
        exceeded = (
            (record["kind"] == "high" and record["value"] >= record["record"])
            or (record["kind"] == "low" and record["value"] <= record["record"])
        )
        record_label = "Record" if exceeded else "Near record"
        record_color = "#FF9F0A" if record["kind"] == "high" else "#64D2FF"
        record_bg = _badge_bg(record_color, 0.22)
        extras.append(
            f'<span class="weather-extra" style="color:{record_color}; '
            f'background:{record_bg}; border-color:{record_color};">'
            f'{record_label} {record["kind"]} · {record["record"]:.0f}° in {record["year"]}</span>'
        )
    # Wildfire smoke is a real recurring issue for this region — same
    # provider as the weather call above (Open-Meteo's Air Quality
    # API), no new vendor/key. Yellow->purple rather than UV's
    # orange->red so the two badges read as distinct signals even at a
    # glance, not "two UV badges." Trend arrow (see
    # air_quality_client._record_and_trend) answers the more useful
    # half of the question most days — not just "how bad," but "is a
    # plume rolling in or already clearing out."
    aqi = air_quality.get("us_aqi") if air_quality else None
    if aqi is not None and aqi > AQI_SHOW_THRESHOLD:
        intensity = min((aqi - AQI_SHOW_THRESHOLD) / (AQI_EXTREME - AQI_SHOW_THRESHOLD), 1.0)
        aqi_color = _lerp_hex("#FFD60A", "#8B008B", intensity)
        aqi_bg = _badge_bg(aqi_color, 0.22 + intensity * 0.25)
        trend_arrow = {"rising": " ↑", "falling": " ↓", "steady": " →"}.get(air_quality.get("trend"), "")
        # 1-10 level instead of the raw 0-500 AQI number (see
        # air_quality_client.level — shared with morning_briefing.py's
        # own prose so both always agree on the same reading).
        aqi_level = air_quality_client.level(aqi)
        extras.append(
            f'<span class="weather-extra" style="color:{aqi_color}; '
            f'background:{aqi_bg}; border-color:{aqi_color};">AQI {aqi_level}{trend_arrow}</span>'
        )
    # The actual cause behind a bad-AQI day is often a wildfire hundreds
    # of km away, not anything local — this is the one badge answering
    # "where's the smoke coming from," not just "how bad is it right
    # now" (see wildfire_client.py). Hard-gated to real wildfire season,
    # so it's simply absent the rest of the year rather than checking
    # and finding nothing. Also gated on the AQI badge itself already
    # showing — a detected hotspot 300km away with air quality still
    # fine here isn't actually affecting anything yet, so it stays
    # paired with the symptom it's explaining rather than showing up on
    # its own as an unexplained, possibly alarming, standalone signal.
    wildfire = wildfire_client.nearest_wildfire() if aqi is not None and aqi > AQI_SHOW_THRESHOLD else None
    if wildfire is not None:
        intensity = 1 - min(wildfire["distance_km"] / wildfire_client.SHOW_RADIUS_KM, 1.0)
        wildfire_color = _lerp_hex("#FFB340", "#FF3B30", intensity)
        wildfire_bg = _badge_bg(wildfire_color, 0.22 + intensity * 0.25)
        extras.append(
            f'<span class="weather-extra" style="color:{wildfire_color}; '
            f'background:{wildfire_bg}; border-color:{wildfire_color};">'
            f'Wildfire · {wildfire["distance_km"]:.0f} km</span>'
        )
    # Garbage/recycling day — used to be its own always-visible tile on
    # the Household page; moved here and gated to "today or tomorrow"
    # (see waste_schedule.next_pickup) so it reads like every other hero
    # badge, something worth a glance right now, not a permanent daily
    # fixture. Tomorrow is included, not just today, since bins actually
    # go out the night before pickup — a same-day-only badge would miss
    # the one moment this is most actionable.
    pickup = waste_schedule.next_pickup(now.date())
    if pickup["days_until"] <= 1:
        when = "today" if pickup["days_until"] == 0 else "tomorrow"
        extras.append(
            f'<span class="weather-extra" style="color:#A2845E; '
            f'background:{_badge_bg("#A2845E", 0.22)}; border-color:#A2845E;">'
            f'{pickup["kind"]} {when}</span>'
        )
    # Payday — same spot and same "today or tomorrow" gating as the
    # garbage badge right above, not a permanent fixture. Green (the
    # app's existing "good" tone, matching market-up/badge-good) rather
    # than a color already claimed by another badge.
    payday = payday_schedule.next_payday(now.date())
    if payday["days_until"] <= 1:
        payday_when = "today" if payday["days_until"] == 0 else "tomorrow"
        extras.append(
            f'<span class="weather-extra" style="color:#32D74B; '
            f'background:{_badge_bg("#32D74B", 0.22)}; border-color:#32D74B;">'
            f'Payday {payday_when}</span>'
        )
    # Recovery status — same pill styling/row as everything else above
    # rather than a separate standalone element, at the user's request
    # ("fully in line with the other pills"). Computed fresh here since
    # this whole block only runs `if weather:` — see pages_recovery for
    # why that's an acceptable tradeoff now that this is the only
    # recovery UI left (no more dedicated rotation page).
    try:
        _recovery_badge = pages_recovery.status_badge_html(now)
    except Exception:
        _recovery_badge = None
    if _recovery_badge:
        extras.append(_recovery_badge)

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

# Page-independent, same reasoning as the leave headline above — the
# morning routine doesn't wait for whichever of the 10 rotating pages
# happens to be up. Below the hero row rather than competing with the
# leave headline for the same prime spot above the clock.
try:
    morning_briefing.render(now, weather, air_quality)
except Exception:
    pass

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
            _safe_render(pages_home.render, FRED_API_KEY, readings, new_flags, _rotation_epoch)
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
    elif page == "household":
        _safe_render(pages_household.render, now)
    elif page == "weather":
        _safe_render(pages_weather.render)
    elif page == "radar":
        _safe_render(pages_radar.render)
    elif page == "sports":
        _safe_render(pages_sports.render)
    elif page == "scores":
        _safe_render(pages_scores.render, _rotation_epoch)
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

# Same bottom-bar queue, same isolation reasoning — a genuinely heavy
# (not just present) precipitation cell newly detected nearby, edge-
# triggered so it fires once per event rather than every rerun while
# it persists (see ec_radar.severe_weather_alert). Falls through to
# news.render_alert_bar below (kind isn't "commute"), reusing its
# existing red/urgent treatment since this alert always sets
# important=True.
try:
    severe_alert = ec_radar.severe_weather_alert(_alert_precip_kind)
    if severe_alert:
        new_alerts.append(severe_alert)
except Exception:
    pass

# Same idea, earlier trigger — the moment radar first has ANYTHING to
# track nearby, regardless of confirmed direction or intensity (see
# ec_radar.tracking_started_alert). Lower-key styling than the severe
# alert above: important=False, so news.render_alert_bar gives it the
# muted black treatment instead of red.
try:
    tracking_alert = ec_radar.tracking_started_alert(_alert_precip_kind)
    if tracking_alert:
        new_alerts.append(tracking_alert)
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
# hours of backlog playing through this bar one at a time. commute_alert/
# severe_alert/tracking_alert above are each appended AFTER new_alerts
# is first populated from news.get_new_alerts(), so they always sit at
# the tail end of the list — this trim (which keeps the most recent
# items) can never drop any of the three even during a real news burst.
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
        # Alternated every render (see the toast-*-anim comment in
        # theme.py) — Streamlit reuses this same bottom-bar DOM node
        # across reruns, and a burst of several alerts in a row would
        # otherwise have every alert after the first reuse the prior
        # one's already-completed animation and just appear instantly,
        # with no intro. A per-rerun toggle always forces a genuine
        # restart, whether this is a new alert or the same one
        # continuing to render.
        st.session_state["_toast_anim_tick"] = st.session_state.get("_toast_anim_tick", 0) + 1
        _toast_variant = "a" if st.session_state["_toast_anim_tick"] % 2 == 0 else "b"
        if current_alert.get("kind") == "commute":
            commute_reminder.render_bar(current_alert, elapsed, _toast_variant)
        else:
            news.render_alert_bar(current_alert, elapsed, _toast_variant)
    else:
        # Earnings dates (a small curated watchlist, see config.
        # EARNINGS_TICKER_WATCHLIST) fold into the same scrolling strip
        # as the macro release calendar rather than getting a section
        # of their own — one more kind of item in something already on
        # screen, not new real estate. Not gated on FRED_API_KEY like
        # the release schedule below — earnings dates come from
        # yfinance, a completely separate source.
        schedule = []
        if FRED_API_KEY and readings:
            schedule.extend(ticker.build_schedule(readings, FRED_API_KEY))
        schedule.extend(ticker.build_earnings_schedule())
        schedule.sort(key=lambda it: it["date"])
        if schedule:
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
    aqi_for_lights = air_quality.get("us_aqi") if air_quality else None
    # Session feedback: waking the bedroom light for weather overnight
    # was the wrong call — sync_lights no longer reacts to weather at
    # all (severe_weather_active/rain_incoming still drive the screen's
    # own separate night_dim override above, just not the light).
    govee_lighting.sync_lights(
        phase, market_intraday_pct, breaking_elapsed, now, weather["sunset"] if weather else None,
        aqi_for_lights, category,
    )
    govee_lighting.sync_plug(now, weather["first_light"] if weather else None, weather["last_light"] if weather else None)
except Exception:
    pass
