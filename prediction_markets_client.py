"""Rolling, per-meeting central-bank rate-decision odds from Polymarket's
public search API — session request: "can we pull rate cut odds from cme
fedwatch" (CME's own FedWatch data turned out to be gated behind a paid,
OAuth-only commercial API, confirmed live: no public JSON/CSV endpoint the
way Baseball Savant's percentile leaderboard had) -> "what about rolling
rate odds from polymarket/kalshi that switches contracts after one
expires."

No API key, no auth: `gamma-api.polymarket.com/public-search` is a public
GET endpoint. Confirmed live that searching "<bank> Decision in" reliably
surfaces that bank's own clean per-meeting series — e.g. "Fed Decision in
September?", each one a 5-way market (50+ bps cut / 25 bps cut / no
change / 25 bps hike / 50+ bps hike) with a real `closed` flag and
`endDate`. "Rolling" is just: fetch that search, drop anything already
`closed`, sort what's left by `endDate`, and treat the earliest as
"current" — no hardcoded month/date logic needed at all. The instant
today's meeting closes, the same query naturally returns next month's as
the new earliest-open entry.

BANKS below is deliberately just Fed/BoC/BoJ, not every major central
bank — confirmed live that ECB and BoE don't currently have an actively-
maintained version of this same per-meeting series (their last
per-meeting markets found were stale by a year+; only annual "hike/cut in
2026" catch-all markets are currently open for them), so forcing them
into this same shape would either be wrong or need an entirely different
data treatment. Left out rather than faked.
"""

import json
import re

import requests
import streamlit as st

import fetch_throttle
import persisted_state

SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
# Odds for a scheduled meeting weeks out don't need to be fresher than
# this for a glance-at dashboard — real money re-prices these markets
# continuously, but nothing about this app's own display cadence needs
# to chase every tick.
CACHE_TTL_SECONDS = 20 * 60

BANKS = {
    "fed": "Fed Decision in",
    "boc": "Bank of Canada Decision in",
    "boj": "Bank of Japan Decision in",
}
BANK_LABELS = {"fed": "Federal Reserve", "boc": "Bank of Canada", "boj": "Bank of Japan"}

# Matched against each sub-market's own `question` text (not a fixed
# index — the API doesn't promise the 5 markets always come back in the
# same order). Order here is cut-to-hike, used as BUCKET_ORDER below for
# consistent display regardless of API ordering. Each question is
# entirely about one single scenario ("Will the Fed decrease interest
# rates by 50+ bps after..."), so a plain co-occurrence check (not a
# tight proximity regex) is safe — confirmed live a naive `decrease.{0,
# 15}50` gap missed every real question, since "decrease interest rates
# by " alone is 28 characters, well past any reasonably tight gap.
_BUCKET_PATTERNS = [
    ("cut_50", re.compile(r"decrease", re.I), re.compile(r"50", re.I)),
    ("cut_25", re.compile(r"decrease", re.I), re.compile(r"25", re.I)),
    ("hold", re.compile(r"no change", re.I), None),
    ("hike_25", re.compile(r"increase", re.I), re.compile(r"25", re.I)),
    ("hike_50", re.compile(r"increase", re.I), re.compile(r"50", re.I)),
]
BUCKET_ORDER = ["cut_50", "cut_25", "hold", "hike_25", "hike_50"]
BUCKET_LABELS = {
    "cut_50": "−50+bps",
    "cut_25": "−25bps",
    "hold": "No change",
    "hike_25": "+25bps",
    "hike_50": "+50+bps",
}


def _bucket_for_question(question: str) -> str | None:
    for bucket, primary, secondary in _BUCKET_PATTERNS:
        if primary.search(question) and (secondary is None or secondary.search(question)):
            return bucket
    return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_current_event_raw(bank: str, query: str) -> dict | None:
    fetch_throttle.wait_turn()
    resp = requests.get(SEARCH_URL, params={"q": query}, timeout=10)
    resp.raise_for_status()
    events = resp.json().get("events") or []
    # Title itself must actually contain "Decision in" too — public-
    # search is a fuzzy text match, not an exact filter, so this guards
    # against a loosely-related result slipping into "current" (nothing
    # observed live so far, but cheap insurance against a future change
    # in Polymarket's own search ranking).
    open_events = [e for e in events if not e.get("closed") and e.get("endDate") and "decision in" in (e.get("title") or "").lower()]
    if not open_events:
        return None
    open_events.sort(key=lambda e: e["endDate"])
    return open_events[0]


