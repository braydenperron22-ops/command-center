#!/bin/bash
# Recovers the kiosk from exactly the failure mode behind the
# "just woke up and there's an error about internet" incident
# (2026-09-15): the kiosk's own network dropped at some point overnight,
# Chromium ended up stuck on its own browser-level "no internet" error
# page, and nothing ever forced a fresh reload once the network
# actually came back. A plain page reload alone can't fix this class of
# freeze — see watchdog_kiosk.sh's own docstring for the identical
# reasoning on the Mac's local test copy, just for a different root
# cause: that one watches a wedged Python process; this one watches a
# stuck browser tab that never even loaded far enough to run any of
# this app's own recovery JS.
#
# Deliberately NOT a "restart Chromium every N minutes regardless"
# script — only restarts on a genuine failing-to-passing TRANSITION
# (the dashboard was unreachable, now it's back). Restarting while
# still genuinely offline accomplishes nothing and would just thrash
# the kiosk every run during a real prolonged outage; restarting on
# every successful check would force a needless, visible reload of an
# already-working kiosk.
#
# Two independent watchdogs on two different signals, deliberately not
# merged — same reasoning app.py's own dashboard-pulse-watchdog already
# documents: this one is blind to a stuck Streamlit SESSION on an
# otherwise fine network (the in-page JS watchdogs already handle
# that — kiosk-stale-watchdog/dashboard-pulse-watchdog, both in
# app.py's consolidated kiosk script); the in-page watchdogs are blind
# to a browser tab that never even loaded far enough for any of that JS
# to start running. This one exists for exactly that gap.
#
# Run every 10 minutes via kiosk_ubuntu_watchdog.timer (session
# request: "make it check in a 10m interval").

set -u

DASHBOARD_URL="https://command-center-hcurakgnngnpwdp8d98hcd.streamlit.app"
STATE_DIR="$HOME/.cache/kiosk_watchdog"
FAILING_MARKER="$STATE_DIR/failing"
LOG_FILE="$STATE_DIR/watchdog.log"
# Confirm the real running process name on this box first: `pgrep -l chromium`.
# Must match kiosk_ubuntu_chromium.service's own ExecStart binary, or
# pkill below silently finds nothing to restart.
CHROMIUM_PROCESS_NAME="chromium"

mkdir -p "$STATE_DIR"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"; }

# /api/v2/app/status is Streamlit Cloud's own lightweight health
# endpoint (confirmed live: fast, real JSON, no cost to the app itself)
# — a more precise signal than a generic internet ping, since it also
# catches "internet's fine but Streamlit Cloud itself is down," which a
# plain ping never would.
if curl --max-time 10 -sf "$DASHBOARD_URL/api/v2/app/status" > /dev/null 2>&1; then
  if [ -f "$FAILING_MARKER" ]; then
    log "Recovered from an outage — forcing Chromium to reload fresh."
    rm -f "$FAILING_MARKER"
    pkill -x "$CHROMIUM_PROCESS_NAME" 2>/dev/null
    # kiosk_ubuntu_chromium.service's own Restart=always brings it
    # straight back up with a fresh page load — that unit owns actually
    # relaunching Chromium, nothing else to do here.
  fi
else
  if [ ! -f "$FAILING_MARKER" ]; then
    log "Dashboard unreachable — marking as failing (won't act again until it recovers)."
    touch "$FAILING_MARKER"
  fi
fi
