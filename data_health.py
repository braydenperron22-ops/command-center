"""Lightweight "is this data source actually still working" tracker —
session request: a staleness watchdog. Every last-good-value fallback
pattern already used throughout this app (portfolio_client, weather_
client, sports_client, news.py, ...) degrades gracefully and silently
when its real source breaks, which is the right call for the page
itself, but means a genuine multi-day outage could sit there completely
unnoticed. This is the missing "someone should still know" half: each
of those modules calls record_success() whenever a fetch genuinely
produces real (non-fallback) data, and check() reports which sources
have gone quiet for longer than they reasonably should.

Session-state only, not disk-persisted — a fresh redeploy/restart
starts with a clean slate rather than immediately flagging every source
as "stale" before it's had a chance to succeed even once.
"""

import time

import streamlit as st

# source_key -> max seconds of silence before it's worth flagging.
# Deliberately generous — the point is "this has been broken for a
# real while," not "this happened to be a few minutes late."
THRESHOLDS_SECONDS = {
    "portfolio": 36 * 60 * 60,  # SnapTrade itself only syncs ~once/day; 36h catches a genuinely missed sync without false-alarming on normal timing
    "weather": 3 * 60 * 60,  # refreshes every ~15-30 min normally
    "sports_schedule": 24 * 60 * 60,  # a schedule pull succeeds daily even off-season (an empty games list is still a real success)
    "news": 6 * 60 * 60,  # several feeds; at least one should succeed within hours even if others are down
}

LABELS = {
    "portfolio": "Portfolio sync",
    "weather": "Weather",
    "sports_schedule": "Sports schedule",
    "news": "News feed",
}


def record_success(source_key: str) -> None:
    """Call this immediately after a fetch genuinely produces real
    (non-fallback) data — cache hits count too (the cache itself only
    ever holds a real prior success), only an actual fallback-to-
    last-good doesn't."""
    st.session_state.setdefault("data_health_last_success", {})[source_key] = time.time()


def check() -> list[dict]:
    """{"key", "label", "hours_stale"} for every source that has BOTH
    succeeded at least once this session AND gone quiet longer than its
    own threshold since — never flags a source that simply hasn't
    reported in yet (e.g. right after a fresh deploy), since that's a
    "give it a minute" state, not a real outage."""
    last_success = st.session_state.get("data_health_last_success", {})
    now = time.time()
    stale = []
    for key, threshold in THRESHOLDS_SECONDS.items():
        last = last_success.get(key)
        if last is None:
            continue
        elapsed = now - last
        if elapsed > threshold:
            stale.append({"key": key, "label": LABELS[key], "hours_stale": elapsed / 3600})
    return stale