def _parse_event(event: dict) -> dict | None:
    outcomes = {}
    for m in event.get("markets") or []:
        bucket = _bucket_for_question(m.get("question") or "")
        if bucket is None:
            continue
        try:
            prices = json.loads(m.get("outcomePrices") or "[]")
            outcomes[bucket] = float(prices[0])
        except (ValueError, IndexError, TypeError):
            continue
    # Fewer than 3 of the 5 buckets parsed means something about the
    # question wording changed enough that this reading can't be
    # trusted — safer to fall back to the last good snapshot than show
    # a visibly-incomplete breakdown.
    if len(outcomes) < 3:
        return None
    return {"title": event.get("title"), "end_date": event.get("endDate"), "outcomes": outcomes}


_last_good: dict[str, dict] = {}


def current_odds(bank: str) -> dict | None:
    """{"title", "end_date", "outcomes": {bucket: probability, ...}} for
    the nearest still-open rate-decision meeting for `bank` (one of
    BANKS' own keys) — rolls to the next meeting automatically the
    moment the current one closes. None if nothing usable has ever come
    back for this bank."""
    query = BANKS.get(bank)
    if query is None:
        return None
    try:
        event = _fetch_current_event_raw(bank, query)
    except Exception:
        return _last_good.get(bank)
    if event is None:
        return _last_good.get(bank)
    parsed = _parse_event(event)
    if parsed is None:
        return _last_good.get(bank)
    _last_good[bank] = parsed
    return parsed


def most_likely_outcome(odds: dict) -> tuple[str, float]:
    """(bucket, probability) for whichever bucket the market currently
    rates most likely."""
    return max(odds["outcomes"].items(), key=lambda kv: kv[1])


# Session request: surface a toast when the market's own view shifts in
# a way actually worth knowing about — either the leading bucket
# outright flips (the market's consensus call on the meeting changed),
# or the leading bucket's own probability moves by a real amount without
# flipping. 12 points is comfortably above the day-to-day noise a liquid
# rate-decision market shows on its own, matching the same "a full
# percentage point is a real single-session move" reasoning
# govee_lighting.MARKET_SIGNIFICANT_MOVE already uses for the room
# light, scaled up since this is a probability, not a price return.
SWING_THRESHOLD = 0.12

# Loaded once at import, saved only on a genuine change (see
# check_for_swing below) — same persisted-cache shape this session's own
# news.py/commute_reminder.py fixes already established, not a repeat of
# either mistake: no per-rerun load, and no save unless the snapshot
# actually differs from what's already on record.
_last_seen: dict[str, dict] = persisted_state.load("prediction_market_last_seen", {})


def check_for_swing(bank: str) -> dict | None:
    """None most of the time. A dict describing a real move
    ({"bank", "kind": "flip"|"shift", "bucket", "prob", "prev_bucket"/
    "prev_prob"}) the first time this bank's leading outcome has moved
    meaningfully since the last time this was called — including the
    special case of the market's consensus bucket flipping outright,
    which always counts regardless of magnitude. Never fires on the
    very first read for a bank (nothing to compare against yet) or
    right after rolling to a new meeting (a fresh contract starting
    somewhere isn't a "shift" from the old one's last reading)."""
    odds = current_odds(bank)
    if odds is None:
        return None
    bucket, prob = most_likely_outcome(odds)
    snapshot = {"title": odds["title"], "bucket": bucket, "prob": round(prob, 4)}
    prev = _last_seen.get(bank)
    if prev == snapshot:
        return None
    _last_seen[bank] = snapshot
    persisted_state.save("prediction_market_last_seen", _last_seen)
    if prev is None or prev["title"] != snapshot["title"]:
        return None
    if prev["bucket"] != bucket:
        return {"bank": bank, "title": odds["title"], "kind": "flip", "bucket": bucket, "prob": prob, "prev_bucket": prev["bucket"]}
    if abs(prob - prev["prob"]) >= SWING_THRESHOLD:
        return {"bank": bank, "title": odds["title"], "kind": "shift", "bucket": bucket, "prob": prob, "prev_prob": prev["prob"]}
    return None


def swing_alert(swing: dict) -> dict:
    """Turns a check_for_swing() result into the same {"headline",
    "category", "important"} shape every other toast source in this app
    produces (news.py, weather_alerts_bar.py, ...) — kept here rather
    than built inline in app.py so the actual wording lives next to the
    data it describes, same reasoning commute_reminder._leave_text has
    for owning its own phrasing."""
    bank_label = BANK_LABELS[swing["bank"]]
    bucket_label = BUCKET_LABELS[swing["bucket"]]
    prob_pct = round(swing["prob"] * 100)
    if swing["kind"] == "flip":
        prev_label = BUCKET_LABELS[swing["prev_bucket"]]
        headline = f"{bank_label}: market now leans {bucket_label} ({prob_pct}%), was {prev_label}"
    else:
        prev_pct = round(swing["prev_prob"] * 100)
        headline = f"{bank_label}: {bucket_label} odds jump to {prob_pct}% (from {prev_pct}%)"
    return {"headline": headline, "category": "Rate Odds", "important": swing["kind"] == "flip"}
