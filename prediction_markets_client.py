"""Rolling, per-meeting central-bank rate-decision odds from Polymarket's
public search API — session request: "can we pull rate cut odds from cme
fedwatch" (CME's own FedWatch data turned out to be gated behind a paid,
OAuth-only commercial API, confirmed live: no public JSON/CSV endpoint the
way Baseball Savant's percentile leaderboard had) -> "what about rolling
rate odds from polymarket/kalshi that switches contracts after one
expires" -> once shipped for just Fed/BoC/BoJ: "I want all of the rate
odds as many as you can find... if that means finding a proper source
for ECB or including other countries [beyond] more than three, I want
them all."

No API key, no auth: `gamma-api.polymarket.com/public-search` is a public
GET endpoint. Confirmed live that a bank-specific search query reliably
surfaces that bank's own per-meeting series with a real `closed` flag and
`endDate`. "Rolling" is just: fetch that search, drop anything already
`closed`, sort what's left by `endDate`, and try each in order until one
actually parses as a rate-decision market — no hardcoded month/date logic
needed at all, and no reliance on a single fixed title wording either
(see BANKS' own comment: title conventions genuinely differ bank to
bank). The instant today's meeting closes, the same query naturally
returns next month's as the new earliest-open entry.

Two market shapes confirmed live, both handled by the same
_bucket_for_question: most banks (Fed, BoC, BoJ, ECB, BoE, RBA, RBNZ,
Mexico, RBI, Korea, Brazil) run a 5-way market — 50+/25 bps either
direction, or no change. Two (Bank of Israel, South African Reserve
Bank) only run a plain 3-way cut/hold/hike, no bps-level detail — a
genuinely coarser market, not a parsing gap, so those banks' `outcomes`
dict just comes back with "cut"/"hold"/"hike" keys instead of the usual
five.

Checked and found NOT to have a currently-open version of this same
per-meeting series, so deliberately left out rather than faked: Swiss
National Bank, Norges Bank (Norway), PBoC (China), Bank Indonesia,
Turkey's CBRT, Riksbank (Sweden) — each either has no live rate-decision
market on Polymarket at all right now, or (Turkey) only unrelated
political/military markets came back for the same search terms.
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

# bank key -> (search query, display name, country/region). Query
# strings are each individually confirmed live to surface that bank's
# real, currently-open per-meeting market — title WORDING genuinely
# varies (e.g. ECB's own series is titled "ECB Interest Rates: <Month>
# <Year>", not "<Bank> Decision in <Month>?" the way most others are),
# which is exactly why current_odds() below validates structurally
# (does it parse into a real rate-decision shape) rather than by
# matching a fixed title pattern.
BANKS = {
    "fed": ("Fed Decision in", "Federal Reserve", "United States"),
    "ecb": ("ECB Interest Rates", "European Central Bank", "Eurozone"),
    "boe": ("Bank of England Decision in", "Bank of England", "United Kingdom"),
    "boj": ("Bank of Japan Decision in", "Bank of Japan", "Japan"),
    "boc": ("Bank of Canada Decision in", "Bank of Canada", "Canada"),
    "rba": ("Reserve Bank of Australia Decision in", "Reserve Bank of Australia", "Australia"),
    "rbnz": ("RBNZ Decision in", "Reserve Bank of New Zealand", "New Zealand"),
    "banxico": ("Bank of Mexico Decision in", "Bank of Mexico", "Mexico"),
    "rbi": ("Reserve Bank of India Decision in", "Reserve Bank of India", "India"),
    "boi": ("Bank of Israel Decision in", "Bank of Israel", "Israel"),
    "sarb": ("South African Reserve Bank Decision in", "South African Reserve Bank", "South Africa"),
    "bok": ("Bank of Korea Decision in", "Bank of Korea", "South Korea"),
    "bcb": ("Bank of Brazil Decision in", "Bank of Brazil", "Brazil"),
}
BANK_LABELS = {key: label for key, (_, label, _) in BANKS.items()}
BANK_COUNTRIES = {key: country for key, (_, _, country) in BANKS.items()}

# Matched against each sub-market's own `question` text (not a fixed
# index — the API doesn't promise the markets always come back in the
# same order). Each question is entirely about one single scenario
# ("Will the Fed decrease interest rates by 50+ bps after..."), so a
# plain co-occurrence check (not a tight proximity regex) is safe —
# confirmed live a naive `decrease.{0,15}50` gap missed every real
# question, since "decrease interest rates by " alone is 28 characters,
# well past any reasonably tight gap. Two genuinely different wordings
# confirmed live across banks — most use "decrease"/"no change"/
# "increase" (Fed, ECB, BoC, BoJ, ...), Bank of Korea instead uses a
# plain "cut"/"hold"/"hike" phrasing ("Will the Bank of Korea cut by 25
# bps at the August 2026 meeting?") — both checked for every bucket
# rather than assuming one convention app-wide.
_DECREASE_WORDS = re.compile(r"decrease|\bcut\b", re.I)
_INCREASE_WORDS = re.compile(r"increase|\bhike\b", re.I)
_HOLD_WORDS = re.compile(r"no change|\bhold\b", re.I)
_BUCKET_PATTERNS = [
    ("cut_50", _DECREASE_WORDS, re.compile(r"50", re.I)),
    ("cut_25", _DECREASE_WORDS, re.compile(r"25", re.I)),
    ("hold", _HOLD_WORDS, None),
    ("hike_25", _INCREASE_WORDS, re.compile(r"25", re.I)),
    ("hike_50", _INCREASE_WORDS, re.compile(r"50", re.I)),
]
BUCKET_ORDER = ["cut_50", "cut_25", "cut", "hold", "hike_25", "hike_50", "hike"]
BUCKET_LABELS = {
    "cut_50": "−50+bps",
    "cut_25": "−25bps",
    "cut": "Cut",
    "hold": "No change",
    "hike_25": "+25bps",
    "hike_50": "+50+bps",
    "hike": "Hike",
}
# Session request: color the direction, not each individual bucket —
# "CUT in ice blue, hold just normal, hike is fire red." Collapses the
# fine-grained 50/25-bps buckets down to the three directions a display
# actually wants to color.
_BUCKET_DIRECTION = {
    "cut_50": "cut", "cut_25": "cut", "cut": "cut",
    "hold": "hold",
    "hike_25": "hike", "hike_50": "hike", "hike": "hike",
}


def bucket_direction(bucket: str) -> str:
    """"cut"/"hold"/"hike" for any bucket key, collapsing away the
    50/25-bps detail some banks carry and others don't."""
    return _BUCKET_DIRECTION[bucket]


