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

Module-level state (see _last_success below), not disk-persisted — a
fresh redeploy/restart starts with a clean slate rather than
immediately flagging every source as "stale" before it's had a chance
to succeed even once. Deliberately process-wide rather than
st.session_state too, once that stopped being just a nice-to-have: a
maintenance/diagnostics view opened from a different device (see
pages_maintenance.py) needs to see the same real tracked state the
kiosk's own long-running session already has, not an empty slate of
its own.

check() only ever reported this visually (the on-screen watchdog badge
in app.py); notify_stale() below adds a phone push for the same
condition — session request: "add meaningful outage alerts... if one
of our sources go dark for a meaningful period of time." all_status()
extends this further for the maintenance page, showing every source's
state, not just the currently-stale ones.
"""

import time

import ntfy_client
import persisted_state

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
    # Session request: "put yfinance in the watchdog" — unofficial,
    # reverse-engineered against Yahoo's own internal endpoints, the
    # single most fragile source in the app by design (breaks outright
    # whenever Yahoo changes something, no key/support tier to fall back
    # on), and previously had no data_health coverage at all despite the
    # Markets page's own fear_greed/shiller_cape tiles already being
    # tracked. Real indices/futures/crypto trade continuously (crypto
    # even on weekends — market_yf_client's own docstring), refreshed
    # every MARKET_DATA_TTL_SECONDS (5 min), so same 3h threshold as
    # weather above: generous enough not to false-alarm on a normal
    # blip, still catches a real outage same-day.
    "markets": 3 * 60 * 60,
    # Session request: close the watchdog gap left by today's new gas/
    # banking/weather-trend sources — none of the three had any
    # data_health coverage at all until now. Real, unfiltered feature-
    # level success (see fuel_price_client.eco_mode_status's own
    # record_success call) — it stays "fresh" through a legitimate
    # daily-source-down-but-weekly-CSV-still-working fallback (that
    # degradation is what the graceful-fallback architecture is FOR,
    # same as "weather" here not distinguishing EC-forecast-down-but-
    # hourly-up from fully healthy), only going stale if BOTH the daily
    # scraper and the weekly government CSV are genuinely down at once.
    # 8 days: generous enough to never false-alarm during that one
    # legitimate fallback window, still catches a real full outage.
    "gas_price": 8 * 24 * 60 * 60,
    # weather_records_client.recent_daily_highs — a separate live fetch
    # (Open-Meteo's archive endpoint) from weather_client.py's own
    # current-conditions pipeline (already covered by "weather" above);
    # a break here wouldn't touch the main weather tile at all, so
    # folding it into that key would silently hide a real, distinct
    # failure. Only feeds the AI's own environment-trends context, not
    # anything mission-critical to the kiosk's main display — 72h
    # (3 days) is generous relative to its own 24h cache, without being
    # so long a real multi-day break goes unnoticed for a week.
    "weather_trends": 3 * 24 * 60 * 60,
    # portfolio_client.fetch_activities — a separate SnapTrade endpoint
    # from fetch_portfolio's own balance call (already covered by
    # "portfolio" above); a break here would silently blank the
    # transaction log and the AI's spending context while the balance
    # tile itself kept working fine, so it needs its own key rather
    # than riding on "portfolio"'s. Same ~once/day real sync cadence
    # underneath, so the same 36h threshold.
    "portfolio_activity": 36 * 60 * 60,
}

LABELS = {
    "portfolio": "Portfolio sync",
    "weather": "Weather",
    "sports_schedule": "Sports schedule",
    "news": "News feed",
    "fear_greed": "Fear & Greed Index",
    "shiller_cape": "Shiller CAPE",
    "scoreboard": "Scoreboard",
    "markets": "Markets (yfinance)",
    "gas_price": "Gas price",
    "weather_trends": "Weather trends",
    "portfolio_activity": "Portfolio activity",
}


# Module-level, not st.session_state — session request: a maintenance/
# diagnostics view ("D" hotkey/mobile tab) needs to show the SAME real
# status regardless of which device is looking. The kiosk's own
# long-running tab and a phone opening the same URL are two different
# Streamlit sessions, but this app is one shared server process either
# way, so session_state was silently hiding the kiosk's real tracked
# state from anything else that looked. Still NOT persisted across
# restarts (see this module's own docstring) — that clean-slate-on-
# redeploy behavior is unchanged, this only fixes cross-session/
# cross-device visibility within one running process.
_last_success: dict[str, float] = {}


def record_success(source_key: str) -> None:
    """Call this immediately after a fetch genuinely produces real
    (non-fallback) data — cache hits count too (the cache itself only
    ever holds a real prior success), only an actual fallback-to-
    last-good doesn't."""
    _last_success[source_key] = time.time()


