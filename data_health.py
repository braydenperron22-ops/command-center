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

check() only ever reported this visually (the on-screen watchdog badge
in app.py); notify_stale() below adds a phone push for the same
condition — session request: "add meaningful outage alerts... if one
of our sources go dark for a meaningful period of time."
"""

import time

import streamlit as st

import ntfy_client

# source_key -> max seconds of silence before it's worth flagging.
# Deliberately generous — the point is "this has been broken for a
# real while," not "this happened to be a few minutes late."
THRESHOLDS_SECONDS = {
    "portfolio": 36 * 60 * 60,  # SnapTrade itself only syncs ~once/day; 36h catches a genuinely missed sync without false-alarming on normal timing
    "weather": 3 * 60 * 60,  # refreshes every ~15-30 min normally
    "sports_schedule": 24 * 60 * 60,  # a schedule pull succeeds daily even off-season (an empty games list is still a real success)
    "news": 6 * 60 * 60,  # several feeds; at least one should succeed within hours even if others are down
    # Only goes quiet if BOTH the external (feargreedmeter.com) and
    # computed (yfinance-derived) tiers fail at once — see
    # market_internals.fear_greed_index's own comment.
    "fear_greed": 6 * 60 * 60,
    "shiller_cape": 24 * 60 * 60,  # multpl.com's own value barely moves day to day; cached 6h, so this just needs to be well past that
    "scoreboard": 24 * 60 * 60,  # a scoreboard pull succeeds daily even on a slate with nothing live (an empty games list is still a real success)
}

LABELS = {
    "portfolio": "Portfolio sync",
    "weather": "Weather",
    "sports_schedule": "Sports schedule",
    "news": "News feed",
    "fear_greed": "Fear & Greed Index",
    "shiller_cape": "Shiller CAPE",
    "scoreboard": "Scoreboard",
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


# Module-level, NOT st.session_state — session report: "I received the
# morning brief three times" (a different feature, same root cause):
# st.session_state is scoped per browser connection, and any reconnect
# starts a fresh session with empty state, making a dedup built on it
# fire again from that session's point of view. Same fix as
# morning_briefing._notified_date — see its own comment.
_notified: set[str] = set()


def notify_stale(stale: list[dict]) -> None:
    """Pushes a phone notification once per source, per outage episode —
    not every rerun for as long as it stays stale, which could be hours
    or days once a source is genuinely down. Session request: "add
    meaningful outage alerts... if one of our sources go dark for a
    meaningful period of time" — THRESHOLDS_SECONDS above already is
    that "meaningful period" gate (3-36h depending on the source, not a
    few minutes' lateness), so nothing extra needed here beyond not
    re-pinging every rerun for the same ongoing outage.

    Tracks which source_keys have already been notified this episode at
    module level (see _notified's own comment); a source dropping out
    of `stale` (i.e. it recovered) clears its own flag, so a second,
    later outage on the same source gets its own fresh alert rather
    than staying silently suppressed forever because it already fired
    once months ago."""
    global _notified
    stale_keys = {s["key"] for s in stale}
    _notified &= stale_keys  # drop any source that's since recovered
    for s in stale:
        if s["key"] in _notified:
            continue
        _notified.add(s["key"])
        ntfy_client.send(
            title="Data source down",
            message=f"{s['label']} hasn't updated in {s['hours_stale']:.0f}h.",
            priority="high",
            tags="warning",
        )
