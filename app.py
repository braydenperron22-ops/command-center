"""Personal command-center dashboard: ambient rotation across Home (macro
data), Conflicts, News, Markets, Internals, Today, Household, Weather,
Hourly, Sports, Scores, Portfolio, and Predictions — clock/weather header
stays constant. Jumbotron (sports takeover) and Maintenance (diagnostics)
are real pages too but deliberately excluded from the passive rotation —
see PAGES in config.py and each page's own routing comments below for
how they're reached instead (an automatic takeover / the J and D
hotkeys)."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import air_quality_client
import commute_reminder
import cpp_payment_dates
import data_health
import ec_forecast
import email_client
import evening_briefing
import govee_lighting
import groq_client
import headline_rotation
import holidays_client
import lightning_client
import local_news_client
import market_yf_client
import morning_briefing
import news
import pages_conflicts
import pages_email
import pages_home
import pages_household
import pages_hourly
import pages_internals
import pages_jumbotron
import pages_maintenance
import pages_markets
import pages_news
import pages_portfolio
import pages_predictions
import pages_radar
import pages_scores
import pages_sports
import pages_today
import pages_weather
import payday_schedule
import persisted_state
import precip_nowcast_client
import prediction_markets_client
import road_conditions
import scores_client
import seasons_client
import sports_alerts
import td_quarter_schedule
import theme
import toast_queue
import ufc_client
import waste_schedule
import weather_alerts_bar
import weather_records_client
import wildfire_client
from config import (
    AQI_EXTREME,
    AQI_SHOW_THRESHOLD,
    EXTREME_COLD_THRESHOLD_C,
    EXTREME_HEAT_THRESHOLD_C,
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
from weather_client import daily_forecast, fetch_weather

st.set_page_config(page_title="Command Center", layout="wide")
theme.inject()

# Kiosk hotkeys: press J to pull the jumbotron up on demand, J again to
# hand the screen back to the normal rotation — session request, for
# watching a game outside the automatic takeover window (see
# sports_alerts.takeover_state). Press D the same way for the
# maintenance/diagnostics page (pages_maintenance.py) — session
# request: "add a maintenance tab... on ours by pressing D." Both keys
# share one toggle rule: set ?page= to that page, or clear it if that
# page's already showing.
#
# Press S to open the screen picker (session request: "bind the S key
# to a selection menu where i can pick any of the screens we've built
# so i can look for ideas without needing to sit through the
# rotation") — a separate ?picker=open query param, not ?page=, since
# the picker is an OVERLAY on top of whatever's already showing (the
# auto-rotation or a specific page), not a page swap itself; toggling
# it must never disturb ?page=. The overlay itself (rendered separately
# below, once _PAGE_LABELS exists) closes via plain <a href> links, not
# this same JS function — window.kioskTogglePicker only needs to exist
# for the keyboard path (S to open/close, Escape to close), which has
# no href to navigate to, just the current URL to toggle in place.
# Exposed on the parent window rather than closed over in here so nothing
# else needs its own copy of this toggle logic if it ever needs it too.
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
#
# The delegated click listener inside this same injected script (below,
# on .screen-picker-item/-backdrop/-close) exists because Streamlit's
# own markdown sanitizer force-adds target="_blank" rel="noopener
# noreferrer" to every <a> it renders under unsafe_allow_html —
# confirmed live, even this app's existing mobile-nav links carry it.
# Left alone, every screen-picker click would pop open a brand-new
# browser tab on the kiosk instead of navigating the one it's already
# showing on. preventDefault() stops that default anchor navigation
# before the browser ever acts on target="_blank", then the handler
# navigates in-place itself via the same URL the href already pointed
# to. Delegated on `document` (not bound to the specific elements) so
# it keeps working after Streamlit tears the picker's markup down and
# rebuilds it every 5s rerun, same reasoning as binding keydown on
# `document` above rather than on any one element.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-hotkeys')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-hotkeys';
      s.textContent = [
        "window.kioskTogglePicker = function () {",
        "  var url = new URL(window.location.href);",
        "  if (url.searchParams.get('picker') === 'open') {",
        "    url.searchParams.delete('picker');",
        "  } else {",
        "    url.searchParams.set('picker', 'open');",
        "  }",
        "  window.location.replace(url.toString());",
        "};",
        "document.addEventListener('keydown', function (e) {",
        "  var key = e.key.toLowerCase();",
        "  var t = e.target;",
        "  var typing = t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName);",
        "  if (key === 'escape') {",
        "    var url = new URL(window.location.href);",
        "    if (url.searchParams.get('picker') === 'open') {",
        "      url.searchParams.delete('picker');",
        "      window.location.replace(url.toString());",
        "    }",
        "    return;",
        "  }",
        "  if (e.metaKey || e.ctrlKey || e.altKey || typing) return;",
        "  if (key === 's') {",
        "    window.kioskTogglePicker();",
        "    return;",
        "  }",
        "  var targetPage = key === 'j' ? 'jumbotron' : key === 'd' ? 'maintenance' : null;",
        "  if (!targetPage) return;",
        "  var url = new URL(window.location.href);",
        "  if (url.searchParams.get('page') === targetPage) {",
        "    url.searchParams.delete('page');",
        "  } else {",
        "    url.searchParams.set('page', targetPage);",
        "  }",
        "  window.location.replace(url.toString());",
        "});",
        "document.addEventListener('click', function (e) {",
        "  var link = e.target.closest && e.target.closest('.screen-picker-item, .screen-picker-backdrop, .screen-picker-close');",
        "  if (!link) return;",
        "  e.preventDefault();",
        "  window.location.replace(link.getAttribute('href'));",
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
#   data-intensity    optional — escalating urgency tiers (intensity-calm through intensity-overdue,
#                     see theme.py's .leave-headline rules) toggled on the closest .leave-headline
#                     ancestor. Session request: "make the leave in timer chill and it progressively
#                     gets more intense... the closer we are to the leave time." Only elements that
#                     set this attribute are touched — the jumbotron/sports countdowns sharing this
#                     same ticker don't set it, so they're unaffected.
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
        // Session report: "four games that are more than a full day
        // away... the saints game shows like two hundred and twenty
        // two hours, which is ridiculous... just make it show days and
        // hours." Mirrors pages_jumbotron._fmt_countdown's own fix —
        // that function only ever drives the first frame, this drives
        // every frame after, so both need the same 24h cutover or the
        // display would flip from correct to wrong one second in.
        "  if (total >= 86400) {",
        "    var days = Math.floor(total / 86400);",
        "    var hrs = Math.floor((total % 86400) / 3600);",
        "    return days + 'd ' + hrs + 'h';",
        "  }",
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
        "    if (el.hasAttribute('data-intensity')) {",
        "      var wrapper = el.closest('.leave-headline') || el;",
        "      var tier = 'calm';",
        "      if (remainingSeconds <= 0) tier = 'overdue';",
        "      else if (remainingSeconds <= 600) tier = 'critical';",
        "      else if (remainingSeconds <= 1800) tier = 'urgent';",
        "      else if (remainingSeconds <= 3600) tier = 'aware';",
        "      ['calm', 'aware', 'urgent', 'critical', 'overdue'].forEach(function (t) {",
        "        wrapper.classList.remove('intensity-' + t);",
        "      });",
        "      wrapper.classList.add('intensity-' + tier);",
        "    }",
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

# Radar page frame animation (pages_radar.py/radar_client.py) — session
# request: "make the radar nice and big... reinstate the radar page."
# Every real radar frame is a genuine, already-loaded <img> stacked
# full-bleed on the others (see .weather-radar-frame-img, theme.py);
# this just toggles which one is opacity:1 on a timer, so "animating"
# never re-fetches anything or touches Streamlit's own rerun cycle at
# all. Same inject-into-the-parent-document/duplicate-guard shape as
# every other kiosk-* script here — survives Streamlit tearing this
# components.html iframe down and rebuilding it every 5s rerun, and
# simply does nothing on any other page (no .weather-radar-frame-img
# elements to find there).
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-radar-anim')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-radar-anim';
      s.textContent = [
        "var kioskRadarIndex = 0;",
        "var kioskRadarHoldTicks = 0;",
        // Real radar cadence is 10 minutes for FRAME_COUNT frames
        // (radar_client.py) — this is purely the on-screen playback
        // speed, unrelated to that. HOLD_TICKS pauses a beat on the
        // most recent frame before looping, so "now" actually reads
        // as the current moment instead of blending straight back
        // into the oldest frame.
        "var KIOSK_RADAR_FRAME_MS = 500;",
        "var KIOSK_RADAR_HOLD_TICKS = 3;",
        "setInterval(function () {",
        "  var frames = document.querySelectorAll('.weather-radar-frame-img');",
        "  if (!frames.length) { kioskRadarIndex = 0; kioskRadarHoldTicks = 0; return; }",
        "  if (kioskRadarIndex >= frames.length) kioskRadarIndex = 0;",
        // Session request: "does RainViewer offer timestamps... it's
        // hard to tell when each frame is." Each frame already carries
        // its own real time as data-time-label (radar_client.py/
        // pages_radar.py) — read straight off whichever frame this
        // tick is actually making visible, so the label can never
        // drift out of sync with the animation the way a separately-
        // ticking clock could.
        "  var label = document.getElementById('weather-radar-timestamp');",
        "  for (var i = 0; i < frames.length; i++) {",
        "    var active = (i === kioskRadarIndex);",
        "    frames[i].style.opacity = active ? '1' : '0';",
        "    if (active && label) { label.textContent = frames[i].getAttribute('data-time-label') || ''; }",
        "  }",
        "  if (kioskRadarIndex === frames.length - 1 && kioskRadarHoldTicks < KIOSK_RADAR_HOLD_TICKS) {",
        "    kioskRadarHoldTicks++;",
        "    return;",
        "  }",
        "  kioskRadarHoldTicks = 0;",
        "  kioskRadarIndex = (kioskRadarIndex + 1) % frames.length;",
        "}, KIOSK_RADAR_FRAME_MS);",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

# Radar frame dynamic sizing — session request: "makes the radar much,
# much, much bigger... you should be able to see it all." A static CSS
# vh budget (theme.py's own .weather-radar-frame-large, several rounds
# of live-tested history on that class's own comment) kept running into
# the same wall no matter how it was tuned: the header above this tile
# isn't a fixed height — it grows and shrinks with the morning-briefing
# sentence's real length, an active weather alert, how many hero badges
# are flagged right now — so any single static value is either too
# small on the header's short days or overlapping the fixed bottom
# ticker on its long ones. Confirmed live across several real reruns:
# the SAME 60vh value measured comfortably clear of the header in one
# check and 75px into the ticker in another, just from the header's own
# content changing between them, nothing to do with viewport size.
#
# Measuring the real remaining space at runtime instead, the same way
# this app already does for the live-countdown ticker/toast dedup
# above — the one thing a static injected stylesheet genuinely can't
# do (this file has said as much in theme.py's own comments for a
# while) but a persistent script can. RADAR_OVERHEAD_PX is the tile's
# own non-frame chrome (padding + credit line + the gap under the
# frame) — near-constant regardless of the frame's own current size,
# so it only needs measuring once per tick, not solved for.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-radar-size')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-radar-size';
      s.textContent = [
        "var KIOSK_RADAR_MIN_PX = 150;",
        "var KIOSK_RADAR_SAFETY_PX = 20;",
        "function kioskSizeRadar() {",
        "  var tile = document.querySelector('.weather-radar-tile-large');",
        "  var frame = document.querySelector('.weather-radar-frame-large');",
        "  if (!tile || !frame) return;",
        "  var tickerTop = window.innerHeight;",
        "  var tickers = document.querySelectorAll('.ticker-bar');",
        "  for (var i = 0; i < tickers.length; i++) {",
        "    var tb = tickers[i].getBoundingClientRect();",
        "    if (tb.height > 0 && tb.top < tickerTop) tickerTop = tb.top;",
        "  }",
        "  var tileTop = tile.getBoundingClientRect().top;",
        "  var overhead = tile.offsetHeight - frame.offsetHeight;",
        "  var available = tickerTop - tileTop - overhead - KIOSK_RADAR_SAFETY_PX;",
        "  var maxWidth = window.innerWidth * 0.9;",
        "  var size = Math.max(KIOSK_RADAR_MIN_PX, Math.min(available, maxWidth));",
        "  frame.style.width = size + 'px';",
        "}",
        "setInterval(kioskSizeRadar, 1000);",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

# Jumbotron win-probability bar (pages_jumbotron._win_probability_html)
# — session request: "can you make the win probability bar update
# smoother instead of jumping." theme.py's own .jumbo-wp-seg already
# carries `transition: width 1s ease`, but that alone can't animate
# anything here: Streamlit re-renders the whole markdown block from
# scratch every rerun, so each .jumbo-wp-seg is a brand new DOM node
# every time with the new width already baked into its inline style —
# not an existing element whose width property just changed, which is
# the only thing a CSS transition can actually animate. Tracked by
# data-wp-key (stable per game+side — the DOM node itself isn't) in a
# plain JS object that survives the churn the same way the countdown
# ticker's own state does, so a genuine change gets a real old->new
# animation: snap instantly back to the last real percentage (no
# transition), force a reflow, then let the CSS transition carry it
# forward to the new one. A first sighting or an unchanged percentage
# just sets the width directly, no animation to fake.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-wp-smoother')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-wp-smoother';
      s.textContent = [
        "window.kioskWpState = window.kioskWpState || {};",
        "function kioskSmoothWp(el) {",
        "  var key = el.getAttribute('data-wp-key');",
        "  var newPct = parseFloat(el.getAttribute('data-wp-pct'));",
        "  if (!key || isNaN(newPct)) return;",
        "  var lastPct = window.kioskWpState[key];",
        "  if (lastPct === undefined || lastPct === newPct) {",
        "    el.style.transition = 'none';",
        "    el.style.width = newPct + '%';",
        "  } else {",
        "    el.style.transition = 'none';",
        "    el.style.width = lastPct + '%';",
        "    void el.offsetHeight;",
        "    el.style.transition = '';",
        "    el.style.width = newPct + '%';",
        "  }",
        "  window.kioskWpState[key] = newPct;",
        "}",
        "function kioskSmoothWpAll() {",
        "  document.querySelectorAll('.jumbo-wp-seg').forEach(kioskSmoothWp);",
        "}",
        "kioskSmoothWpAll();",
        "new MutationObserver(kioskSmoothWpAll).observe(document.body, {childList: true, subtree: true});",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

# Session request: "how can we improve the experience watching the game
# on the jumbotron... everything to feel good and seamless and like
# its all orchestrated" — a general-purpose version of the win-
# probability smoother just above, for every OTHER jumbotron element
# that currently just pops to its new value/state on each rerun (same
# root cause: Streamlit re-renders the whole markdown block from
# scratch, so there's never an existing DOM node for a CSS transition
# to animate from). Any element opts in with two data attributes —
# data-fade-slot (a stable logical identity for "this one spot," e.g.
# "matchup-batter" or "lineup-current-Blue Jays" — NOT the DOM node,
# which is new every time) and data-fade-value (whatever value means
# "this is genuinely the same thing as last rerun" — a player id, a
# play description, an inning+half string) — rather than each feature
# needing its own bespoke smoother script the way the win-probability
# bar has. A first sighting of a slot, or an unchanged value, sets
# nothing (already rendered correctly, nothing to animate); a genuine
# change snaps opacity to 0, forces a reflow, then transitions to 1 —
# same reflow-then-transition trick as kiosk-wp-smoother, opacity
# instead of width since these are appear/replace moments, not a
# continuous bar. 0.45s cubic-bezier(.2,.8,.2,1) matches this board's
# own existing card fade-in convention (.jumbo-around-fade-a/-b in
# theme.py) rather than introducing a new easing feel.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-jumbo-fade')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-jumbo-fade';
      s.textContent = [
        "window.kioskFadeState = window.kioskFadeState || {};",
        "function kioskApplyFadeIn(el) {",
        "  var slot = el.getAttribute('data-fade-slot');",
        "  var value = el.getAttribute('data-fade-value');",
        "  if (!slot || value === null) return;",
        "  var last = window.kioskFadeState[slot];",
        "  if (last === undefined) {",
        "    window.kioskFadeState[slot] = value;",
        "    return;",
        "  }",
        "  if (last !== value) {",
        "    window.kioskFadeState[slot] = value;",
        "    el.style.transition = 'none';",
        "    el.style.opacity = '0';",
        "    void el.offsetHeight;",
        "    el.style.transition = 'opacity 0.45s cubic-bezier(.2,.8,.2,1)';",
        "    el.style.opacity = '1';",
        "  }",
        "}",
        "function kioskApplyFadeInAll() {",
        "  document.querySelectorAll('[data-fade-slot]').forEach(kioskApplyFadeIn);",
        "}",
        "kioskApplyFadeInAll();",
        "new MutationObserver(kioskApplyFadeInAll).observe(document.body, {childList: true, subtree: true});",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

# Session request: "make it so all the red headlines within the last 2
# hours cycle at the top of the screen with a cool animation when it
# swaps" (headline_rotation.py) — same reflow-then-restart-animation
# trick as kiosk-jumbo-fade just above, toggling a CSS class
# (.rotation-swap-in, theme.py) instead of directly manipulating
# opacity, since the swap-in keyframe needs to coexist with the
# critical tier's own separate continuous pulse animation rather than
# replace it (see theme.py's own comment on why that rules out setting
# el.style.animation directly). Only ever one .headline-rotation
# element on the page at a time, so this tracks a single last-seen
# value rather than kiosk-jumbo-fade's per-slot map.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-headline-rotation-swap')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-headline-rotation-swap';
      s.textContent = [
        "window.kioskHeadlineRotationValue = undefined;",
        "function kioskApplyHeadlineRotationSwap() {",
        "  var el = document.querySelector('.headline-rotation');",
        "  if (!el) { window.kioskHeadlineRotationValue = undefined; return; }",
        "  var value = el.getAttribute('data-rotate-value');",
        "  var last = window.kioskHeadlineRotationValue;",
        "  if (last === undefined) {",
        "    window.kioskHeadlineRotationValue = value;",
        "    return;",
        "  }",
        "  if (last !== value) {",
        "    window.kioskHeadlineRotationValue = value;",
        "    el.classList.remove('rotation-swap-in');",
        "    void el.offsetHeight;",
        "    el.classList.add('rotation-swap-in');",
        "  }",
        "}",
        "kioskApplyHeadlineRotationSwap();",
        "new MutationObserver(kioskApplyHeadlineRotationSwap).observe(document.body, {childList: true, subtree: true});",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

# Connection watchdog — session report: "why is my dashboard stuck at
# 12:48pm" while the real time was 7:29pm, ~7 hours stale. Confirmed
# not a code bug: a fresh instance of the exact same deployed code
# ticked correctly, every requests.get/post call in this app already
# has an explicit timeout, and a plain browser refresh fixed it
# instantly — meaning the Python process itself was fine the whole
# time, but this kiosk's own long-lived browser tab had silently lost
# its Streamlit WebSocket connection and never reconnected on its own.
# st_autorefresh (above) can't rescue this: its own rerun trigger rides
# that exact same connection, so once it's dead, the "every 5s" tick
# just stops firing right along with everything else, with nothing on
# screen ever indicating it. This is a plain browser-level timer,
# deliberately NOT going through Streamlit/the WebSocket at all — a
# full hard reload re-establishes a genuinely fresh connection from
# scratch, so even a silent, otherwise-invisible disconnect can never
# leave the kiosk frozen for more than one interval.
#
# Interval briefly tightened to 5 minutes the same evening, after a
# second, related incident: a live game staying stuck on stale pregame
# data ("the game has started but the jumbotron hasnt picked it up")
# that only resolved once a completely separate browser session loaded
# the app. But a reload is a real, visible event on a kiosk (a brief
# flash, any in-progress animation resetting) — 5 minutes traded away
# too much of that for not enough benefit, and turned into its own
# complaint: "why does the board refresh so often." Settled back at 60
# minutes: "an hour, if the board tenses up itll be fixed within the
# hour is good" — an occasional rare safety net, not something meant
# to be regularly visible.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-reload-watchdog')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-reload-watchdog';
      s.textContent = [
        "setInterval(function () {",
        "  window.parent.location.reload();",
        "}, 60 * 60 * 1000);",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

# Bottom ticker — session report: "this dashboard is really heavy...
# the bottom bar[ is] a little janky on the old laptop." Same root
# cause class as the win-probability bar above (a plain markdown re-emit
# recreating the DOM node every rerun, restarting whatever animation it
# carries). A twin fix used to sit right above this one for the live
# radar loop GIF — removed along with the whole Radar page at the
# user's own request ("get rid of radar and replace it with hourly
# weather data"), taking its own now-dead persistence script with it.
# ticker.render_html() is one plain st.markdown call, so Streamlit replaces
# its whole .ticker-bar > .ticker-track > .ticker-content tree from
# scratch on every ~5s rerun — and .ticker-track carries a 55-second
# CSS scroll animation (animation: ticker-scroll, theme.py), which a
# browser always restarts from 0% the instant a NEW element gets that
# animation, even with identical content. The scroll never got more
# than a few seconds into its own 55s cycle before snapping back to
# the start — on a fast machine that reads as a barely-perceptible
# stutter; on weaker hardware, forcing that same restart (a style
# recalc across dozens of ticker-item spans, easily 40+ once every
# live stat source is duplicated for the seamless loop) is real,
# regular jank.
#
# Same fix shape as the radar loop: a persistent .ticker-bar clone
# living as a direct child of <body>, entirely outside Streamlit's own
# churn, so its .ticker-track element is never recreated and its
# animation just keeps running uninterrupted. Only .ticker-track's
# innerHTML gets resynced (and only when it's actually changed — a
# real stat ticking, not every 5s regardless), never the track element
# itself; .ticker-bar's own CSS is already position:fixed with no
# dependency on where it sits in the DOM, so — unlike the radar frame —
# this doesn't need any manual position-tracking against the (now-
# hidden) real one.
#
# Bug found from a session report ("what happened to my toast alerts?
# and my bottom bar"): the clone keeps class="ticker-bar" (only its id
# differs), so the very first time the REAL ticker-bar goes away for a
# real reason — a news/weather/sports toast or the jumbotron leave-
# ticker taking over this same slot, both of which skip calling
# ticker.render_html() entirely for that rerun — the plain
# `document.querySelector('.ticker-bar')` below matched the PERSISTENT
# CLONE ITSELF instead of finding nothing. That aliased `real` to the
# clone, and the final `real.style.display = 'none'` line hid the
# clone permanently — nothing else in this script ever un-hides it, so
# once any toast fired even once, the ticker was gone for the rest of
# the session, reload required. `:not(#kiosk-ticker-persistent)`
# excludes the clone from that lookup so a genuinely-absent real ticker
# correctly falls into the `if (!real)` branch instead.
#
# Second bug, found the same session, reproduced live on a real page
# (internals): the clone can inherit a stale `display:none` at the
# exact moment it's cloned — a real timing window right at a toast-to-
# ticker transition (real gets hidden as the toast begins, and if the
# very next real ticker-bar Streamlit creates once the toast clears
# happens to still carry that same stale inline style at the instant
# this observer callback catches it and clones it, `persistent`
# permanently inherits `display:none` too, with nothing else in this
# script ever explicitly un-hiding it afterward — confirmed live: manually
# forcing `persistent.style.display = 'block'` fixed it permanently, proving
# nothing was actively re-hiding it, it just had no path back to visible on
# its own). `persistent.style.display = ''` right after cloning clears
# any inherited inline override unconditionally, so the clone always
# starts from a clean, CSS-default (visible) state regardless of
# whatever `real` happened to look like at the exact clone moment.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-ticker-persist')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-ticker-persist';
      s.textContent = [
        // THE root cause of the recurring "bottom bar goes blank, no
        // toast appears" reports (news/commute/sports/weather toasts
        // all share this one bug, all at this one call site): the
        // ticker, the news/commute/sports/weather toast bars, and
        // .jumbo-leave-ticker are mutually exclusive branches of ONE
        // if/elif/else in app.py, so they all render at the exact same
        // script position every rerun. Streamlit reuses the SAME
        // underlying DOM node across reruns for that one position
        // (confirmed live via a MutationObserver logging the node's own
        // class flipping between 'ticker-bar' and 'news-alert-bar-
        // market' rerun to rerun, not a fresh node each time) and only
        // patches the attributes ITS OWN markup actually specifies —
        // an inline style we set directly via plain DOM API (not
        // through Streamlit) is invisible to that diffing and never
        // gets cleared just because the next rerun's HTML string omits
        // a style attribute entirely.
        // `real.style.display = 'none'` below (a previous fix, hiding
        // Streamlit's own ticker-bar while its animation-safe clone
        // shows instead) sets exactly that kind of inline style. The
        // very next time a real news/commute/sports/weather alert
        // takes over this same slot, it lands on that same DOM node —
        // now carrying class='news-alert-bar-market' (or whichever
        // toast fired) but STILL with the stale display:none inline
        // style from when it was last a hidden ticker-bar. Confirmed
        // live: the toast's own markup, its CSS class's rules, and
        // app.py's dispatch logic were all completely correct — the
        // element existed in the DOM the whole time, just invisible.
        // None of these toast classes are EVER intentionally hidden by
        // anything else in this app, so unconditionally clearing a
        // stale inline display:none the instant one appears on any of
        // them is always safe.
        "var TOAST_SEL = '.news-alert-bar, .news-alert-bar-market, .commute-alert-bar, " +
          ".sports-alert-bar-mlb, .sports-alert-bar-nhl, .sports-alert-bar-nfl, " +
          ".weather-alert-bar-extreme, .weather-alert-bar-warning, .weather-alert-bar-warning-moderate, " +
          ".weather-alert-bar-watch, .weather-alert-bar-statement, .jumbo-leave-ticker';",
        "function kioskUnhideStaleToast() {",
        "  var toastEl = document.querySelector(TOAST_SEL);",
        "  if (toastEl && toastEl.style.display === 'none') {",
        "    toastEl.style.display = '';",
        "  }",
        "}",
        "function kioskPersistTicker() {",
        "  kioskUnhideStaleToast();",
        "  var real = document.querySelector('.ticker-bar:not(#kiosk-ticker-persistent)');",
        "  var persistent = document.getElementById('kiosk-ticker-persistent');",
        "  if (!real) {",
        "    if (persistent) persistent.remove();",
        "    return;",
        "  }",
        "  if (!persistent) {",
        "    persistent = real.cloneNode(true);",
        "    persistent.id = 'kiosk-ticker-persistent';",
        "    persistent.style.display = '';",
        "    document.body.appendChild(persistent);",
        "  }",
        "  var realTrack = real.querySelector('.ticker-track');",
        "  var persistentTrack = persistent.querySelector('.ticker-track');",
        "  if (realTrack && persistentTrack && persistentTrack.innerHTML !== realTrack.innerHTML) {",
        "    persistentTrack.innerHTML = realTrack.innerHTML;",
        "  }",
        "  real.style.display = 'none';",
        "}",
        "kioskPersistTicker();",
        "new MutationObserver(kioskPersistTicker).observe(document.body, {childList: true, subtree: true});",
      ].join('\\n');
      doc.head.appendChild(s);
    })();
    </script>
    """,
    height=0,
)