def _bucket_for_question(question: str) -> str | None:
    for bucket, primary, secondary in _BUCKET_PATTERNS:
        if primary.search(question) and (secondary is None or secondary.search(question)):
            return bucket
    # No bps-level detail in this question — a coarser 3-way market
    # (Bank of Israel, South African Reserve Bank). "no change"/"hold"
    # is already caught above regardless of detail level, so this only
    # ever needs to catch a bare decrease/cut or increase/hike.
    if _DECREASE_WORDS.search(question):
        return "cut"
    if _INCREASE_WORDS.search(question):
        return "hike"
    return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _search_raw(query: str) -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(SEARCH_URL, params={"q": query}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("events") or []


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
    # Fewer than 3 recognized buckets means either this isn't really a
    # rate-decision market (a loosely-related search result — public-
    # search is fuzzy text matching, not an exact filter) or something
    # about the question wording changed enough that this reading can't
    # be trusted — either way, safer to skip it than show a visibly-
    # incomplete breakdown. 3 covers both real shapes: all of a 3-way
    # market, or a majority of a 5-way one.
    if len(outcomes) < 3:
        return None
    return {"title": event.get("title"), "end_date": event.get("endDate"), "outcomes": outcomes}


_last_good: dict[str, dict] = {}


def current_odds(bank: str) -> dict | None:
    """{"title", "end_date", "outcomes": {bucket: probability, ...}} for
    the nearest still-open rate-decision meeting for `bank` (one of
    BANKS' own keys) — rolls to the next meeting automatically the
    moment the current one closes. Tries every still-open search result
    in end-date order, not just the earliest, so one loosely-related
    result that doesn't actually parse as a rate-decision market (fuzzy
    text search, not an exact filter) doesn't block a real one further
    down the list. None if nothing usable has ever come back for this
    bank."""
    entry = BANKS.get(bank)
    if entry is None:
        return None
    query = entry[0]
    try:
        events = _search_raw(query)
    except Exception:
        return _last_good.get(bank)
    open_events = sorted(
        (e for e in events if not e.get("closed") and e.get("endDate")),
        key=lambda e: e["endDate"],
    )
    for event in open_events:
        parsed = _parse_event(event)
        if parsed is not None:
            _last_good[bank] = parsed
            return parsed
    return _last_good.get(bank)


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
