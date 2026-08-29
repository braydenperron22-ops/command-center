#!/bin/bash
# Watchdog for com.brayden.commandcenter — launchd's own KeepAlive only
# restarts the service if the PROCESS actually exits; it has no way to
# notice a process that's still alive but wedged (this Mac's own real
# memory pressure stalling it for a stretch, or a genuine deadlock).
# Session report 2026-08-29: "it only freezes sometimes but the freeze
# is persistent through refreshes" — refreshing a browser can never fix
# this class of freeze, since it's just asking the same stuck server
# for the same thing again. See project_kiosk_watchdog.md.
#
# Checks the heartbeat app.py writes (heartbeat.py) as the literal last
# statement of every successfully-completed script rerun. A stale file
# means a rerun genuinely hasn't finished — not a guess — so this force-
# restarts the launchd service, which KeepAlive then brings back up.
#
# Run on its own independent launchd schedule (com.brayden.commandcenter.
# watchdog.plist) — deliberately a *separate* service from the one it's
# watching, so a hang in the main app can never also freeze the thing
# meant to detect it.

set -u

APP_DIR="/Users/persey/Desktop/macro-dashboard"
HEARTBEAT_FILE="$APP_DIR/data/heartbeat.txt"
LAST_RESTART_FILE="$APP_DIR/data/watchdog_last_restart.txt"
LOG_FILE="$APP_DIR/data/watchdog.log"

# st_autorefresh reruns every 5s; 180s leaves generous slack over the
# documented cold-start worst case (fetch_throttle.py: ~20 external
# sources staggered 0.5s apart just in throttling, on top of real
# per-call latency — some archive-style fetches alone take ~14s) so a
# legitimately slow cold start is never mistaken for a hang.
MAX_AGE_SECONDS=180

# Once we've force-restarted, give the fresh process a full cooldown
# before we're willing to act again — otherwise a slow-but-not-hung
# cold start (or a real outage upstream, e.g. an ESPN/Upstash blip
# affecting many sources at once) could make this fight itself in a
# restart loop instead of just letting the new process finish starting.
COOLDOWN_SECONDS=300

mkdir -p "$APP_DIR/data"
now=$(date +%s)

if [ -f "$LAST_RESTART_FILE" ]; then
  last_restart=$(cat "$LAST_RESTART_FILE" 2>/dev/null)
  if [[ "$last_restart" =~ ^[0-9]+$ ]]; then
    since=$((now - last_restart))
    if [ "$since" -lt "$COOLDOWN_SECONDS" ]; then
      exit 0
    fi
  fi
fi

stale=0
reason=""
if [ ! -f "$HEARTBEAT_FILE" ]; then
  stale=1
  reason="heartbeat file missing"
else
  heartbeat=$(cut -d. -f1 < "$HEARTBEAT_FILE" 2>/dev/null)
  if ! [[ "$heartbeat" =~ ^[0-9]+$ ]]; then
    stale=1
    reason="heartbeat file unreadable"
  else
    age=$((now - heartbeat))
    if [ "$age" -gt "$MAX_AGE_SECONDS" ]; then
      stale=1
      reason="heartbeat stale (${age}s old)"
    fi
  fi
fi

if [ "$stale" -eq 1 ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') $reason — restarting com.brayden.commandcenter" >> "$LOG_FILE"
  echo "$now" > "$LAST_RESTART_FILE"
  launchctl kickstart -k "gui/$(id -u)/com.brayden.commandcenter"
fi