def check() -> list[dict]:
    """{"key", "label", "hours_stale"} for every source that has BOTH
    succeeded at least once this process AND gone quiet longer than its
    own threshold since — never flags a source that simply hasn't
    reported in yet (e.g. right after a fresh deploy), since that's a
    "give it a minute" state, not a real outage."""
    now = time.time()
    stale = []
    for key, threshold in THRESHOLDS_SECONDS.items():
        last = _last_success.get(key)
        if last is None:
            continue
        elapsed = now - last
        if elapsed > threshold:
            stale.append({"key": key, "label": LABELS[key], "hours_stale": elapsed / 3600})
    return stale


def all_status() -> list[dict]:
    """{"key", "label", "hours_since", "threshold_hours", "status"} for
    EVERY tracked source, not just the currently-stale ones check()
    returns — session request: the maintenance page showing "how
    everything is updating," not just what's currently broken. status
    is "unknown" (hasn't succeeded even once yet this process), "stale"
    (past its own threshold), or "fresh" (succeeded within it)."""
    now = time.time()
    out = []
    for key, threshold in THRESHOLDS_SECONDS.items():
        last = _last_success.get(key)
        if last is None:
            out.append(
                {"key": key, "label": LABELS[key], "hours_since": None, "threshold_hours": threshold / 3600, "status": "unknown"}
            )
            continue
        elapsed = now - last
        out.append({
            "key": key,
            "label": LABELS[key],
            "hours_since": elapsed / 3600,
            "threshold_hours": threshold / 3600,
            "status": "stale" if elapsed > threshold else "fresh",
        })
    return out


# Loaded once at import, not re-fetched from persisted_state on every
# call — notify_stale() runs unconditionally every 5s rerun (app.py
# calls it with no gating), and with persisted_state now backed by
# Upstash Redis, "reload from the cloud every rerun just to check"
# would burn roughly 17,280 GET commands a day from this one call site
# alone. See groq_client.py's own _outage_episode for the twin of this
# same fix (same shape, same root cause: "will this handle our
# volume ok?" traced live to ~3.3x over the free tier's 500k/month
# across the three call sites with this pattern). Mutated in place,
# only ever re-saved on a genuine change (a source going stale or
# recovering — rare, real events).
_stale_notified: set = set(persisted_state.load("data_health_stale", []))


def notify_stale(stale: list[dict]) -> None:
    """Pushes a phone notification once per source, per outage episode —
    not every rerun for as long as it stays stale, which could be hours
    or days once a source is genuinely down. Session request: "add
    meaningful outage alerts... if one of our sources go dark for a
    meaningful period of time" — THRESHOLDS_SECONDS above already is
    that "meaningful period" gate (3-36h depending on the source, not a
    few minutes' lateness), so nothing extra needed here beyond not
    re-pinging every rerun for the same ongoing outage.

    Tracks which source_keys have already been notified this episode via
    persisted_state (see _stale_notified above), not st.session_state or
    a plain process-local-only global — a session reset or a process
    restart (a redeploy, a Cloud sleep/wake) must never look like
    "nothing sent yet" for an outage still genuinely in progress. A
    source dropping out of `stale` (i.e. it recovered) clears its own
    flag, so a second, later outage on the same source gets its own
    fresh alert rather than staying silently suppressed forever because
    it already fired once months ago."""
    global _stale_notified
    notified = _stale_notified & {s["key"] for s in stale}  # drop any source that's since recovered
    for s in stale:
        if s["key"] in notified:
            continue
        notified.add(s["key"])
        ntfy_client.send(
            title="Data source down",
            message=f"{s['label']} hasn't updated in {s['hours_stale']:.0f}h.",
            priority="high",
            tags="warning",
        )
    if notified != _stale_notified:
        _stale_notified = notified
        persisted_state.save("data_health_stale", sorted(notified))