# Toast chime + client-side reveal overlay — session request: "add
# chimes for important news or severe weather alerts or leave in
# notifications... without needing an autoclicker to keep the screen
# engaged. Also add client side animations for the toast bar because we
# had to get rid of them because they were causing complications."
#
# The original toast-bar animation (news.render_alert_bar's own
# docstring has the full story) stretched a label into view via a CSS
# animation whose own timing was recomputed from `elapsed` every 5s
# Streamlit rerun — real complexity purpose-built around exact
# assumptions of how Streamlit patches this element, and it broke:
# "I'm still not getting any Toast alerts... it might be running in a
# refresh window... causing it to instantly die." Removed entirely
# rather than fixed at the time. This is a genuinely different design,
# not a repeat of that one: the toast bar itself renders in its final
# state immediately, same as it does today, with zero Streamlit-timed
# animation state of its own to ever get stuck in. Everything below —
# the chime and the reveal — is a client-side script watching the
# ALREADY-persisted toast slot (kioskPersistTicker/TOAST_SEL above) via
# the same MutationObserver pattern, entirely independent of Streamlit's
# own rerun cadence: it fires once, the moment this script's own DOM
# read notices genuinely new toast content (not on every 5s rerun that
# just re-renders the SAME still-active toast), and its animation is a
# fixed-duration CSS transition set once in JS, never recomputed against
# `elapsed` the way the old one was.
#
# Chime-worthy is a deliberate subset, not every toast this app fires:
# "important news" -> real breaking news only (.news-alert-bar), not
# routine .news-alert-bar-market; "severe weather" -> the genuinely
# severe tiers (extreme/warning), not every advisory-level watch/
# statement; "leave in notifications" -> the commute alert and the
# jumbotron's own leave-ticker. Two loudness tiers (a 3-note chime for
# the most urgent bracket, a softer 2-note one for the rest) rather
# than one flat sound for everything.
#
# Audio autoplay: browsers block JS-triggered sound without a prior user
# gesture on that page — this script still calls play() the instant a
# real chime-worthy toast appears, but on a kiosk that's never clicked
# at all, the browser may keep the AudioContext silently suspended
# forever with no error surfaced here. That's a real, one-time browser
# setting to fix (chrome://settings/content/sound -> add this
# dashboard's own URL to "Allowed to play sound," or launch the kiosk
# browser itself with --autoplay-policy=no-user-gesture-required) — not
# something any script running inside the page can grant itself, and
# not the same thing as an autoclicker: a one-time setting survives
# every future reboot/reload on its own, nothing has to keep running.
components.html(
    """
    <script>
    (function () {
      var doc = window.parent.document;
      if (doc.getElementById('kiosk-toast-chime')) return;
      var s = doc.createElement('script');
      s.id = 'kiosk-toast-chime';
      s.textContent = [
        "var KIOSK_CHIME_URGENT_SEL = '.news-alert-bar';",
        "var KIOSK_CHIME_GENTLE_SEL = '.jumbo-leave-ticker';",
        // Session follow-up to the Aaron work: "can we improve the sound
        // design with the same intention we did with aaron" — scoped (by
        // the user's own answer) to just the one-shot "leave in" toast,
        // not the persistent .jumbo-leave-ticker: that element's own
        // .live-countdown child rewrites its text every second (see the
        // kiosk-countdown-ticker script above), so fingerprinting it by
        // textContent the way kioskCheckToastChime does for every other
        // toast would re-chime once a second for as long as it's on
        // screen — confirmed live (6 chimes in 5 seconds) before this
        // was scoped away from it. .commute-alert-bar's own headline is
        // plain static text set once per toast (commute_reminder.
        // render_bar), so it doesn't have that problem.
        "var KIOSK_LEAVE_VOICE_SEL = '.commute-alert-bar';",
        // Session request, after clicking through a set of options built
        // for this exact purpose: "low bell + AARON for sure." Weather
        // alerts get their own treatment instead of the generic 3-note
        // urgent chime: the single low "gloomy ping" plus a real spoken
        // announcement naming the actual hazard, not a canned recording —
        // the whole point of doing this with SpeechSynthesisUtterance
        // instead of a fixed audio file is that "or whatever the
        // situation is" just works, straight off the real toast's own
        // headline text, with no new recording needed for the next
        // hazard type EC ever adds.
        //
        // Follow-up session request: "make a voiceline for each type of
        // special weather statement that exists" — originally only
        // extreme/warning were in this tier (watch/statement/moderate-
        // warning toasts got no audio at all, a real coverage gap).
        // Every weather severity theme.py defines a .weather-alert-bar-*
        // color for is included now; kioskPlayWeatherAlert itself reads
        // which one off the element's own class list to pick a tier-
        // appropriate spoken lead-in (a Special Weather Statement
        // shouldn't open with the same "This is an alert" urgency as a
        // Tornado Warning even though both read the full EC bulletin).
        "var KIOSK_WEATHER_VOICE_SEL = '.weather-alert-bar-extreme, .weather-alert-bar-warning, .weather-alert-bar-warning-moderate, .weather-alert-bar-watch, .weather-alert-bar-statement';",
        // Session request: "add the scoring play for the Habs, Jays and
        // Saints [voice]" — sports toasts (sports_alerts.render_alert_bar)
        // used to match none of the selectors above at all, the one
        // alert kind in the whole toast queue with zero audio. Own tier
        // between commute and the generic chime fallback: a distinct
        // earcon plus a real spoken line when one's set (only "score"/
        // "final" alerts carry one — see sports_alerts.get_new_alerts's
        // own comments on why), same shape KIOSK_LEAVE_VOICE_SEL already
        // uses. bar_class is built per-sport (sports-alert-bar-mlb/nhl/
        // nfl), so this lists all three rather than one shared class.
        "var KIOSK_SPORTS_VOICE_SEL = '.sports-alert-bar-mlb, .sports-alert-bar-nhl, .sports-alert-bar-nfl';",
        // Session request: "incorporate emails... important emails to
        // be sent to me via a toast alert." Reuses the plain gentle
        // chime below (kioskPlayChime(false)) rather than its own
        // earcon — no spoken line either, deliberately: reading a
        // stranger's-eye-view of personal email content out loud in a
        // shared room is a real privacy step up from "a toast appeared
        // on screen," not something this was asked for.
        "var KIOSK_EMAIL_CHIME_SEL = '.email-alert-bar';",
        "var kioskLastChimeKey = null;",
        // Session request: "make it so the audio alerts are dynamic based
        // on time of day starting quiet and dynamically getting louder
        // during mid day then dropping off to complete silence during
        // the 10pm to 5am window with the exception of severe weather as
        // that can sound at a moderate frequency overnight." Returns a
        // 0..1 multiplier read off the KIOSK's OWN clock (not the
        // server's — this is client-side so a kiosk sitting in the
        // user's own room is already on the right local time without
        // needing the Python side's TIMEZONE constant threaded through).
        //
        // Session follow-up #1: "make the adjusted sound system based on
        // time a little more strict, its currently almost 7 and my
        // alert jumpscared me." The original curve was a single
        // symmetric sine hump spanning the WHOLE 5am-10pm day window
        // (peak at 1:30pm, decaying all the way back down across the
        // following 8.5 hours) — confirmed by hand, that put ~7pm at
        // roughly 0.67, still two-thirds of full volume.
        //
        // Session follow-up #2: "it should slowly drop down and hit
        // silence... and ramp back up in the morning... in a straight
        // line increase decrease." Replaced the sine easing (and its
        // 0.3 quiet floor) with a plain linear triangle wave: 0 right
        // at 5am, climbing in a straight line to 1.0 at 1:30pm, then
        // back down in a straight line to 0 right at 10pm — the day
        // curve itself now reaches true silence exactly at the night
        // boundary instead of arriving at a 0.3 floor and then hard-
        // cutting, so the transition into night is seamless rather than
        // a drop.
        //
        // Session follow-up #3: "severe weather should ring at 100%
        // during the day regardless of time and 50% at night regardless
        // of time." Severe weather stopped following the ramp — a flat
        // step function instead, same isNight boundary (10pm-5am)
        // everything else uses, two fixed levels instead of a
        // continuous curve.
        //
        // Session follow-up #4, live at 5am: "make it ramp up slower.
        // It's five AM... its keeping me up." That flat step jumped
        // straight from 0.5 to 1.0 the instant the clock hit 5am — the
        // exact moment someone's still asleep, the worst possible time
        // for an abrupt doubling in volume. Now a short linear ramp
        // (5am-8am) carries it from the night's own 0.5 up to the day's
        // 1.0 gradually instead of snapping — continuous at both ends
        // (0.5 at 4:59am, 0.5 again at 5:00am, reaching 1.0 by 8am),
        // so the moment the night cutoff ends is never itself the
        // loudest possible jump. Full 1.0 holds flat from 8am to 10pm
        // same as before; only the first 3 morning hours changed.
        "function kioskAlertVolume(severe) {",
        "  var d = new Date();",
        "  var hour = d.getHours() + d.getMinutes() / 60;",
        "  var isNight = hour >= 22 || hour < 5;",
        "  if (severe) {",
        "    if (isNight) { return 0.5; }",
        "    var morningRampEnd = 8;",
        "    if (hour < morningRampEnd) { return 0.5 + 0.5 * (hour - 5) / (morningRampEnd - 5); }",
        "    return 1;",
        "  }",
        "  if (isNight) { return 0; }",
        "  var dayStart = 5, peak = 13.5, dayEnd = 22;",
        "  if (hour <= peak) { return (hour - dayStart) / (peak - dayStart); }",
        "  return 1 - (hour - peak) / (dayEnd - peak);",
        "}",
        // Session feedback on the plain-sine chimes above: "not quite my
        // tempo... restart from scratch... this is kinda bad." Rebuilt on
        // FM synthesis instead of stacked sine harmonics (a real, tested
        // pass — see the audio audit artifact this came from for the
        // side-by-side comparisons) — a modulator oscillator sweeps the
        // carrier's own pitch, and how far it sweeps decays across the
        // note, the same real mechanism behind genuine bell/glass system
        // sounds (why a struck bell simplifies from metallic to pure as
        // it rings down, not just fades at one flat timbre). A small
        // synthesized reverb (no sample file — a short burst of filtered
        // noise decaying exponentially, through a ConvolverNode) gives it
        // real space instead of sitting dry. Shared by kioskPlayChime,
        // kioskPlayWeatherAlert's storm tone, and kioskPlaySportsVoice's
        // earcon below — one voice, reused everywhere a tone plays.
        "function kioskMakeReverbImpulse(c, duration, decay) {",
        "  var rate = c.sampleRate;",
        "  var length = Math.floor(rate * duration);",
        "  var impulse = c.createBuffer(2, length, rate);",
        "  for (var ch = 0; ch < 2; ch++) {",
        "    var data = impulse.getChannelData(ch);",
        "    for (var i = 0; i < length; i++) { data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, decay); }",
        "  }",
        "  return impulse;",
        "}",
        "function kioskGetReverb(c) {",
        "  if (!window.__kioskReverbNode) {",
        "    var convolver = c.createConvolver();",
        "    convolver.buffer = kioskMakeReverbImpulse(c, 1.7, 2.4);",
        "    convolver.connect(c.destination);",
        "    window.__kioskReverbNode = convolver;",
        "  }",
        "  return window.__kioskReverbNode;",
        "}",
        // carrierFreq: fundamental Hz. opts: {time, gain, duration, wet,
        // brightness, modRatio, modIndex}. A non-integer modRatio (2.8,
        // 3.9, ...) is what reads as metal rather than a plain harmonic
        // pad — integer ratios collapse back into an ordinary overtone
        // series.
        "function kioskPlayFMBell(c, carrierFreq, opts) {",
        "  opts = opts || {};",
        "  var t0 = opts.time !== undefined ? opts.time : c.currentTime;",
        "  var duration = opts.duration || 1.1;",
        "  var modRatio = opts.modRatio !== undefined ? opts.modRatio : 3.43;",
        "  var modIndex = opts.modIndex !== undefined ? opts.modIndex : 3.2;",
        "  var gainMul = opts.gain !== undefined ? opts.gain : 0.6;",
        "  var carrier = c.createOscillator();",
        "  carrier.type = 'sine'; carrier.frequency.value = carrierFreq;",
        "  var modulator = c.createOscillator();",
        "  modulator.type = 'sine'; modulator.frequency.value = carrierFreq * modRatio;",
        "  var modGain = c.createGain();",
        "  modGain.gain.setValueAtTime(carrierFreq * modIndex, t0);",
        "  modGain.gain.exponentialRampToValueAtTime(Math.max(carrierFreq * 0.03, 1), t0 + duration * 0.85);",
        "  modulator.connect(modGain); modGain.connect(carrier.frequency);",
        "  var filter = c.createBiquadFilter();",
        "  filter.type = 'lowpass'; filter.frequency.value = opts.brightness || 2200; filter.Q.value = 0.5;",
        "  var out = c.createGain();",
        "  out.gain.setValueAtTime(0, t0);",
        "  out.gain.linearRampToValueAtTime(gainMul, t0 + 0.006);",
        "  out.gain.exponentialRampToValueAtTime(0.0006, t0 + duration);",
        "  carrier.connect(filter); filter.connect(out);",
        "  var dry = c.createGain(); dry.gain.value = 0.85;",
        "  var wet = c.createGain(); wet.gain.value = opts.wet !== undefined ? opts.wet : 0.14;",
        "  out.connect(dry); dry.connect(c.destination);",
        "  out.connect(wet); wet.connect(kioskGetReverb(c));",
        "  carrier.start(t0); modulator.start(t0);",
        "  carrier.stop(t0 + duration + 0.05); modulator.stop(t0 + duration + 0.05);",
        "}",
        // Session request: "make it so the alert fires at 100% for leave
        // in notifications regardless of time." forceVol (optional) lets
        // a caller override the day/night curve entirely — kioskPlayLeaveVoice
        // passes 1 explicitly; every other caller (breaking news) omits
        // it and gets the normal time-of-day-scaled behavior unchanged.
        //
        // Session request, after A/B-ing current vs. rebuilt live: "change
        // gentle to the new rebuild one, change urgent to the new rebuild
        // one." Gentle is one quiet FM bell (D4) — the smallest, simplest
        // cue in the system, since it's also the most frequent. Urgent
        // reuses the exact same FM-bell voice at a touch more modulation
        // edge, told apart from gentle by a quick double-hit instead of a
        // brighter pitch — the same session's own earlier correction ("way
        // too bright") ruled out reaching for brightness to signal urgency.
        "function kioskPlayChime(urgent, forceVol) {",
        "  try {",
        "    var vol = (typeof forceVol === 'number') ? forceVol : kioskAlertVolume(false);",
        "    if (vol <= 0) return;",
        "    var Ctx = window.AudioContext || window.webkitAudioContext;",
        "    if (!Ctx) return;",
        "    var ctx = window.__kioskChimeCtx || (window.__kioskChimeCtx = new Ctx());",
        "    if (ctx.state === 'suspended') { ctx.resume(); }",
        "    var now = ctx.currentTime;",
        "    if (urgent) {",
        "      kioskPlayFMBell(ctx, 329.63, { time: now, gain: 0.5 * vol, duration: 0.35, wet: 0.16, brightness: 2100, modRatio: 3.9, modIndex: 3.0 });",
        "      kioskPlayFMBell(ctx, 329.63, { time: now + 0.15, gain: 0.6 * vol, duration: 0.95, wet: 0.2, brightness: 2100, modRatio: 3.9, modIndex: 3.0 });",
        "    } else {",
        "      kioskPlayFMBell(ctx, 293.66, { time: now, gain: 0.5 * vol, duration: 1.3, wet: 0.18, brightness: 1900, modRatio: 2.8, modIndex: 2.1 });",
        "    }",
        "  } catch (e) {}",
        "}",
        // "Aaron" is a real macOS voice name and won't exist on every
        // kiosk (Windows/Linux browsers report an entirely different
        // voice list) — matched by name, case-insensitively, with a
        // graceful fallback rather than a hard requirement: the same
        // male-name heuristic used to sort the options page's own voice
        // list, then simply whichever voice the browser reports first.
        // getVoices() can briefly return [] right after a page load
        // before the browser's voice list finishes loading async, but a
        // kiosk tab stays open for hours between real alerts, so by the
        // time one actually fires this has always resolved in practice.
        "function kioskFindVoice() {",
        "  if (!window.speechSynthesis) return null;",
        "  var voices = window.speechSynthesis.getVoices();",
        "  if (!voices.length) return null;",
        "  var byName = voices.find(function (v) { return v.name.toLowerCase().indexOf('aaron') !== -1; });",
        "  if (byName) return byName;",
        "  var maleHints = ['male', 'david', 'daniel', 'alex', 'mark', 'guy', 'fred', 'james', 'tom', 'george'];",
        "  var byHint = voices.find(function (v) { return maleHints.some(function (h) { return v.name.toLowerCase().indexOf(h) !== -1; }); });",
        "  return byHint || voices[0];",
        "}",
        // Session request, after clicking through a set of built-for-
        // this-purpose options: "low bell + AARON for sure." A single
        // low sine-tone ping (the exact "Low Bell" candidate from that
        // comparison), then a real spoken sentence for whatever the
        // situation actually is.
        //
        // Session follow-up: "voices on Dell suck... is there a way to
        // have a streamlit side text to speech" — the sentence itself
        // (EC's full bulletin, smoothed; a milestone's "approaching in
        // N minutes" phrasing) now gets built ONCE, server-side, in
        // weather_alerts_bar.py (_spoken_summary / _milestone_spoken_
        // text), then rendered to actual audio there too via Piper
        // (kiosk_tts.py) — every kiosk plays back the identical WAV
        // regardless of its own OS or installed voices, instead of each
        // device's own speechSynthesis picking a different (and on
        // Windows, notably worse) voice for the same text. This
        // function no longer parses or reconstructs any sentence at
        // all — data-summary always already IS the final text to say;
        // data-audio-b64 is that text already rendered, only absent if
        // Piper synthesis itself failed, in which case speechSynthesis
        // is still the safety net.
        "function kioskPlayWeatherAlert(el) {",
        // Session report: "will the AI voice read every single EC
        // alert? even if its a heat or squall warning?" — yes, and it
        // turned out EVERY weather alert (not just genuinely severe
        // ones) was hitting kioskAlertVolume's "severe" branch here,
        // hardcoded true regardless of the real hazard — a routine
        // Heat Warning at 2am got the same never-fully-silent floor as
        // an actual tornado. data-severe (weather_alerts_bar.py's own
        // _is_severe_hazard — thunderstorm/tornado/hurricane/tropical
        // storm/tsunami, the same set already used for the Govee-light
        // storm escalation) now carries the REAL per-alert answer;
        // only those hazards keep the never-silent exception, anything
        // else (heat, cold, frost, fog, squall, a plain statement)
        // follows the normal quiet-at-night curve like any other alert.
        "  var severe = el.getAttribute('data-severe') === 'true';",
        "  var vol = kioskAlertVolume(severe);",
        // Session report: "make the original sound a little more
        // noticeable cause i cannot hear it right off the bat" — a lone
        // 220Hz sine is a real bell's fundamental, but real bells are
        // audible partly BECAUSE of their overtones, not despite them; a
        // pure single tone at that low a pitch can read as weak/thin on
        // a small kiosk speaker with poor bass response. Added a quieter
        // 440Hz octave-up layer on the same envelope (same "Low Bell"
        // character — still one low tone, not a different sound — just
        // with the harmonic content real bells have that helps it cut
        // through) and raised the base gain from 0.4 to 0.55.
        "  try {",
        "    var Ctx = window.AudioContext || window.webkitAudioContext;",
        "    if (Ctx) {",
        "      var ctx = window.__kioskChimeCtx || (window.__kioskChimeCtx = new Ctx());",
        "      if (ctx.state === 'suspended') { ctx.resume(); }",
        "      var now = ctx.currentTime;",
        "      [[220, 0.55], [440, 0.18]].forEach(function (pair) {",
        "        var osc = ctx.createOscillator(), gain = ctx.createGain();",
        "        osc.type = 'sine'; osc.frequency.value = pair[0];",
        "        gain.gain.setValueAtTime(0, now);",
        "        gain.gain.linearRampToValueAtTime(pair[1] * vol, now + 0.02);",
        "        gain.gain.exponentialRampToValueAtTime(0.001, now + 1.9);",
        "        osc.connect(gain); gain.connect(ctx.destination);",
        "        osc.start(now); osc.stop(now + 1.9);",
        "      });",
        "    }",
        "  } catch (e) {}",
        "  try {",
        "    var summary = el.getAttribute('data-summary') || '';",
        "    var audioB64 = el.getAttribute('data-audio-b64');",
        "    if (audioB64) {",
        "      setTimeout(function () {",
        "        var audio = new Audio('data:audio/wav;base64,' + audioB64);",
        "        audio.volume = vol;",
        "        audio.play().catch(function () {});",
        "      }, 2150);",
        "    } else if (summary && window.speechSynthesis) {",
        "      setTimeout(function () {",
        "        window.speechSynthesis.cancel();",
        "        var utter = new SpeechSynthesisUtterance(summary);",
        "        var voice = kioskFindVoice();",
        "        if (voice) utter.voice = voice;",
        "        utter.rate = 0.92;",
        "        utter.pitch = 0.88;",
        "        utter.volume = vol;",
        "        window.speechSynthesis.speak(utter);",
        "      }, 2150);",
        "    }",
        "  } catch (e) {}",
        "}",
        // Same follow-up request, for the "leave in" toast: read the
        // real calendar context out loud instead of a canned line, same
        // as the weather voice above — now built server-side too
        // (commute_reminder._leave_spoken_text), rendered to audio via
        // the same Piper path (kiosk_tts.py). Kept on the SAME 2-note
        // gentle chime (kioskPlayChime(false)) rather than a new tone —
        // this session's ask was specifically to add the voice, not
        // redesign the ping.
        // Session request: "make it so the alert fires at 100% for leave
        // in notifications regardless of time" (bypassed kioskAlertVolume
        // entirely) — later walked back once flat 100% became its own
        // 4am-jumpscare problem: "I don't want the leave in timer to
        // wake everyone in my family up... but I want it to be louder
        // during the day." commute_reminder._leave_volume_ceiling now
        // computes that ceiling server-side from the shift's own real
        // leave-by time (quiet for a 4am leave-by, full by 8am) and
        // passes it as data-volume — every alert for the same shift's
        // countdown shares one ceiling instead of drifting per-alert.
        // Falls back to full volume only if the attribute is somehow
        // missing (a caller that predates this, same defensive shape
        // as _alert_label's own fallback).
        "function kioskPlayLeaveVoice(el) {",
        "  var vol = parseFloat(el.getAttribute('data-volume'));",
        "  if (!(vol >= 0 && vol <= 1)) { vol = 1; }",
        "  kioskPlayChime(false, vol);",
        "  try {",
        "    var summary = el.getAttribute('data-summary') || '';",
        "    var audioB64 = el.getAttribute('data-audio-b64');",
        "    if (audioB64) {",
        "      setTimeout(function () {",
        "        var audio = new Audio('data:audio/wav;base64,' + audioB64);",
        "        audio.volume = vol;",
        "        audio.play().catch(function () {});",
        "      }, 800);",
        "    } else if (summary && window.speechSynthesis) {",
        "      setTimeout(function () {",
        "        window.speechSynthesis.cancel();",
        "        var utter = new SpeechSynthesisUtterance(summary);",
        "        var voice = kioskFindVoice();",
        "        if (voice) utter.voice = voice;",
        "        utter.rate = 0.95;",
        "        utter.pitch = 0.9;",
        "        utter.volume = vol;",
        "        window.speechSynthesis.speak(utter);",
        "      }, 800);",
        "    }",
        "  } catch (e) {}",
        "}",
        // Session request: "add the scoring play for the Habs, Jays and
        // Saints [voice]... add the sports scoreboard ping." Same shape
        // as kioskPlayLeaveVoice above (a distinct earcon, then an
        // optional real spoken line if the toast carries one), but the
        // earcon itself is a small two-note rise instead of one tone —
        // this is deliberately the liveliest cue in the system, the one
        // meant to still read as fun rather than matching gentle/urgent's
        // own restraint. sports_alerts.render_alert_bar only sets data-
        // audio-b64/data-summary for a "score" or "final" alert (see its
        // own comment) — a pregame/warmup/start/streak/lead_change toast
        // still gets the ping with no voice line after it, same as any
        // other chime-only toast.
        "function kioskPlaySportsVoice(el) {",
        "  try {",
        "    var Ctx = window.AudioContext || window.webkitAudioContext;",
        "    if (Ctx) {",
        "      var ctx = window.__kioskChimeCtx || (window.__kioskChimeCtx = new Ctx());",
        "      if (ctx.state === 'suspended') { ctx.resume(); }",
        "      var vol = kioskAlertVolume(false);",
        "      if (vol > 0) {",
        "        var now = ctx.currentTime;",
        "        kioskPlayFMBell(ctx, 349.23, { time: now, gain: 0.5 * vol, duration: 0.3, wet: 0.14, brightness: 2400, modRatio: 2.5, modIndex: 2.4 });",
        "        kioskPlayFMBell(ctx, 392.00, { time: now + 0.07, gain: 0.55 * vol, duration: 0.7, wet: 0.18, brightness: 2600, modRatio: 2.5, modIndex: 2.4 });",
        "      }",
        "    }",
        "  } catch (e) {}",
        "  try {",
        "    var summary = el.getAttribute('data-summary') || '';",
        "    var audioB64 = el.getAttribute('data-audio-b64');",
        "    var spokenVol = kioskAlertVolume(false);",
        "    if (audioB64) {",
        "      setTimeout(function () {",
        "        var audio = new Audio('data:audio/wav;base64,' + audioB64);",
        "        audio.volume = spokenVol;",
        "        audio.play().catch(function () {});",
        "      }, 500);",
        "    } else if (summary && window.speechSynthesis) {",
        "      setTimeout(function () {",
        "        window.speechSynthesis.cancel();",
        "        var utter = new SpeechSynthesisUtterance(summary);",
        "        var voice = kioskFindVoice();",
        "        if (voice) utter.voice = voice;",
        "        utter.rate = 0.98;",
        "        utter.pitch = 1.0;",
        "        utter.volume = spokenVol;",
        "        window.speechSynthesis.speak(utter);",
        "      }, 500);",
        "    }",
        "  } catch (e) {}",
        "}",
        // Session request: "make it so the kiosk plays a muted sound
        // every 5 to 10 sec so it never goes stale... primed for when a
        // real alert comes through." Doesn't replace the one-time
        // browser sound-permission setting (chrome://settings/content/
        // sound, or --autoplay-policy=no-user-gesture-required) — if
        // that's genuinely never been granted, resume() below still
        // silently does nothing, same as kioskPlayChime's own attempt
        // would. What this DOES fix is a real, separate failure mode:
        // some browsers auto-suspend an AudioContext that's sat with
        // nothing scheduled on it for a while (a power-saving
        // heuristic), even after it was properly unlocked earlier — a
        // real chime hitting a re-suspended context would either play
        // late (after resume() completes) or not at all depending on
        // the browser. A truly silent tick (gain permanently at 0, not
        // just quiet) every KIOSK_AUDIO_KEEPALIVE_MS keeps real work
        // scheduled on the shared context often enough that it never
        // sits idle long enough to trigger that auto-suspend, so a real
        // chime always hits an already-running context instead of
        // paying that resume cost on the one moment it actually matters.
        "var KIOSK_AUDIO_KEEPALIVE_MS = 7000;",
        "function kioskAudioKeepAlive() {",
        "  try {",
        "    var Ctx = window.AudioContext || window.webkitAudioContext;",
        "    if (!Ctx) return;",
        "    var ctx = window.__kioskChimeCtx || (window.__kioskChimeCtx = new Ctx());",
        "    if (ctx.state === 'suspended') { ctx.resume(); }",
        "    var osc = ctx.createOscillator();",
        "    var gain = ctx.createGain();",
        "    gain.gain.value = 0;",
        "    osc.frequency.value = 440;",
        "    osc.connect(gain);",
        "    gain.connect(ctx.destination);",
        "    osc.start();",
        "    osc.stop(ctx.currentTime + 0.05);",
        "  } catch (e) {}",
        "}",
        // Session report: "the client side animations... don't show up"
        // for a real toast, despite its chime firing (confirmed heard
        // live) — chime doesn't depend on layout, this does. Measuring
        // el.getBoundingClientRect() synchronously inside the
        // MutationObserver callback risks the exact race
        // news.render_alert_bar's own docstring already names ("it
        // might be running in a refresh window... causing it to
        // instantly die"): a just-inserted real toast can still be
        // mid-layout the instant the mutation fires, so the rect this
        // reads can be zero-sized — the overlay still gets created, just
        // sized to nothing, so nothing visible ever animates even though
        // every other part of the mechanism ran correctly. Deferred with
        // setTimeout (not requestAnimationFrame — confirmed live that rAF
        // callbacks can be suspended indefinitely by the browser while a
        // tab is backgrounded/hidden, and a kiosk's display sleeping or
        // losing focus at exactly the wrong moment shouldn't silently
        // swallow a severe weather alert's own animation) so the rect is
        // read on the next tick instead, after layout has had a chance to
        // settle either way, and skipped outright if it's still
        // zero-sized (the toast was removed again before ever being
        // laid out — nothing real to reveal, not worth animating garbage).
        "function kioskRevealOverlay(el, urgent) {",
        "  setTimeout(function () {",
        "  var rect = el.getBoundingClientRect();",
        "  if (!rect.width || !rect.height) return;",
        "  var overlay = document.getElementById('kiosk-toast-overlay');",
        "  if (!overlay) {",
        "    overlay = document.createElement('div');",
        "    overlay.id = 'kiosk-toast-overlay';",
        "    overlay.style.position = 'fixed';",
        // Session report: "take a look at the leave in alert for when
        // you were on the Jumbotron mode... it slides out to the
        // right, and it looks great... apply that one to the rest of
        // the Toast alerts" — this reveal overlay already runs for
        // every toast (see kioskCheckToastChime's own call below), but
        // 9999 sat BELOW every real toast bar's own z-index:10000 (see
        // .news-alert-bar's own comment in theme.py — every toast bar
        // shares that same value). An overlay positioned exactly on
        // top of an opaque bar with a LOWER z-index renders fully
        // hidden behind it, so the wipe was only ever visible against
        // .jumbo-leave-ticker, which sits at a mere z-index:10 — the
        // one place it could actually show through. Raised to 10001,
        // above every real toast bar, so the same wipe that was only
        // ever reaching the jumbotron ticker now shows for all of
        // them. Deliberately above .screen-picker's own 10000 too
        // (that comment calls itself "above every other overlay" on
        // purpose) — accepted here since this overlay is pointer-
        // events:none and on screen well under a second, so the only
        // real cost is a brief visual pass-through on the rare instant
        // a toast fires while that manually-opened menu happens to be
        // up, never a click blocked.
        "    overlay.style.zIndex = '10001';",
        "    overlay.style.pointerEvents = 'none';",
        "    document.body.appendChild(overlay);",
        "  }",
        "  overlay.style.top = rect.top + 'px';",
        "  overlay.style.left = rect.left + 'px';",
        "  overlay.style.width = rect.width + 'px';",
        "  overlay.style.height = rect.height + 'px';",
        "  overlay.style.background = urgent ? '#FF3B30' : '#FFB300';",
        "  overlay.style.transition = 'none';",
        "  overlay.style.clipPath = 'inset(0 0 0 0%)';",
        "  overlay.style.opacity = '1';",
        // Forces the browser to apply the reset styles above before the
        // transition below is set, so the transition actually animates
        // FROM fully-covering TO cleared rather than jumping straight
        // to its end state with nothing visibly happening — the same
        // reflow-forcing trick this app's other one-shot CSS triggers
        // already rely on.
        "  overlay.offsetHeight;",
        "  overlay.style.transition = 'clip-path 0.55s cubic-bezier(.4,0,.2,1), opacity 0.25s ease-in 0.55s';",
        "  overlay.style.clipPath = 'inset(0 0 0 100%)';",
        "  overlay.style.opacity = '0';",
        "  }, 0);",
        "}",
        "function kioskCheckToastChime() {",
        "  var weatherEl = document.querySelector(KIOSK_WEATHER_VOICE_SEL);",
        "  var urgentEl = weatherEl ? null : document.querySelector(KIOSK_CHIME_URGENT_SEL);",
        "  var leaveEl = (weatherEl || urgentEl) ? null : document.querySelector(KIOSK_LEAVE_VOICE_SEL);",
        "  var sportsEl = (weatherEl || urgentEl || leaveEl) ? null : document.querySelector(KIOSK_SPORTS_VOICE_SEL);",
        "  var emailEl = (weatherEl || urgentEl || leaveEl || sportsEl) ? null : document.querySelector(KIOSK_EMAIL_CHIME_SEL);",
        "  var gentleEl = (weatherEl || urgentEl || leaveEl || sportsEl || emailEl) ? null : document.querySelector(KIOSK_CHIME_GENTLE_SEL);",
        "  var el = weatherEl || urgentEl || leaveEl || sportsEl || emailEl || gentleEl;",
        "  if (!el || el.style.display === 'none') { kioskLastChimeKey = null; return; }",
        // .jumbo-leave-ticker's own child .live-countdown span rewrites
        // its textContent once a second (kiosk-countdown-ticker script
        // above) — fingerprinting straight off el.textContent the way
        // every other toast does would re-chime every second for as
        // long as that ticker's on screen (confirmed live: 6 chimes in
        // 5 seconds). Its own data-target-ms is the stable identity
        // instead — same countdown instance, same target, no re-chime;
        // a genuinely new countdown (a different leave-by time) always
        // carries a different target-ms and still chimes once for real.
        "  var tickerEl = el.querySelector('.live-countdown');",
        "  var key = el.className + '|' + (tickerEl ? tickerEl.getAttribute('data-target-ms') : el.textContent);",
        "  if (key === kioskLastChimeKey) return;",
        "  kioskLastChimeKey = key;",
        "  if (weatherEl) {",
        // data-silent (weather_alerts_bar.py's own render_alert_bar) —
        // session request, for the lightning toast specifically: "make
        // it so it doesn't speak... not audible." Every other weather
        // alert never sets this, so this only ever skips the chime for
        // a caller that explicitly opted into quiet; the toast itself
        // still slides in below exactly like any other.
        "    if (weatherEl.getAttribute('data-silent') !== 'true') { kioskPlayWeatherAlert(weatherEl); }",
        "  } else if (leaveEl) {",
        "    kioskPlayLeaveVoice(leaveEl);",
        "  } else if (sportsEl) {",
        "    kioskPlaySportsVoice(sportsEl);",
        "  } else if (emailEl) {",
        "    kioskPlayChime(false);",
        "  } else {",
        "    kioskPlayChime(!!urgentEl);",
        "  }",
        "  kioskRevealOverlay(el, !!(weatherEl || urgentEl));",
        "}",
        "kioskCheckToastChime();",
        "new MutationObserver(kioskCheckToastChime).observe(document.body, {childList: true, subtree: true, characterData: true});",
        "kioskAudioKeepAlive();",
        "setInterval(kioskAudioKeepAlive, KIOSK_AUDIO_KEEPALIVE_MS);",
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

# UFC coverage — session request: "add UFC to the jumbotron... auto
# rotation between fights coverage starts at 5pm every saturday, only
# will not be shown on main if habs are playing. otherwise let it
# run," corrected right after: "jays should take priority too." Kept
# fully separate from `_takeover` above (see ufc_client.py's own
# docstring on why a fight card needed a genuinely different data
# shape/takeover concept, not a config tweak to the existing one) —
# the exception is applied here, narrowly: only a LIVE Habs or Jays
# game specifically wins, not Saints — UFC still takes the screen over
# a live Saints game if both happen to be active at once.
try:
    _ufc_takeover = ufc_client.takeover_state(now)
except Exception:
    _ufc_takeover = None
if _ufc_takeover is not None and _takeover and _takeover["league"]["sport"] in ("nhl", "mlb") and _takeover["phase"] == "live":
    _ufc_takeover = None

_requested_page = None
try:
    _requested_page = st.query_params.get("page")
    if _requested_page == "jumbotron":
        # Manual preview from a phone, for a day with no game in its
        # window — falls back to whatever game is nearest so the board
        # can actually be looked at outside a real takeover.
        page = "jumbotron"
        _takeover = _takeover or sports_alerts.takeover_preview_state()
    elif _requested_page == "maintenance":
        # Not part of PAGES (config.py) — deliberately excluded from
        # the normal rotation, same "hidden unless asked for" treatment
        # as jumbotron. Session request: "add a maintenance tab... by
        # pressing D." See pages_maintenance.py.
        page = "maintenance"
    elif _requested_page in PAGES:
        page = _requested_page
    elif _takeover or _ufc_takeover:
        page = "jumbotron"
    else:
        page, _, _ = _scheduled_page(_rotation_epoch)
except Exception:
    page = "today"

# The jumbotron owns the entire screen: no hero row, no morning
# briefing, no rotation countdown, no pre-game headline (the board has
# its own, much bigger countdown). The leave-for-work and breaking-news
# headlines skip their render too now that they're pinned banners
# (position: fixed, see theme.py) rather than in-flow text — session
# request: "make it so red headlines dont stick up top when were in
# game mode," reversing an earlier "a game is never a reason to miss a
# shift" decision from back when the leave headline just flowed above
# the hero row instead of overlaying the board. The toast queue, ticker
# and Govee sync still run as normal.
_jumbotron_active = page == "jumbotron" and (_takeover is not None or _ufc_takeover is not None)
# Separate from _jumbotron_active above on purpose — that one is "is
# THIS session's screen currently showing the board," which is exactly
# what the screen-dimming/top-alert suppression above needs, but wrong
# for the physical Govee light: the light is one shared real-world
# device, not per-session, and it should track "is a Jays/Habs game
# actually live/in its takeover window right now" regardless of which
# page any particular connected session (kiosk, a phone checking the
# score) happens to be routed to. sync_plug already gets this right via
# plug_should_stay_on(_takeover) below; sync_lights was wrongly wired
# to page-gated _jumbotron_active instead — session report: "my gov
# lights are completely off... all over the place tonight" while the
# Jays game was genuinely live, traced to exactly this: any session not
# currently on the jumbotron page (e.g. a phone on the news page) would
# compute _jumbotron_active=False and push the shared light straight to
# its normal (here, night-off) state on its own next rerun, fighting
# whatever the kiosk's own session had just set.
_game_takeover_live = _takeover is not None
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
        if _takeover:
            _team_label = _takeover["league"]["label"].title()
        elif _ufc_takeover:
            _team_label = "UFC"  # not .title()'d — that would mangle it to "Ufc"
        else:
            _team_label = ""
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

# Ordinary page-to-page rotation curtain — session report: "the
# transition between pages is quite choppy at times where different
# elements from different pages kinda blend into one before delivering
# the other ones. Can we make it so that the other page is preloaded
# prior to the switch so that it's a seamless swap, or even a little
# animation to switch between the two pages." Real preloading would
# mean rendering (and fetching data for) every page on every single
# rerun just to have a hidden one ready — a genuine, ongoing cost for
# a purely cosmetic fix. Same trick .jumbo-transition above already
# uses instead: a same-rerun curtain, detected the identical way (a
# genuine flip since the last rerun, via st.session_state — see that
# block's own comment), that masks the moment while the real new page
# finishes streaming in underneath it, then fades away — the practical
# effect of a seamless swap without the cost of a real one. Scoped to
# skip both jumbotron entry and exit (_prev_page/page != "jumbotron")
# since those already get their own, more deliberate curtain above —
# this is only for a routine swap between two ordinary pages.
try:
    _prev_page = st.session_state.get("_prev_page")
    if not _jumbotron_active and _prev_page is not None and _prev_page != page and _prev_page != "jumbotron" and page != "jumbotron":
        st.markdown('<div class="page-transition-curtain"></div>', unsafe_allow_html=True)
    st.session_state["_prev_page"] = page
except Exception:
    pass

_PAGE_LABELS = {
    "home": "Home", "conflicts": "Conflicts", "news": "News", "email": "Email", "markets": "Markets",
    "internals": "Internals", "today": "Today", "household": "Household",
    "weather": "Weather", "hourly": "Hourly", "radar": "Radar", "sports": "Sports", "scores": "Scores",
    "portfolio": "Portfolio", "predictions": "Predictions",
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
_auto_active = " mobile-nav-item-active" if _requested_page not in PAGES and _requested_page != "maintenance" else ""
# Separate from the PAGES loop above (same reasoning as jumbotron —
# not part of the normal rotation, so it doesn't belong in that list).
# Session request: "add a maintenance tab for the mobile version."
_maint_active = " mobile-nav-item-active" if page == "maintenance" else ""
st.markdown(
    f'<div class="mobile-nav"><a class="mobile-nav-item mobile-nav-item-auto{_auto_active}" href="?">Auto</a>{_nav_items}'
    f'<a class="mobile-nav-item mobile-nav-item-maintenance{_maint_active}" href="?page=maintenance">Dev</a></div>',
    unsafe_allow_html=True,
)

# Screen picker — session request: "bind the S key to a selection menu
# where i can pick any of the screens we've built so i can look for
# ideas without needing to sit through the rotation." Rendered
# unconditionally (regardless of `page`, including during a jumbotron
# takeover) so S works no matter what's currently showing — CSS alone
# decides whether it's actually visible, gated on the ?picker=open
# query param the hotkey script above toggles. Every entry (including
# the backdrop/close, see _close_href below) is a plain <a href="...">
# — real navigation, not a JS-driven partial update or an onclick=""
# handler (Streamlit's own markdown sanitizer already strips inline
# style="" from anchors — confirmed live elsewhere in this file — not
# worth gambling that onclick="" survives it too when a plain href does
# the exact same job with zero risk). Clicking any screen tile closes
# the picker for free, since that fresh href has no picker= param at
# all — same "URL is the only source of truth" approach the J/D
# hotkeys already use. Jumbotron/maintenance included alongside the
# normal PAGES rotation — both are real built screens, just
# deliberately excluded from the passive rotation (see their own
# routing comments above), which is exactly what this picker exists to
# route around.
_picker_open = st.query_params.get("picker") == "open"
_picker_entries = [(key, _PAGE_LABELS[key]) for key in PAGES] + [
    ("jumbotron", "Jumbotron"), ("maintenance", "Dev / Maintenance"),
]
_picker_tiles = "".join(
    f'<a class="screen-picker-item{" screen-picker-item-active" if key == page else ""}" href="?page={key}">{label}</a>'
    for key, label in _picker_entries
)
# Wherever closing the picker (backdrop click, the × button) should
# land — exactly the URL state from before it opened, not a hardcoded
# "?": _requested_page already holds the real ?page= value (or None
# for auto-rotation), same source the mobile-nav's own "Auto" link
# above is built from.
_close_href = f"?page={_requested_page}" if _requested_page in PAGES or _requested_page in ("jumbotron", "maintenance") else "?"
st.markdown(
    f'<div class="screen-picker{" screen-picker-open" if _picker_open else ""}">'
    f'<a class="screen-picker-backdrop" href="{_close_href}"></a>'
    f'<div class="screen-picker-panel">'
    f'<div class="screen-picker-header"><span>Jump to a screen</span>'
    f'<a class="screen-picker-close" href="{_close_href}">&times;</a></div>'
    f'<div class="screen-picker-grid">{_picker_tiles}</div>'
    f"</div></div>",
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
if _requested_page not in PAGES and not _jumbotron_active and page != "maintenance":
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

# Session request: "add a lot more conditions... proper animations for
# rain or excessive heat or whatever." Reuses the SAME thresholds
# weather_alerts_bar._fallback_text already established for its own
# extreme-heat/cold banner (config.EXTREME_HEAT_THRESHOLD_C/EXTREME_
# COLD_THRESHOLD_C) rather than inventing new numbers — but against the
# CURRENT actual reading (feels_like_c, falling back to temp_c), not
# that banner's own forecast high/low: the scene is meant to reflect
# what it actually looks/feels like right now, the same "current
# reading, not today's forecast extreme" distinction weather_records_
# client's own record badge already draws.
weather_temp_extreme = None
if weather:
    _scene_temp = weather.get("feels_like_c")
    if _scene_temp is None:
        _scene_temp = weather.get("temp_c")
    if _scene_temp is not None:
        if _scene_temp >= EXTREME_HEAT_THRESHOLD_C:
            weather_temp_extreme = "heat"
        elif _scene_temp <= EXTREME_COLD_THRESHOLD_C:
            weather_temp_extreme = "cold"

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
# needing its own boundary — this only ever matters for the pre-dawn
# half of the night anyway, since the sunrise-undim block further down
# always pulls this back down before real midday regardless.
#
# Session report: "I think we have it tied up to the sunset/sunrise
# thing right now... instead of having it turn off at a different time
# every day, make it go into dim night mode at nine PM." Used to also
# require `phase == "night"` (real astronomical night, from scenery.
# phase_for) — on a long summer evening, real night can start well
# after 9pm, so quiet_hours stayed False (screen still bright) for a
# while past the intended fixed start. Dropped that condition entirely:
# this is now a plain fixed clock window, independent of the sky/
# scenery phase used everywhere else — that phase (and the actual
# background gradient it paints) is untouched, still fully real-
# condition-based, exactly as asked ("keeps its whole background color
# scheme to whatever is going on... just the turn on, turn off
# structure").
QUIET_HOURS_START_HOUR = 21
quiet_hours = now.hour >= QUIET_HOURS_START_HOUR or now.hour < 12
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
            sky_style(category, phase, bg_fade_from, bg_blend, now, weather_temp_extreme),
            unsafe_allow_html=True,
        )
        st.markdown(
            scene_html(category, phase, weather["weather_code"] if weather else 2, now, weather_temp_extreme),
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

    MORNING_UNDIM_MINUTES = 120  # "an hour and a half, two hours... i mean slowly" — the longer end of that range, pacing unchanged

    # Morning undim, overriding the fast (FADE_SECONDS = 90s) ramp above
    # AND the quiet_hours floor just above this. Originally keyed on
    # real elapsed minutes since `weather["sunrise"]` — session
    # follow-up, immediately after the plug/quiet_hours fix above went
    # to a fixed clock schedule: "even though the plug turns on at four
    # thirty, the display will still be dimmed until seven AM, correct?"
    # It wasn't quite that — checked live, real sunrise today was
    # 6:05am, so the ramp wouldn't even START until then and wouldn't
    # finish until 8:05am, not 7 — but the same seasonal-drift problem
    # already fixed for the plug/dim-start applied here too (a winter
    # sunrise past 7:30am would push full brightness to 9:30-10am).
    # Fixed to a clock schedule now: starts at MORNING_UNDIM_START_HOUR
    # (5am — 30 min after the plug's own fixed 4:30am power-on, so the
    # room gets a real "on but still dim" moment rather than jumping
    # straight to brightening the instant it has power), same 120-
    # minute pacing as before, landing on a clean, fully-bright-by-7am
    # every single day regardless of season — matching what the
    # question itself assumed was already happening.
    #
    # This intentionally does NOT touch the sky gradient/phase_for's
    # own real-sunrise-based clamp — only the dim overlay's own pace,
    # which is what was actually asked about; the actual background
    # color scheme stays exactly as real-condition-based as it already
    # was. Doesn't touch the evening (sunset→night) dim-IN side at all
    # — only the morning undim was ever in question here.
    #
    # Extends its own authority past the ramp itself (clamped to 0,
    # via max()) through the rest of the day, up to QUIET_HOURS_START_
    # HOUR — not just the 2-hour ramp window. Caught before ever
    # shipping: quiet_hours (line ~1514) is True for any hour < 12, a
    # bound that only worked in the old sunrise-tied version because
    # phase naturally left "night" well before the ramp finished. Now
    # that quiet_hours no longer checks phase at all (the plug/dim-
    # start fix earlier this same session), that safety net is gone —
    # without this, night_dim would snap back to quiet_hours' 1.0 the
    # moment the ramp's own window ended at 7am and stay fully dark
    # until quiet_hours itself lapses at noon. Bounded to before
    # QUIET_HOURS_START_HOUR (9pm) specifically so this doesn't fight
    # the evening dim-in — past 9pm this stops applying and control
    # correctly reverts to quiet_hours' own 1.0.
    MORNING_UNDIM_START_HOUR = 5
    undim_start = now.replace(hour=MORNING_UNDIM_START_HOUR, minute=0, second=0, microsecond=0)
    minutes_since_undim_start = (now - undim_start).total_seconds() / 60
    if minutes_since_undim_start >= 0 and now.hour < QUIET_HOURS_START_HOUR:
        night_dim = max(0.0, 1.0 - minutes_since_undim_start / MORNING_UNDIM_MINUTES)

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

    # Session request: an early shift's leave-in countdown can start
    # ticking well before the phase/quiet-hours fade naturally
    # brightens things (e.g. an 8am appointment pulls the 2-hour
    # headline window back to ~5:30am) — force full brightness while
    # that headline is actually up so the countdown is readable, not
    # sitting under the sleep-dim overlay. Capped to before 7am
    # specifically: past that, phase is already "day" and the normal
    # morning brightening has it covered on its own.
    if now.hour < 7:
        try:
            if commute_reminder.leave_headline_active(now):
                night_dim = 0.0
        except Exception:
            pass

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

# Fetched once per rerun and reused below to feed the bottom rotating
# alert bar — get_new_alerts() marks headlines as seen as a side
# effect, so it must only be called once per script run, REGARDLESS of
# page — skipping it during a takeover would stall the batch
# classifier and the seen-headline tracking for as long as the game
# runs. update_top_alert's own state-tracking/push-dedup also still
# needs to run unconditionally for the same reason; only the actual
# on-screen render is gated on _jumbotron_active, and that now happens
# once, jointly with the other 3 "red headline" sources, via
# headline_rotation.render further down (see its own comment) rather
# than news.render_top_alert_bar directly here. Wrapped since a bug in
# this tracking shouldn't stop the clock/hero row and every page below
# it from rendering.
new_alerts = []
try:
    new_alerts = news.get_new_alerts()
    news.update_top_alert(new_alerts)
except Exception:
    pass

_weather_alert_shown = False

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
    # inconsistent to trust. The Radar page that still showed the live
    # map for manual reading was itself later removed too ("get rid of
    # radar and replace it with hourly weather data") — see
    # pages_hourly.py for its replacement.
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
        # Session report, in two parts: first "27 in 2025... that is not
        # a record high, it is a year ago" (fixed by labeling the real
        # 10-year basis instead of just the bare year), then "the
        # hottest August 7th ever recorded... why don't you just say
        # that?" once that honest "(10y)" label made clear it wasn't
        # actually an all-time record. weather_records_client now
        # genuinely looks back to ARCHIVE_START_YEAR (1940 — the real
        # floor of what the archive API can provide, confirmed live),
        # so this can finally say "since 1940" and mean it literally,
        # not round up a decade to "ever."
        extras.append(
            f'<span class="weather-extra" style="color:{record_color}; '
            f'background:{record_bg}; border-color:{record_color};">'
            f'{record_label} {record["kind"]} (since {weather_records_client.ARCHIVE_START_YEAR}) · '
            f'{record["record"]:.0f}° in {record["year"]}</span>'
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
    # Session request: "let me know when we hit a new quarter which
    # means my sales reset" — TD's own fiscal quarters (confirmed live:
    # Nov/Feb/May/Aug, one calendar quarter ahead of the regular year),
    # not the calendar ones. Same today/evening-tomorrow gating as the
    # garbage/payday badges just above, for the same reason: this is
    # rare enough (4x/year) that it's worth flagging the evening before
    # too, not just the instant it happens. Violet — every other color
    # already used nearby (brown/green/orange/blue) is claimed.
    quarter = td_quarter_schedule.next_quarter_start(now.date())
    if quarter["days_until"] == 0 or (quarter["days_until"] == 1 and now.hour >= EVENING_BADGE_HOUR):
        quarter_when = "today" if quarter["days_until"] == 0 else "tomorrow"
        extras.append(
            f'<span class="weather-extra" style="color:#BF5AF2; '
            f'background:{_badge_bg("#BF5AF2", 0.22)}; border-color:#BF5AF2;">'
            f'New TD quarter {quarter_when}</span>'
        )
    # Session request: "flag pension days so i know when the branch
    # will be a zoo" — CPP/OAS payment days, a real, well-known
    # branch-traffic spike (see cpp_payment_dates.py's own docstring
    # for why these are the real published Service Canada dates, not a
    # computed rule). Same today/evening-tomorrow gating as every other
    # badge here. Rose/red — reads as "brace yourself" rather than the
    # neutral-good tone of payday's green, deliberately different even
    # though both are "money moved" events.
    cpp = cpp_payment_dates.next_payment_date(now.date())
    if cpp and (cpp["days_until"] == 0 or (cpp["days_until"] == 1 and now.hour >= EVENING_BADGE_HOUR)):
        cpp_when = "today" if cpp["days_until"] == 0 else "tomorrow"
        extras.append(
            f'<span class="weather-extra" style="color:#FF375F; '
            f'background:{_badge_bg("#FF375F", 0.22)}; border-color:#FF375F;">'
            f'CPP day {cpp_when}</span>'
        )
    # Session request: "can you include the first day of each season as
    # a hero badge/fact the AI can use" — real astronomical equinox/
    # solstice dates (see seasons_client.py's own docstring), same
    # today/evening-tomorrow gating as every other badge here. Golden
    # yellow — every other color already used nearby (green/violet/
    # rose-red) is claimed, and it reads as sun/season-change rather
    # than any of this row's existing "money moved" associations.
    season = seasons_client.next_season_start(now.date())
    if season and (season["days_until"] == 0 or (season["days_until"] == 1 and now.hour >= EVENING_BADGE_HOUR)):
        season_when = "today" if season["days_until"] == 0 else "tomorrow"
        extras.append(
            f'<span class="weather-extra" style="color:#FFD60A; '
            f'background:{_badge_bg("#FFD60A", 0.22)}; border-color:#FFD60A;">'
            f'{season["label"]} starts {season_when}</span>'
        )
    # Session request: "what other hero badges can we add... is there
    # an area that's not covered?" — statutory holidays already fed a
    # morning-brief fact (holidays_client.holiday_clause) but never a
    # badge. Same today/evening-tomorrow gating as every other calendar
    # badge here, via next_holiday (a purpose-built twin of
    # holiday_clause's own lookup, shaped like every other next_X
    # function on this page rather than holiday_clause's own wider,
    # differently-worded lookahead). Teal — every other color nearby
    # (brown/green/violet/rose/gold) is already claimed, and it reads
    # as its own distinct "calendar" signal rather than another green
    # "money" badge.
    holiday = holidays_client.next_holiday(now.date())
    if holiday and (holiday["days_until"] == 0 or (holiday["days_until"] == 1 and now.hour >= EVENING_BADGE_HOUR)):
        holiday_when = "today" if holiday["days_until"] == 0 else "tomorrow"
        extras.append(
            f'<span class="weather-extra" style="color:#30D5C8; '
            f'background:{_badge_bg("#30D5C8", 0.22)}; border-color:#30D5C8;">'
            f'{holiday["label"]} {holiday_when}</span>'
        )
    # Session follow-up, same "what other hero badges" question — black
    # ice risk already fed a morning-brief fact (morning_briefing.
    # _road_ice_clause) but never a badge either. Plain same-day flag,
    # no days_until gating needed (road_conditions.ice_risk is already
    # "is this true right now"), same shape as the UV/AQI badges above
    # rather than the calendar-event badges' today/tomorrow pattern.
    # Icy blue — distinct from rain nowcast's own #64D2FF further down,
    # cold/warning enough to read as "drive carefully" at a glance.
    if road_conditions.ice_risk(weather.get("temp_c"), weather.get("forecast_low_c"), weather):
        extras.append(
            f'<span class="weather-extra" style="color:#0A84FF; '
            f'background:{_badge_bg("#0A84FF", 0.22)}; border-color:#0A84FF;">'
            f"Black ice risk</span>"
        )
    # Session request: "move the rain forecasting into... a hero badge
    # if it's flagged" — the minute-cast (precip_nowcast_client.py)
    # used to sit as its own tile on the Radar page; pulled out
    # entirely so that page could go back to being just the map,
    # "much much much bigger" (see pages_radar.py). Same badge-row
    # shape as everything else here, but its own much shorter fuse —
    # a minute-cast only ever covers the next 60 minutes in the first
    # place, so "flagged" means rain is actually about to start or
    # stop somewhere in that window, not a days-out heads-up the way
    # the badges above this one work. Blue — unclaimed among this
    # row's own palette, and already this app's own color for weather/
    # rain elsewhere (the Weather page's beacon, the radar "you are
    # here" marker).
    #
    # Session report: "there was rain in the nowcast last night... I
    # got the toast alert that rain was in forty five minutes, but I
    # didn't end up seeing anything [on the badge]... the rain, in
    # fact, did end up coming." Root cause: this used to only badge the
    # two EDGES (an approaching or clearing moment), not the steady
    # middle — real rain that's already started but whose model hasn't
    # resolved a clear end within the 60-minute window yet fell into a
    # real gap where neither rain_starting_in_minutes nor
    # rain_ending_in_minutes returns anything, so the badge showed
    # nothing even while it was genuinely raining. Follow-up request:
    # "I want it to be a full thing... rain in, then rain now, and
    # then clearing in" — a third, live "Rain now" state closes that
    # gap, and "clearing" replaces the old "easing" wording to match.
    try:
        nowcast = precip_nowcast_client.minutely_forecast()
    except Exception:
        nowcast = None
    if nowcast:
        starting = precip_nowcast_client.rain_starting_in_minutes(nowcast)
        ending = precip_nowcast_client.rain_ending_in_minutes(nowcast)
        nowcast_text = None
        if starting is not None:
            nowcast_text = "Rain starting now" if starting == 0 else f"Rain in {starting} min"
        elif ending is not None:
            nowcast_text = "Clearing now" if ending == 0 else f"Clearing in {ending} min"
        elif nowcast[0]["precip_rate_mm"] >= precip_nowcast_client.DEFAULT_THRESHOLD_MM:
            # Raining right now, but the model hasn't resolved a clear
            # end within the window yet — the exact gap from the
            # session report above.
            nowcast_text = "Rain now"
        if nowcast_text:
            extras.append(
                f'<span class="weather-extra" style="color:#64D2FF; '
                f'background:{_badge_bg("#64D2FF", 0.22)}; border-color:#64D2FF;">'
                f'{nowcast_text}</span>'
            )
    extras_html = f'<div class="weather-extras">{"".join(extras)}</div>' if extras else ""

    weather_block = f"""<div class="hero-weather">
        <div class="clock weather-condition"><span class="weather-icon">{icon_svg}</span>{weather['temp_c']:.0f}°C</div>
        <div class="weather-condition-label">{condition_label}</div>
        <div class="date-sub">Corbeil{hilo_html}</div>{extras_html}
    </div>"""

# Directly above the clock, page-independent (visible regardless of
# which of the 6 rotating pages is up, unlike Today's own content).
# Skipped during a takeover — session request: "make it so red
# headlines dont stick up top when were in game mode" — now that it's
# position: fixed (see theme.py), it would pin itself right over the
# jumbotron's own board instead of just flowing above it.
#
# Session request: "make it so all the red headlines within the last 2
# hours cycle at the top of the screen with a cool animation when it
# swaps, make it hard cached in upstash so refreshes dont reset it." A
# single call now covers what used to be 4 separate ones stacked at
# fixed offsets (commute_reminder.render_leave_headline, weather_
# alerts_bar.render_storm_headline/render, news.render_top_alert_bar) —
# see headline_rotation.py's own module docstring for the full story.
try:
    if not _jumbotron_active:
        _weather_alert_shown = headline_rotation.render(now, weather)
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

# AI outage push — page-independent and NOT gated on _jumbotron_active,
# unlike the badge render below: an outage matters just as much during
# a takeover as any other time, same reasoning as news.get_new_alerts()
# running unconditionally every rerun. See groq_client.notify_if_outage
# for the "meaningful period, not a single blip" gate and its own
# per-episode dedup. Session request: "add meaningful outage alerts
# like an AI outage."
try:
    groq_client.notify_if_outage()
except Exception:
    pass

# Small bottom-right system-health glance — session request, after the
# original percentage-based version's own blind spots caused real
# confusion ("thought we rate limited main?? ... badge said 100%"):
# "can you just change the badge to say AI: Active or AI: Rate Limited
# or any an all other statuses it may have." Later widened to one row
# per model — session request, once conflicts started pinning its own
# model (gpt-oss-120b) separately from everything else's default
# (llama-3.3-70b-versatile): "since we have a bunch of different
# models now... show what models are active and what ones are not
# responding." See groq_client.ai_status_by_model for the full status
# list and what each one actually means. Page-independent like the
# pinned headlines above; suppressed during a takeover for the same
# reason they are.
if not _jumbotron_active:
    try:
        _ai_rows_html = "".join(
            f"""<div class="ai-status-row">
                <span class="ai-status-dot ai-status-dot-{m['tone']}"></span>
                <span class="ai-status-text">{m['label']}: {m['status']}</span>
            </div>"""
            for m in groq_client.ai_status_by_model()
        )
        st.markdown(f'<div class="ai-status-bar">{_ai_rows_html}</div>', unsafe_allow_html=True)
    except Exception:
        pass

# The jumbotron brings its own marquee (clock, date, weather), so the
# standard hero row would just be a duplicate stacked above it.
if not _jumbotron_active:
    # Reserves the real vertical space the unified headline-rotation
    # slot occupies (theme.py's .headline-rotation, fixed at top:18px)
    # so the clock/weather row renders below it instead of underneath
    # it — session report, from back when this was 3-4 separately
    # stacked fixed banners rather than 1: "our heat warning just
    # popped up and its kinda colliding with the leave in timer."
    # Shrunk from 220px (tuned for that old worst-case stack of up to 3
    # elements) to roughly this one element's own actual height, now
    # that only ever one shows at a time. Only added on a rerun where
    # it actually rendered (_weather_alert_shown), not a permanent gap
    # on every ordinary alert-free day.
    _hero_spacer = '<div style="height: 110px;"></div>' if _weather_alert_shown else ""
    st.markdown(
        f"""{_hero_spacer}<div class="hero-row">
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
# Push, unconditional (page-independent, not gated on _jumbotron_active
# — same reasoning as the AI outage check above) — see
# data_health.notify_stale for the per-source, per-episode dedup.
try:
    data_health.notify_stale(_stale_sources)
except Exception:
    pass
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
    # Session request: "make sure that the AI is only actually called
    # if we're not in jumbotron mode... if we're not in jumbotron mode,
    # have the AI called to do an evening brief." Same gate as the
    # morning brief right above — their own time windows never overlap
    # (5-10am vs 7-11pm), so at most one of the two ever actually
    # renders anything on a given rerun regardless.
    try:
        evening_briefing.render(now)
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

# Session report: "the transition between pages is quite choppy...
# different elements from different pages pop up as longer than five
# seconds." Root cause (confirmed via a full audit of every page's own
# data sources against fetch_throttle.py's hard-floored 0.5s gap
# between any two real, cache-miss outbound calls anywhere in the
# app): the bottom ticker below already keeps most "many-source" pages
# (Markets, Internals, News, Home, Today, non-live Sports) continuously
# warm by incidentally calling the exact same underlying cached
# functions on every rerun regardless of which page is showing — but
# Scores, Household, and Weather each have their own data sources that
# nothing else in the app ever touches. With PAGE_ROTATION_SECONDS at
# 5 minutes and 15 pages in rotation, a full cycle is ~75 minutes —
# far longer than any of these pages' own 5-15 minute TTLs — so every
# single time rotation swings back around to one of them, ALL of its
# sources are guaranteed stale at once, forcing several real fetches
# to serialize back to back through fetch_throttle's own 0.5s-per-call
# floor before the page can even finish rendering: 3 for Scores
# (MLB/NHL/NFL), up to 4 bundled inside local_news_client.fetch_items
# for Household, 2 for Weather (EC + Open-Meteo) — several real seconds
# of pure throttled waiting, on top of actual network latency, exactly
# matching the reported symptom. Same fix as the FRED readings above:
# call them unconditionally too, so their own cache entries never
# actually go cold between rotation visits, same as everything the
# ticker already keeps warm by accident.
try:
    for _league in scores_client.LEAGUES:
        scores_client.fetch_games(_league["key"])
except Exception:
    pass
try:
    local_news_client.fetch_items()
except Exception:
    pass
try:
    ec_forecast.current_conditions()
    daily_forecast()
except Exception:
    pass

# Intraday change of whatever instrument best represents "the market"
# right now drives the Govee light's base color below — same open/
# closed swap (index / futures) as the Markets page itself for "open"/
# "closed". Fetched unconditionally like the FRED readings above, but
# this reuses quote_for's own 5-minute cache (the same cache the
# Markets page itself hits), so it's free network-wise once anything
# has warmed it.
#
# Session request: "instead of using crypto as a proxy for weekend
# sentiment, can we use [Polymarket's SPY-closes-above contract]?" —
# on weekends this is now Polymarket's own market-implied expected SPY
# close (prediction_markets_client.close_forecast_return), turned into
# a plain return % against SPY's own last actual close, instead of
# Bitcoin's intraday move. Checked live: this exact "closes above"
# contract shape only exists for SPY and WTI Crude Oil on Polymarket —
# Nasdaq/Dow/Gold don't have one — so SPY is what stands in here, the
# same role "sp500" already plays in the open/closed states above it.
try:
    market_status = market_yf_client.market_status()
    if market_status == "weekend":
        _spy_quote = market_yf_client.quote_for("SPY")
        _spy_last_close = _spy_quote["history"][-1] if _spy_quote and _spy_quote.get("history") else None
        _spy_forecast = prediction_markets_client.close_forecast_return("spy", _spy_last_close)
        market_intraday_pct = _spy_forecast["pct_return"] if _spy_forecast else None
    else:
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
    elif page == "email":
        _safe_render(pages_email.render)
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
    elif page == "hourly":
        _safe_render(pages_hourly.render)
    elif page == "radar":
        _safe_render(pages_radar.render)
    elif page == "jumbotron":
        _safe_render(pages_jumbotron.render, now, _takeover, weather, _ufc_takeover)
    elif page == "sports":
        _safe_render(pages_sports.render)
    elif page == "scores":
        _safe_render(pages_scores.render, _rotation_epoch)
    elif page == "portfolio":
        _safe_render(pages_portfolio.render)
    elif page == "predictions":
        _safe_render(pages_predictions.render, readings, FRED_API_KEY)
    elif page == "maintenance":
        _safe_render(pages_maintenance.render)
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
#
# The phone push for this same milestone lives inside commute_reminder.
# check() itself now, not here — session report: "I received the leave
# for work [alert] three times," root-caused to st.session_state being
# scoped per browser connection (a reconnect resets it, so a dedup
# built on it fires again from that fresh session's point of view).
# check()'s own module-level dedup is immune to that; see its docstring.
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

# EC weather-alert toasts: same queue, same isolation reasoning as the
# blocks above — session report: "a recent special weather statement
# just came in but it didnt show as a toast alert." The persistent
# banner (headline_rotation.render, further down) already covers most
# pages, but is skipped entirely during a jumbotron takeover, and this
# toast queue is the one thing that still runs regardless (see
# weather_alerts_bar.get_new_alerts's own docstring for the full
# reasoning) — genuinely the only path that guarantees a new alert is
# never missed just because a game happened to be on screen.
try:
    new_alerts.extend(weather_alerts_bar.get_new_alerts(now))
except Exception:
    pass

# Storm-proximity toasts: "toast alerts for when the storm gets closer
# every like 5-10 mins... same thing for when the storm is leaving" —
# a separate, repeating cadence from the one-shot "new alert" toast
# right above (see weather_alerts_bar.get_storm_proximity_alerts's own
# docstring), so it gets its own try/except for the same isolation
# reasoning as every other block here.
try:
    new_alerts.extend(weather_alerts_bar.get_storm_proximity_alerts(now))
except Exception:
    pass

# Nearby lightning-strike toasts — session request: "a breaking news
# alert when there's lightning within... ten kilometers on my
# location." Own module (Xweather, not Environment Canada — see
# lightning_client's own docstring on why), same isolation reasoning
# and "kind": "weather" dispatch as the two blocks above, so a strike
# rides the exact same top-priority toast lane a real EC warning does.
try:
    new_alerts.extend(lightning_client.get_new_alerts(now))
except Exception:
    pass

# Rain-nowcast toasts — session request: "did the nowcast from xweather
# fire this morning at all... build [a real alert]." Own module
# (precip_nowcast_client.py), same isolation reasoning and "kind":
# "weather" dispatch as the two blocks above — see that module's own
# get_new_alerts docstring for why it reuses lightning_client's exact
# pattern rather than a new toast family of its own.
try:
    new_alerts.extend(precip_nowcast_client.get_new_alerts(now))
except Exception:
    pass

# Important-email toasts — session request: "incorporate emails...
# important emails to be sent to me via a toast alert, but you need to
# make sure that they're important, and not crap." Own module
# (email_client.py, IMAP + an app password — see its own docstring),
# same isolation reasoning as every other block here: a Gmail hiccup
# never takes down breaking news/weather/sports.
try:
    new_alerts.extend(email_client.get_new_alerts(now))
except Exception:
    pass

# Prediction-market rate-odds toasts — session request: "rolling rate
# odds from polymarket/kalshi... news/toast alert on a big swing." Same
# isolation reasoning as every other block here: a bug in one bank's
# check must never take down another's, or real breaking-news alerts.
# check_for_swing itself already returns None almost every call (see
# its own docstring) — this only actually produces an alert on a real
# consensus flip or a large probability move, not every rerun.
#
# Session follow-up: "as soon as a contract hits a hundred percent,
# send us a big toast alert. I want a phone notification... that goes
# for everything" — check_for_lock_in runs for every bank right
# alongside check_for_swing, same isolation/None-most-of-the-time
# shape, own try/except so one bank's lock-in check can't take down
# another's.
for _pm_bank in prediction_markets_client.BANKS:
    try:
        swing = prediction_markets_client.check_for_swing(_pm_bank)
        if swing:
            new_alerts.append(prediction_markets_client.swing_alert(swing))
    except Exception:
        pass
    try:
        lock_in = prediction_markets_client.check_for_lock_in(_pm_bank)
        if lock_in:
            new_alerts.append(prediction_markets_client.lock_in_alert(lock_in))
    except Exception:
        pass

# Radar-based severe/tracking-started toast alerts (ec_radar.
# severe_weather_alert / tracking_started_alert) removed along with the
# rest of the radar lookahead-forecasting layer at the user's own
# request, judged too inconsistent to trust — the live radar map that
# layer sat alongside was itself removed later ("get rid of radar and
# replace it with hourly weather data").

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
    # Weather ranks above even commute — session request: weather alerts
    # are "arguably the most important part of the dashboard," and a
    # genuine EC warning outranks a leave-for-work reminder the same way
    # it already outranks everything else in this queue.
    if alert.get("kind") == "weather":
        return -1
    if alert.get("kind") == "commute":
        return 0
    if alert.get("kind") == "sports":
        priority = sports_alerts.COUNTDOWN_PRIORITY
        sport = alert.get("sport")
        return 1 + (priority.index(sport) if sport in priority else len(priority))
    # Personal correspondence outranks routine/market news, same
    # reasoning as every tier above it, but below anything that's
    # actually time-boxed (a commute window, a live game) — an email
    # already sitting in the inbox isn't going anywhere in the next
    # few minutes the way those are.
    if alert.get("kind") == "email":
        return 5
    return 10


def _render_bottom_ticker(readings: dict) -> None:
    """A pure live-stat ticker (session request: "remove the dates for
    data... just not [as] informational and as good as the other
    options" — the release-date countdown machinery this used to have
    is gone entirely, see ticker.py's own module docstring). Each
    source isolated in its own try so a single one hiccuping (e.g.
    yfinance briefly unreachable) only drops that one item, not the
    whole ticker.

    Session report: "the bottom bar goes away... the ticker tape goes
    away... the red headliner... should be there, but it's not." A
    caught toast-render failure below used to just leave current_alert
    reset to None with nothing else rendered that rerun — the bottom
    strip going fully blank instead of falling back to this same
    ticker the way an empty alert queue naturally does. Factored out
    so both paths can call it."""
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
        stats.extend(ticker.build_playoff_odds_stat_items())
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
        stats.extend(ticker.build_prediction_market_stat_items())
    except Exception:
        pass
    try:
        gas_stat = ticker.build_gas_stat_item()
        if gas_stat:
            stats.append(gas_stat)
    except Exception:
        pass
    try:
        commute_stat = ticker.build_commute_stat_item()
        if commute_stat:
            stats.append(commute_stat)
    except Exception:
        pass
    try:
        aqi_stat = ticker.build_aqi_stat_item()
        if aqi_stat:
            stats.append(aqi_stat)
    except Exception:
        pass
    try:
        wildfire_stat = ticker.build_wildfire_stat_item()
        if wildfire_stat:
            stats.append(wildfire_stat)
    except Exception:
        pass

    if stats:
        st.markdown(ticker.render_html(stats), unsafe_allow_html=True)


current_alert, elapsed = None, None
try:
    new_alerts.sort(key=_alert_priority)
    if len(new_alerts) > MAX_BURST_ALERTS:
        overflow = len(new_alerts) - MAX_BURST_ALERTS
        news_only = [a for a in new_alerts if _alert_priority(a) == 10]
        keep_news = news_only[overflow:] if overflow < len(news_only) else []
        new_alerts = [a for a in new_alerts if _alert_priority(a) < 10] + keep_news
    toast_queue.extend(new_alerts)

    now_ts = time.time()
    current_alert = toast_queue.current(now_ts)
    if current_alert:
        elapsed = now_ts - current_alert["shown_at"]
        if elapsed > news.TOAST_SECONDS:
            toast_queue.advance()
            current_alert, elapsed = None, None

    if current_alert:
        # Session report: "I'm still not getting any Toast alerts... get
        # rid of the animation... do what you gotta do." The old intro
        # animation needed a per-rerun a/b variant toggle (Streamlit
        # reuses the same bottom-bar DOM node across reruns, and
        # changing animation-name each render was the only way to force
        # a genuine restart rather than reusing an already-completed
        # instance) — removed entirely along with the animation itself
        # (see news.render_alert_bar's own docstring), so there's no
        # rerun-timing state left here to manage at all.
        #
        # Session report: "the GoVi lights are going red... but the
        # toast is not there... I get the alert, but I don't get the
        # toast notification." The Govee block below reads this same
        # current_alert/elapsed pair to decide whether to flash red —
        # a genuinely separate code path from the actual st.markdown
        # call here. Before this, a render failure inside any one of
        # these four dispatch calls fell through to the single bare
        # `except Exception: pass` around this whole block (see below),
        # which left current_alert already assigned to a real, truthy
        # alert — so the light still fired for it even though the
        # toast HTML never actually rendered that rerun. Wrapping the
        # dispatch itself, resetting current_alert to None on failure,
        # and logging what broke (instead of swallowing it silently)
        # means the light can no longer show red for a toast that
        # didn't actually appear, and the next real failure leaves an
        # actual trace instead of vanishing without one.
        try:
            if current_alert.get("kind") == "commute":
                commute_reminder.render_bar(current_alert)
            elif current_alert.get("kind") == "sports":
                sports_alerts.render_alert_bar(current_alert)
            elif current_alert.get("kind") == "weather":
                weather_alerts_bar.render_alert_bar(current_alert)
            elif current_alert.get("kind") == "email":
                email_client.render_alert_bar(current_alert)
            else:
                news.render_alert_bar(current_alert)
        except Exception as toast_render_exc:
            import traceback

            print(f"TOAST RENDER FAILED: {current_alert.get('kind', 'news')} alert {current_alert!r}")
            traceback.print_exc()
            persisted_state.save(
                "toast_render_error",
                {
                    "at": now_ts,
                    "kind": current_alert.get("kind", "news"),
                    "headline": current_alert.get("headline"),
                    "error": f"{type(toast_render_exc).__name__}: {toast_render_exc}",
                },
            )
            current_alert, elapsed = None, None
            # Falls back to the ticker rather than leaving the bottom
            # strip fully blank for this rerun — see _render_bottom_
            # ticker's own docstring for the session report this fixes.
            _render_bottom_ticker(readings)
    elif _jumbotron_active and commute_reminder.leave_headline_active(now):
        # Session report: a golf tee time's leave-in window landing
        # during a Jays game — "that space is crucial for the
        # jumbotron... replace the bottom scroll bar with a timer...
        # game alerts and breaking news is allowed to trump the timer
        # but at least its still there." render_leave_headline (the big
        # red banner) already skips itself entirely during a takeover —
        # no room for it on that board — so without this, an early
        # commitment during game time only ever showed up as scattered
        # milestone toasts, not something continuously visible. Same
        # slot as the market ticker below (position/z-index match
        # exactly, see .jumbo-leave-ticker in theme.py), so this branch
        # only ever runs when current_alert is empty — a real toast
        # still covers it the instant one fires, same as it already
        # covers the market ticker.
        commute_reminder.render_ticker_leave_bar(now)
    else:
        _render_bottom_ticker(readings)
except Exception as _bottom_bar_exc:
    # Session report: "the bottom bar goes away... the ticker tape
    # goes away... the red headliner... should be there, but it's
    # not." This outer catch used to be a bare `except: pass` around
    # the ENTIRE block above — the queue sort/extend, the elapsed
    # calc, and the toast/ticker dispatch all shared it, so a failure
    # anywhere in the shared setup (not just inside one render call,
    # which has its own try/except above) silently blanked the whole
    # bottom strip with zero trace. Logged the same way the render-
    # specific catch above does, and still attempts the ticker as a
    # last-resort fallback (its own try/except, so a failure there
    # can't cascade into a second silent blank).
    import traceback

    print(f"BOTTOM BAR SETUP FAILED: {_bottom_bar_exc!r}")
    traceback.print_exc()
    persisted_state.save(
        "toast_render_error",
        {"at": time.time(), "kind": "setup", "headline": None, "error": f"{type(_bottom_bar_exc).__name__}: {_bottom_bar_exc}"},
    )
    try:
        _render_bottom_ticker(readings)
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
    # Session request: "red govee flashes for when the storm is
    # approaching... solid red at like 30% for when its here... same
    # thing for when the storm is leaving," later "it should show at
    # night" — this one specifically DOES bypass the night gate (see
    # govee_lighting.sync_lights's own updated docstring), unlike
    # breaking news, which still fully respects it.
    try:
        storm_phase_info = weather_alerts_bar.current_storm_phase(now)
    except Exception:
        storm_phase_info = None
    storm_phase_name = storm_phase_info["phase"] if storm_phase_info else None
    govee_lighting.sync_lights(
        phase, market_intraday_pct, breaking_elapsed, now, weather["sunset"] if weather else None,
        aqi_for_lights, category, score_flash, _game_takeover_live, storm_phase_name,
    )
    try:
        leave_timer_active = commute_reminder.leave_headline_active(now)
    except Exception:
        leave_timer_active = False
    # Session report: "I think we have it tied up to the sunset/
    # sunrise thing right now... instead of having it turn off at a
    # different time every day, make it go into dim night mode at nine
    # PM and have it fully turn off at... nine thirty... and turn the
    # monitor on at four thirty AM." sync_plug's own on/off window used
    # to be real civil-twilight first_light/last_light (see its own
    # docstring, now updated) — a fixed daily schedule instead, same
    # same-day [on, off) window shape that check already expects, so
    # nothing about the override logic below it (game_live/leave_timer_
    # active/storm_active/the off-grace buffer) needed to change at all.
    plug_on_at = now.replace(hour=4, minute=30, second=0, microsecond=0)
    plug_off_at = now.replace(hour=21, minute=30, second=0, microsecond=0)
    govee_lighting.sync_plug(
        now,
        plug_on_at,
        plug_off_at,
        game_live,
        leave_timer_active,
        storm_phase_name is not None,
    )
except Exception:
    pass
