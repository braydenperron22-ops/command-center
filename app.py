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
import data_health
import govee_lighting
import market_yf_client
import morning_briefing
import news
import pages_conflicts
import pages_home
import pages_household
import pages_internals
import pages_jumbotron
import pages_markets
import pages_news
import pages_portfolio
import pages_radar
import pages_scores
import pages_sports
import pages_today
import pages_weather
import payday_schedule
import sports_alerts
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
import streamlit.components.v1 as components
from icons import icon_for, label_for
from scenery import FADE_SECONDS, condition_category, phase_for, scene_html, sky_style
import ticker
from weather_client import fetch_weather

st.set_page_config(page_title="Command Center", layout="wide")
theme.inject()

# Kiosk hotkey: press J to pull the jumbotron up on demand, J again to
# hand the screen back to the normal rotation — session request, for
# watching a game outside the automatic takeover window (see
# sports_alerts.takeover_state).
#
# Has to be a components iframe rather than st.markdown: Streamlit
# strips <script> out of unsafe_allow_html entirely, so markdown can't
# run anything. The iframe's own document never has keyboard focus on a
# kiosk (nobody clicks into it), so a listener bound inside it would
# never fire — instead it injects the listener into the PARENT document
# once, where the keystrokes actually land. Injecting a real <script>
# element (rather than binding a closure from in here) also means the
# handler keeps working after Streamlit tears this iframe down and
# rebuilds it, which it does on every 5-second rerun.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-hotkeys')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-hotkeys';
      s.textContent = [
        "document.addEventListener('keydown', function (e) {",
        "  if (e.key !== 'j' && e.key !== 'J') return;",
        "  if (e.metaKey || e.ctrlKey || e.altKey) return;",
        "  var t = e.target;",
        "  if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;",
        "  var url = new URL(window.location.href);",
        "  if (url.searchParams.get('page') === 'jumbotron') {",
        "    url.searchParams.delete('page');",
        "  } else {",
        "    url.searchParams.set('page', 'jumbotron');",
        "  }",
        "  window.location.replace(url.toString());",
        "});",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

# Live countdown ticker — global (not page-scoped) because every timer
# element on this dashboard (the jumbotron's pregame countdown, the
# commute reminder's "leave in" headline, the Sports page's "first
# pitch in" badge) needs the same fix: a server-rendered digit only
# ever updates once per 5s rerun, so it visibly jumps in 5s steps
# instead of actually ticking (session feedback on the jumbotron
# countdown: bring seconds back but "uncorrelated to the sync up of
# the whole system" — then, "make that logic work for all the timer
# elements... specifically the big red leave in timer"). Same
# injected-into-the-parent-document technique as the hotkey listener
# above, same duplicate-guard reasoning. Any page can opt an element in
# just by giving it class="live-countdown" plus:
#   data-target-ms   required — the target instant, real UTC epoch ms
#   data-format       "clock" (H:MM:SS, default) or "words" (e.g. "1h 26m"/"45 min")
#   data-template     optional wrapper with a "{}" placeholder for the ticking token (default "{}")
#   data-zero-text    optional full replacement text once the target's passed (e.g. "Leave now")
# Re-queries .live-countdown fresh every tick rather than caching
# element references, so it keeps finding the right nodes even though
# Streamlit replaces them underneath it on its own 5s cycle.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-countdown-ticker')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-countdown-ticker';
      s.textContent = [
        "function kioskFmtWords(totalSeconds) {",
        "  var totalMinutes = Math.max(0, Math.floor(totalSeconds / 60));",
        "  var hours = Math.floor(totalMinutes / 60);",
        "  var minutes = totalMinutes % 60;",
        "  return hours > 0 ? (hours + 'h ' + minutes + 'm') : (minutes + ' min');",
        "}",
        "function kioskFmtClock(totalSeconds) {",
        "  var total = Math.max(0, Math.round(totalSeconds));",
        "  var h = Math.floor(total / 3600);",
        "  var m = Math.floor((total % 3600) / 60);",
        "  var sec = total % 60;",
        "  if (h > 0) return h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');",
        "  return m + ':' + String(sec).padStart(2, '0');",
        "}",
        "setInterval(function () {",
        "  var now = Date.now();",
        "  document.querySelectorAll('.live-countdown').forEach(function (el) {",
        "    var targetMs = parseInt(el.getAttribute('data-target-ms'), 10);",
        "    if (!targetMs) return;",
        "    var remainingSeconds = (targetMs - now) / 1000;",
        "    var zeroText = el.getAttribute('data-zero-text');",
        "    if (zeroText && remainingSeconds <= 0) {",
        "      el.textContent = zeroText;",
        "      return;",
        "    }",
        "    var format = el.getAttribute('data-format') || 'clock';",
        "    var token = format === 'words' ? kioskFmtWords(remainingSeconds) : kioskFmtClock(remainingSeconds);",
        "    var template = el.getAttribute('data-template') || '{}';",
        "    el.textContent = template.replace('{}', token);",
        "  });",
        "}, 1000);",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

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

# Pinned here rather than further down (where it used to sit, just under
# the autorefresh call) because the jumbotron takeover below has to know
# the local wall-clock time before page routing can be decided at all.
# Hosted deployments (Streamlit Cloud) run on the server's own timezone
# (typically UTC), not North Bay's — pin explicitly rather than trusting
# datetime.now(), then drop tzinfo so it stays comparable with the naive
# sunrise/sunset values Open-Meteo returns for the same zone.
now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)

# Jumbotron takeover — session request: "I want the kiosk to run as
# normal, but one hour before any game Habs or Jays, and during the
# game, I want it to go to that exactly so the game can be enjoyed with
# this system, before reverting back to the other system." The
# jumbotron is deliberately NOT in PAGES (it never joins the rotation);
# this is the only thing that ever selects it, and it releases on its
# own once takeover_state stops returning a phase.
try:
    _takeover = sports_alerts.takeover_state(now)
except Exception:
    _takeover = None

# Manual "End Session" button (pages_jumbotron.render(), bottom-right of
# the board) — session request: "make an end session button... that
# closes out the game session therefore closing the jumbotron which
# turns on the dimming and turns off the govee lights." Suppresses the
# automatic takeover for this specific game_id only (pregame/live/
# postgame all share the same id, so ending it mid-game also skips that
# game's own postgame recap — the point is "I'm done watching," not
# "skip to the next phase"); a different game later, even the same
# team's next one, isn't affected. Nulling _takeover itself here (before
# every routing/dim/light decision below derives from it) means nothing
# downstream needs its own separate check — an explicit ?page=jumbotron
# or the J-hotkey still overrides this and shows the board on demand,
# same as they already do when there's no real takeover at all (see the
# takeover_preview_state() fallback just below).
if _takeover and _takeover["game"]["game_id"] == st.session_state.get("jumbotron_dismissed_game_id"):
    _takeover = None

_requested_page = None
try:
    _requested_page = st.query_params.get("page")
    if _requested_page == "jumbotron":
        # Manual preview from a phone, for a day with no game in its
        # window — falls back to whatever game is nearest so the board
        # can actually be looked at outside a real takeover.
        page = "jumbotron"
        _takeover = _takeover or sports_alerts.takeover_preview_state()
    elif _requested_page in PAGES:
        page = _requested_page
    elif _takeover:
        page = "jumbotron"
    else:
        page, _, _ = _scheduled_page(_rotation_epoch)
except Exception:
    page = "today"

# The jumbotron owns the entire screen: no hero row, no morning
# briefing, no rotation countdown, no pre-game headline (the board has
# its own, much bigger countdown). The leave-for-work headline still
# renders — a game is never a reason to miss a shift — and so do the
# toast queue, ticker and Govee sync.
_jumbotron_active = page == "jumbotron" and _takeover is not None
if not _jumbotron_active and page == "jumbotron":
    # Nothing to show (no game at all, e.g. both leagues in the
    # offseason) — fall back rather than rendering an empty board.
    page, _, _ = _scheduled_page(_rotation_epoch)

# Transition overlay — session feedback: the hard cut between the
# everyday dashboard and the jumbotron "feels dystopian," worth a real
# transition each way. Detected as a genuine flip in _jumbotron_active
# since the last rerun (not "is jumbotron active right now" — that's
# true for the whole ~1hr+ takeover window, this only needs to fire
# once at the actual moment of change), same session-state-diff
# pattern the page-flip crossfade and score-flash animations already
# use elsewhere in this app.
#
# Rendered as a fixed, full-screen, pointer-events:none curtain with a
# CSS animation that holds briefly then fades itself out — not a
# second Streamlit rerun's worth of a blank/loading page. The real
# destination page (jumbotron or the normal dashboard) still renders
# underneath it in this exact same script run, so nothing is skipped
# or delayed; the curtain just politely reveals it a couple seconds
# later instead of cutting instantly. Only exists in the DOM for the
# one rerun where the flip happened — the very next 5s rerun renders
# with no overlay markup at all.
try:
    _prev_jumbotron_active = st.session_state.get("_prev_jumbotron_active", False)
    if _jumbotron_active and not _prev_jumbotron_active:
        _team_label = (_takeover["league"]["label"] if _takeover else "").title()
        st.markdown(
            f'<div class="jumbo-transition jumbo-transition-in">'
            f'<div class="jumbo-transition-brand">FANCAVE<span>JUMBOTRON</span></div>'
            f'<div class="jumbo-transition-sub">GAME MODE · {_team_label}</div></div>',
            unsafe_allow_html=True,
        )
    elif _prev_jumbotron_active and not _jumbotron_active:
        st.markdown(
            '<div class="jumbo-transition jumbo-transition-out">'
            '<div class="jumbo-transition-brand-normal">Command Center</div>'
            '<div class="jumbo-transition-sub-normal">Back to your day</div></div>',
            unsafe_allow_html=True,
        )
    st.session_state["_prev_jumbotron_active"] = _jumbotron_active
except Exception:
    pass

_PAGE_LABELS = {
    "home": "Home", "conflicts": "Conflicts", "news": "News", "markets": "Markets",
    "internals": "Internals", "today": "Today", "household": "Household",
    "weather": "Weather", "radar": "Radar", "sports": "Sports", "scores": "Scores",
    "portfolio": "Portfolio",
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
if _requested_page not in PAGES and not _jumbotron_active:
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

# True during EC's own most dangerous hazard tier (tornado/hurricane/
# tsunami, from its official alert feed) — drives the screen going
# fully bright (not just dimmed less, see night_dim below) rather than
# the light, which no longer reacts to weather at all (session
# feedback: waking the bedroom light overnight was the wrong call).
# Used to also fold in a radar-confirmed heavy-precipitation stint
# (ec_radar.severe_weather_stint_active) — removed along with the rest
# of the radar-based lookahead/severity forecasting at the user's own
# request, judged too inconsistent to trust; EC's own official alert
# feed alone is the reliable half that's left.
try:
    severe_weather_active = weather_alerts_bar.current_severity() == "extreme"
except Exception:
    severe_weather_active = False

# Session request: "make it so the screen cannot turn off if there's a
# live game — after the game is over the setup can sleep," later
# corrected to also hold through the postgame recap (see
# sports_alerts.plug_should_stay_on's own docstring). Reuses _takeover
# — already nulled above by the manual End Session dismiss check — so
# that's the one case this doesn't hold through, same as the request.
try:
    game_live = sports_alerts.plug_should_stay_on(_takeover)
except Exception:
    game_live = False

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
weather_worth_waking_for = severe_weather_active
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

    # Session feedback: "even if it's not dark outside, I want the
    # screen to be dark" for the jumbotron — sky_style paints the
    # daytime sky gradient straight onto stAppViewContainer, which sits
    # behind every page including the jumbotron's own semi-transparent
    # glass panels, washing out the arena-dark look with whatever tint
    # the actual time of day happens to be. Skipped entirely during a
    # takeover rather than overridden with more CSS — the config.toml
    # base theme's own backgroundColor is already solid black, so
    # simply not painting a sky over it gives the jumbotron exactly the
    # always-dark background it wants for free.
    if not _jumbotron_active:
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
    # stays on the full sleep-dim floor no matter how long a stint has
    # been running, which is the whole fix for "this kept me awake."
    # Before quiet hours (still evening, presumably awake anyway), the
    # previous whole-duration behavior still applies: severe weather
    # overrides dimming entirely. Used to also soften dimming for
    # ordinary (non-severe) rain — removed along with the rest of the
    # radar-based precip detection this depended on.
    #
    # A live game does NOT get an exemption here — session correction:
    # "the screen is allowed to dim," the actual ask was keeping the
    # smart plug powering the monitor from cutting out overnight (see
    # govee_lighting.sync_plug's own game_live param), a separate thing
    # from this dim overlay.
    if quiet_hours and not weather_wake_recent:
        night_dim = 1.0
    elif severe_weather_active:
        night_dim = 0.0

    # Session request: "make it so the screen does not dim in game
    # mode" — narrower than (and doesn't reopen) the "any live game"
    # exemption reverted just above: this only kicks in while the
    # jumbotron is actually the thing on screen (the pregame-through-
    # postgame takeover window), not for the whole time some tracked
    # game happens to be live in the background during the normal
    # rotation. Takes final precedence over quiet hours/night too —
    # game mode is for actually watching, not for sleeping through.
    if _jumbotron_active:
        night_dim = 0.0

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


UV_EXTREME = 11  # UV index at which the badge reaches full vibrant red

weather_block = ""
if weather:
    icon_svg = icon_for(category, phase)
    condition_label = label_for(weather["weather_code"])

    hilo_html = ""
    high, low = weather.get("forecast_high_c"), weather.get("forecast_low_c")
    if high is not None and low is not None:
        hilo_html = f' · <span class="weather-hilo">H:{high:.0f}° L:{low:.0f}°</span>'

    # Rain/snow arrival + severity badges (radar-based lookahead
    # forecasting) removed at the user's own request, judged too
    # inconsistent to trust — see ec_radar.py's own module docstring.
    # The Radar page still shows the live map for manual reading.
    extras = []
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
    EVENING_BADGE_HOUR = 18  # 6pm — see the garbage/payday badges just below

    # Garbage/recycling day — used to be its own always-visible tile on
    # the Household page; moved here and gated to "today, or tomorrow
    # once it's evening" (see waste_schedule.next_pickup) so it reads
    # like every other hero badge, something worth a glance right now,
    # not a permanent daily fixture. "Tomorrow" only starts showing at
    # EVENING_BADGE_HOUR — session feedback: seeing "Garbage tomorrow"
    # at 10am is a full day early and just noise, but by evening it's
    # the actionable "bins go out tonight" moment. "Today" still shows
    # any time, since that one's always immediately actionable.
    pickup = waste_schedule.next_pickup(now.date())
    if pickup["days_until"] == 0 or (pickup["days_until"] == 1 and now.hour >= EVENING_BADGE_HOUR):
        when = "today" if pickup["days_until"] == 0 else "tomorrow"
        extras.append(
            f'<span class="weather-extra" style="color:#A2845E; '
            f'background:{_badge_bg("#A2845E", 0.22)}; border-color:#A2845E;">'
            f'{pickup["kind"]} {when}</span>'
        )
    # Payday — same spot and same today/evening-tomorrow gating as the
    # garbage badge right above, not a permanent fixture. Green (the
    # app's existing "good" tone, matching market-up/badge-good) rather
    # than a color already claimed by another badge.
    payday = payday_schedule.next_payday(now.date())
    if payday["days_until"] == 0 or (payday["days_until"] == 1 and now.hour >= EVENING_BADGE_HOUR):
        payday_when = "today" if payday["days_until"] == 0 else "tomorrow"
        extras.append(
            f'<span class="weather-extra" style="color:#32D74B; '
            f'background:{_badge_bg("#32D74B", 0.22)}; border-color:#32D74B;">'
            f'Payday {payday_when}</span>'
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

# Same treatment for the final hour before a Jays/Habs game — session
# request: "First Pitch In, counting down from an hour, similar to the
# get ready to go timers" (see sports_alerts.render_game_countdown).
# Skipped during a takeover: the jumbotron's own board carries a far
# bigger countdown for the exact same game, and two would just compete.
if not _jumbotron_active:
    try:
        sports_alerts.render_game_countdown(now)
    except Exception:
        pass

# The jumbotron brings its own marquee (clock, date, weather), so the
# standard hero row would just be a duplicate stacked above it.
if not _jumbotron_active:
    st.markdown(
        f"""<div class="hero-row">
            <div class="hero-time">
                <div class="clock">{now.strftime('%I:%M %p').lstrip('0')}</div>
                <div class="date-sub">{now.strftime('%A, %B %d')}</div>
            </div>{weather_block}
        </div>""",
        unsafe_allow_html=True,
    )

# Staleness watchdog (session request) — page-independent, same
# reasoning and the same .weather-extra pill styling as the recovery
# badge above. Silent unless a source that has genuinely succeeded at
# least once this session has since gone quiet longer than its own
# threshold (see data_health.py) — never flags a source that simply
# hasn't reported in yet, e.g. right after a fresh redeploy.
try:
    _stale_sources = data_health.check()
except Exception:
    _stale_sources = []
if _stale_sources and not _jumbotron_active:
    _stale_tint = "rgba(255,105,97,0.22)"
    _stale_bg = f"linear-gradient({_stale_tint}, {_stale_tint}), rgba(12,12,16,0.72)"
    _stale_badges = "".join(
        f'<span class="weather-extra" style="color:#FF6961; background:{_stale_bg}; border-color:#FF6961;">'
        f'⚠ {s["label"]}: {s["hours_stale"]:.0f}h stale</span>'
        for s in _stale_sources
    )
    st.markdown(f'<div class="weather-extras">{_stale_badges}</div>', unsafe_allow_html=True)

# Page-independent, same reasoning as the leave headline above — the
# morning routine doesn't wait for whichever of the 10 rotating pages
# happens to be up. Below the hero row rather than competing with the
# leave headline for the same prime spot above the clock. Suppressed
# during a takeover along with the rest of the standard chrome — a
# morning-routine summary has no business on a live scoreboard, and
# takeovers only ever happen at game time anyway.
if not _jumbotron_active:
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


# The bottom ticker's own live indicator-value items are global (useful
# regardless of which page is showing), so macro readings are fetched
# unconditionally — pages_home.py's own tiles reuse this same fetch.
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
    elif page == "jumbotron":
        _safe_render(pages_jumbotron.render, now, _takeover, weather)
    elif page == "sports":
        _safe_render(pages_sports.render)
    elif page == "scores":
        _safe_render(pages_scores.render, _rotation_epoch)
    elif page == "portfolio":
        _safe_render(pages_portfolio.render)
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

# Jays/Habs scoring-play alerts: drops into the same bottom-bar queue
# as breaking news/commute (below) — session request: "every time
# there's an update in a game have a blue headline come through with a
# blue govee flash [...] same with the habs but make it red." Wrapped
# separately from the queue's own try/except, same reasoning as the
# commute block above — a bug here shouldn't take down real breaking-
# news alerts, and this needs to run before that block so a fresh
# scoring play is picked up in this same rerun.
try:
    new_alerts.extend(sports_alerts.get_new_alerts(now))
except Exception:
    pass

# Radar-based severe/tracking-started toast alerts (ec_radar.
# severe_weather_alert / tracking_started_alert) removed along with the
# rest of the radar lookahead-forecasting layer at the user's own
# request — see ec_radar.py's own module docstring.

# News alerts: strictly-filtered items queue up and take over the bottom
# bar (normally the release calendar) for TOAST_SECONDS each, breaking-news
# style, before control returns to the calendar ticker. This happens
# regardless of which page is active.
#
# Session request: when several alerts land at once, priority order is
# "leave in at the top, then Habs, then Jays" — commute first, then NHL
# sports alerts, then MLB, then everything else (news). The sort is
# stable, so scoring plays within one game and chronologically-sorted
# news batches each keep their own internal order.
#
# A feed outage that recovers can surface dozens of headlines in one
# batch (everything that was never marked "seen" while it was down) —
# capped to MAX_BURST_ALERTS so that doesn't turn into hours of backlog
# playing through this bar one at a time. The trim only ever cuts from
# the lowest-priority end (the news tail, oldest first, since news
# arrives sorted oldest->newest) — a commute or sports alert can never
# be squeezed out by a news burst, which the old tail-keeping trim
# quietly stopped guaranteeing for commute the day sports alerts
# started appending after it.
#
# current_alert/elapsed defined here (not just inside the try) so the
# Govee block below always has a real value to check even if this try
# body fails before reaching the assignment further down — it has its
# own try/except too, but there's no reason to make it depend on this
# block's internals for a safe default.
def _alert_priority(alert: dict) -> int:
    if alert.get("kind") == "commute":
        return 0
    if alert.get("kind") == "sports":
        priority = sports_alerts.COUNTDOWN_PRIORITY
        sport = alert.get("sport")
        return 1 + (priority.index(sport) if sport in priority else len(priority))
    return 10


current_alert, elapsed = None, None
try:
    news_queue = st.session_state.setdefault("news_queue", [])
    new_alerts.sort(key=_alert_priority)
    if len(new_alerts) > MAX_BURST_ALERTS:
        overflow = len(new_alerts) - MAX_BURST_ALERTS
        news_only = [a for a in new_alerts if _alert_priority(a) == 10]
        keep_news = news_only[overflow:] if overflow < len(news_only) else []
        new_alerts = [a for a in new_alerts if _alert_priority(a) < 10] + keep_news
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
        elif current_alert.get("kind") == "sports":
            sports_alerts.render_alert_bar(current_alert, elapsed, _toast_variant)
        else:
            news.render_alert_bar(current_alert, elapsed, _toast_variant)
    else:
        # A pure live-stat ticker (session request: "remove the dates
        # for data... just not [as] informational and as good as the
        # other options" — the release-date countdown machinery this
        # used to have is gone entirely, see ticker.py's own module
        # docstring). Each source isolated in its own try so a single
        # one hiccuping (e.g. yfinance briefly unreachable) only drops
        # that one item, not the whole ticker.
        stats = []
        try:
            stats.extend(ticker.build_market_stat_items())
        except Exception:
            pass
        try:
            portfolio_stat = ticker.build_portfolio_stat_item()
            if portfolio_stat:
                stats.append(portfolio_stat)
        except Exception:
            pass
        try:
            stats.extend(ticker.build_sports_stat_items())
        except Exception:
            pass
        try:
            stats.extend(ticker.build_indicator_stat_items(readings))
        except Exception:
            pass
        try:
            stats.extend(ticker.build_internals_stat_items())
        except Exception:
            pass
        try:
            gas_stat = ticker.build_gas_stat_item()
            if gas_stat:
                stats.append(gas_stat)
        except Exception:
            pass
        try:
            aqi_stat = ticker.build_aqi_stat_item()
            if aqi_stat:
                stats.append(aqi_stat)
        except Exception:
            pass

        if stats:
            st.markdown(ticker.render_html(stats), unsafe_allow_html=True)
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
    score_flash = None
    if current_alert and current_alert.get("kind") == "sports" and elapsed is not None and elapsed < govee_lighting.FLASH_SECONDS:
        score_flash = (elapsed, current_alert["flash_color"])
    aqi_for_lights = air_quality.get("us_aqi") if air_quality else None
    # Session feedback: waking the bedroom light for weather overnight
    # was the wrong call — sync_lights no longer reacts to weather at
    # all (severe_weather_active still drives the screen's own separate
    # night_dim override above, just not the light).
    govee_lighting.sync_lights(
        phase, market_intraday_pct, breaking_elapsed, now, weather["sunset"] if weather else None,
        aqi_for_lights, category, score_flash, _jumbotron_active,
    )
    govee_lighting.sync_plug(
        now, weather["first_light"] if weather else None, weather["last_light"] if weather else None, game_live
    )
except Exception:
    pass
