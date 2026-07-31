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
# Session request: "instead of having their acronym... just have their
# flag" — lowercase ISO codes for flags.flag_for(), one per bank. "eu"
# for the ECB isn't a real ISO country code, but it's the flags.py key
# already chosen for the EU flag itself, and there's no single country
# a shared central bank could honestly point to instead.
BANK_FLAG_CODES = {
    "fed": "us", "ecb": "eu", "boe": "gb", "boj": "jp", "boc": "ca",
    "rba": "au", "rbnz": "nz", "banxico": "mx", "rbi": "in", "boi": "il",
    "sarb": "za", "bok": "kr", "bcb": "br",
}

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
    "cut_50": "Cut",
    "cut_25": "Cut",
    "cut": "Cut",
    "hold": "No change",
    "hike_25": "Hike",
    "hike_50": "Hike",
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
    # Found live while adding the macro-data-print series below: the
    # endpoint defaults to just 5 events with no limit_per_type param,
    # and fuzzy relevance ranking doesn't reliably put the one
    # currently-open event in that top 5 (confirmed: "How many jobs
    # added" without this came back with 5 closed months and not the
    # open one). 20 comfortably covers a year+ of monthly history for
    # any single series without this becoming a heavier request.
    resp = requests.get(SEARCH_URL, params={"q": query, "limit_per_type": 20}, timeout=10)
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
# actually differs from what's already on record. Per-instance (session
# request: "every single toast we get... every terminal gets its own
# alert") — this is exactly the mechanism the real BoE-headline incident
# traced back to for news.py; same fix here so a swing toast for one
# instance doesn't silently block every other instance from getting its
# own.
_last_seen: dict[str, dict] = persisted_state.load_per_instance("prediction_market_last_seen", {})


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
    persisted_state.save_per_instance("prediction_market_last_seen", _last_seen)
    if prev is None or prev["title"] != snapshot["title"]:
        return None
    if prev["bucket"] != bucket:
        return {"bank": bank, "title": odds["title"], "kind": "flip", "bucket": bucket, "prob": prob, "prev_bucket": prev["bucket"]}
    if abs(prob - prev["prob"]) >= SWING_THRESHOLD:
        return {"bank": bank, "title": odds["title"], "kind": "shift", "bucket": bucket, "prob": prob, "prev_prob": prev["prob"]}
    return None


# --- Rolling macro-data-print markets (CPI, unemployment) --------------
# Session follow-up, after picking CPI + unemployment as the two most
# useful things to add beyond central banks: "pull the consensus...
# build a forecast or a forecasted value based on the value of the
# prediction markets themselves... estimate if it's gonna be coming in
# cooler or hotter than expected." Checked this repo first: there is no
# economist-consensus figure anywhere (fred_client.py/indicators.py only
# ever compute the actual reported value, never a forecast) — so
# "expected" here means the last actual FRED reading, and "hotter"/
# "cooler" is the market's own next-print forecast relative to what
# already printed last time, not a Wall Street consensus poll this app
# has no free source for.
#
# Different market shape than the bank-decision ones above: Polymarket
# runs one event per calendar month, and *within* that event, one binary
# sub-market per specific point value ("Will the July 2026 unemployment
# rate be 4.2%?") rather than a handful of named buckets. So the
# "forecast" isn't a single most-likely bucket — it's a probability-
# weighted average across every point value the event covers, a much
# better summary of a distribution spread across 8-12 adjacent buckets
# than picking just the single largest one.
#
# Session follow-up #2: "instead of having two of them that are kinda
# random... find data for Canada as well... have the next closest event
# show up automatically... across Canada and the US." Checked live:
# Canada's monthly CPI/unemployment series (matching the US's cadence
# and per-point-value shape) has gone dormant — nothing currently open
# past Dec 2025/Feb 2026 — so `ca_unemployment` below is kept configured
# but will legitimately come back `None` from current_data_forecast()
# until Polymarket reopens a real one, same "don't fake it" rule this
# file's own module docstring already applies to central banks with no
# live market. Canada DOES have one open series right now, just a
# coarser annual aggregate ("Canada Annual Inflation 2026", range-
# bucketed rather than point-value) — included honestly labeled as
# "(Annual)" rather than passed off as the same monthly-YoY shape the US
# entries are.
#
# Session follow-up #3: "is there anything more outside of just the
# basic stuff... unemployment rate, CPI, GDP, etc.?" Checked live and
# confirmed 6 more genuinely open, cleanly-parseable US markets: Core
# PCE (the Fed's own preferred inflation gauge), ISM Manufacturing PMI,
# ISM Services PMI, Non-Farm Payrolls ("How many jobs added"), UMich
# Consumer Sentiment, and a real quarterly GDP-growth market. Not every
# one gets a "last actual" FRED comparison, though — reading_key is None
# for whichever ones have no honest actual-value baseline available in
# this app (ISM is proprietary data with no free FRED series; Non-Farm
# Payrolls' and GDP's own FRED series exist but need a diff/annualized
# transform this app doesn't otherwise have a use for). Those render as
# a plain market-forecast box instead of faking a hotter/cooler call
# against a baseline that isn't real — see pages_predictions.py's
# _macro_hero_html.
DATA_SERIES = {
    "us_cpi": {
        "query": "Inflation US Annual",
        "label": "CPI (YoY)",
        "country": "United States",
        # Matches "<Month> Inflation US - Annual", not the
        # "(Higher Brackets)" duplicate some already-closed months
        # also carry.
        "title_pattern": re.compile(r"Inflation US - Annual$"),
        "unit": "%",
        "reading_key": ("us", "cpi"),
    },
    "us_unemployment": {
        "query": "Unemployment Rate",
        "label": "Unemployment Rate",
        "country": "United States",
        # Matches "<Month> Unemployment Rate" only — excludes the
        # per-country variants ("... - Japan", "... - Mexico") the same
        # search also surfaces.
        "title_pattern": re.compile(r"^[A-Za-z]+ Unemployment Rate$"),
        "unit": "%",
        "reading_key": ("us", "unemployment"),
    },
    "us_core_pce": {
        "query": "Core PCE YoY",
        "label": "Core PCE (YoY)",
        "country": "United States",
        "title_pattern": re.compile(r"^Core PCE YoY - "),
        "unit": "%",
        # Not in config.py's INDICATORS (that would also add a tile to
        # the Home page and a ticker item, well beyond what was asked
        # for here) — fetched directly, see pages_predictions.py's
        # _EXTRA_FRED_SERIES.
        "reading_key": None,
        "fred_series": ("PCEPILFE", "yoy"),
    },
    "us_ism_manufacturing": {
        "query": "ISM Manufacturing PMI",
        "label": "ISM Manufacturing PMI",
        "country": "United States",
        "title_pattern": re.compile(r"^ISM Manufacturing PMI - "),
        "unit": "",
        "reading_key": None,
        "decimals": 1,
    },
    "us_ism_services": {
        "query": "ISM Services PMI",
        "label": "ISM Services PMI",
        "country": "United States",
        "title_pattern": re.compile(r"^ISM Services PMI - "),
        "unit": "",
        "reading_key": None,
        "decimals": 1,
    },
    "us_nonfarm_payrolls": {
        "query": "How many jobs added",
        "label": "Nonfarm Payrolls",
        "country": "United States",
        "title_pattern": re.compile(r"^How many jobs added in \w+\??$"),
        "unit": "k jobs",
        "reading_key": None,
        "decimals": 0,
    },
    "us_umich_sentiment": {
        "query": "University of Michigan Consumer Sentiment",
        "label": "Consumer Sentiment (UMich)",
        "country": "United States",
        "title_pattern": re.compile(r"^University of Michigan Consumer Sentiment - "),
        "unit": "",
        "reading_key": None,
        "fred_series": ("UMCSENT", "level"),
        "decimals": 1,
    },
    "us_gdp_growth": {
        "query": "US GDP growth",
        "label": "GDP Growth (QoQ)",
        "country": "United States",
        "title_pattern": re.compile(r"^US GDP growth in Q\d 20\d\d\??$"),
        "unit": "%",
        "reading_key": None,
        "decimals": 1,
    },
    "ca_cpi": {
        "query": "Canada Annual Inflation",
        "label": "CPI (Annual)",
        "country": "Canada",
        "title_pattern": re.compile(r"^Canada Annual Inflation \d{4}$"),
        "unit": "%",
        "reading_key": ("ca", "cpi"),
    },
    "ca_unemployment": {
        "query": "Unemployment Rate Canada",
        "label": "Unemployment Rate",
        "country": "Canada",
        "title_pattern": re.compile(r"Unemployment Rate - Canada$"),
        "unit": "%",
        "reading_key": ("ca", "unemployment"),
    },
}


# Requires an actual decimal point rather than a trailing "%" — index-
# level series (ISM PMI, UMich Sentiment) state their thresholds as
# bare decimals ("below 49.0", no percent sign at all), so a "%"
# requirement silently zeroed out every point for those. Requiring the
# decimal point instead of dropping the check entirely is what keeps
# this safe: it still won't match a bare year like "2026" or "2027"
# that shows up in some questions' own wording, since those never carry
# a decimal point.
_VALUE_RE = re.compile(r"(\d+\.\d+)")


def _value_for_question(question: str) -> float | None:
    """The bucket's own represented value — the single number for a
    point-value question ("...be 4.2%?"), or the midpoint for a range
    question ("...between 2.5% and 2.9%?", Canada's coarser annual
    market uses this shape). Tail buckets ("...at least 4.0%?") fall
    back to their one boundary number, same approximation _parse_event
    doesn't need but this distribution-average approach does."""
    values = [float(x) for x in _VALUE_RE.findall(question)]
    return sum(values) / len(values) if values else None


# Non-Farm Payrolls questions are phrased in thousands of jobs, not a
# percentage ("...add between 0 and 50k jobs..."), and carry one bucket
# with no number at all ("Will the US lose jobs in July?"). -50
# (thousand) is a representative stand-in for that bucket — an
# approximation, not a real reported figure, since the question itself
# gives no magnitude for a loss, but this bucket's own probability is
# usually small enough that the approximation barely moves the overall
# weighted average.
_NFP_VALUE_RE = re.compile(r"(\d+)k?\b")


def _value_for_nfp_question(question: str) -> float | None:
    if re.search(r"lose jobs", question, re.I):
        return -50.0
    values = [float(x) for x in _NFP_VALUE_RE.findall(question)]
    return sum(values) / len(values) if values else None


_VALUE_PARSERS = {"us_nonfarm_payrolls": _value_for_nfp_question}


def _parse_data_event(event: dict, value_fn) -> dict | None:
    points = []
    for m in event.get("markets") or []:
        value = value_fn(m.get("question") or "")
        if value is None:
            continue
        try:
            prices = json.loads(m.get("outcomePrices") or "[]")
            points.append((value, float(prices[0])))
        except (ValueError, IndexError, TypeError):
            continue
    # Same "at least 3 recognized points" guard as _parse_event above —
    # fuzzy search can surface an unrelated event, or question wording
    # can drift enough that this reading shouldn't be trusted.
    if len(points) < 3:
        return None
    total_prob = sum(p for _, p in points)
    if total_prob <= 0:
        return None
    forecast = sum(v * p for v, p in points) / total_prob
    return {"title": event.get("title"), "end_date": event.get("endDate"), "forecast": forecast, "points": points}


_last_good_series: dict[str, dict] = {}


def current_data_forecast(series: str) -> dict | None:
    """{"title", "end_date", "forecast", "points"} — the market's own
    probability-weighted point forecast for the next print of `series`
    (a DATA_SERIES key), rolling to the next month's event the same way
    current_odds() rolls to the next meeting."""
    cfg = DATA_SERIES.get(series)
    if cfg is None:
        return None
    try:
        events = _search_raw(cfg["query"])
    except Exception:
        return _last_good_series.get(series)
    open_events = sorted(
        (
            e for e in events
            if not e.get("closed") and e.get("endDate") and cfg["title_pattern"].search(e.get("title") or "")
        ),
        key=lambda e: e["endDate"],
    )
    value_fn = _VALUE_PARSERS.get(series, _value_for_question)
    for event in open_events:
        parsed = _parse_data_event(event, value_fn)
        if parsed is not None:
            _last_good_series[series] = parsed
            return parsed
    return _last_good_series.get(series)


def next_data_series() -> str | None:
    """Whichever DATA_SERIES key has the soonest still-open, actually-
    parseable print across every tracked country/series right now —
    session request: "have the next closest event show up automatically
    on that page across Canada and the US," instead of a fixed pair.
    None if nothing across the whole roster currently parses (e.g. every
    series' market happens to be between contracts at the same moment)."""
    candidates = []
    for series in DATA_SERIES:
        forecast = current_data_forecast(series)
        if forecast and forecast.get("end_date"):
            candidates.append((forecast["end_date"], series))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


# Below this, a print reads as flat/"in-line" rather than hotter or
# cooler — real CPI/unemployment prints move in 0.1-point increments, so
# anything tighter than half of that is noise, not a signal worth
# calling out.
_IN_LINE_THRESHOLD = 0.05


def forecast_vs_last_actual(series: str, last_actual: float | None) -> dict | None:
    """The market's own next-print forecast for `series` compared
    against the last actual FRED reading (there's no economist-
    consensus figure anywhere in this app to compare against instead) —
    {"title", "end_date", "forecast", "points", "last_actual", "delta",
    "direction"} where direction is "hotter"/"cooler"/"in-line". None if
    either side of the comparison isn't available yet."""
    forecast_data = current_data_forecast(series)
    if forecast_data is None or last_actual is None:
        return None
    delta = forecast_data["forecast"] - last_actual
    if abs(delta) < _IN_LINE_THRESHOLD:
        direction = "in-line"
    elif delta > 0:
        direction = "hotter"
    else:
        direction = "cooler"
    return {**forecast_data, "last_actual": last_actual, "delta": delta, "direction": direction}


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


# --- Weekend market-close forecast (SPY, WTI Crude Oil) -----------------
# Session request: "instead of using crypto as a proxy for weekend
# sentiment, can we use [polymarket.com/event/spy-closes-above-on-
# july-30-2026]? And then find that same contract for... the Nasdaq and
# the Dow and gold and crude oil." Checked live: this "closes above $X"
# daily contract family only actually exists for SPY and WTI Crude Oil —
# Nasdaq, Dow, and Gold don't have a matching contract on Polymarket at
# all (only individual mega-cap stocks otherwise run this same shape),
# so only those two are built here rather than faking the other three.
#
# Genuinely different market shape from every series above: each
# sub-market is an independent "will it close above $X" question, not a
# set of mutually-exclusive named buckets — a survival function P(close
# > X) sampled at a handful of strikes, not a probability distribution
# that sums to 1 on its own. Turning that into a single expected-close
# forecast means decomposing consecutive strikes into bucket
# probabilities first (P(strike_i < close <= strike_i+1) = P(close >
# strike_i) - P(close > strike_i+1)), then the same probability-weighted
# midpoint average the macro-print forecasts above already use.
CLOSE_SERIES = {
    "spy": {
        "query": "S&P 500 (SPY) closes above",
        "label": "S&P 500 (SPY)",
        "yf_symbol": "SPY",
    },
    "wti": {
        "query": "WTI Crude Oil (WTI) closes above",
        "label": "WTI Crude Oil",
        "yf_symbol": "CL=F",
    },
}

_THRESHOLD_RE = re.compile(r"\$(\d+\.?\d*)")


def _threshold_for_question(question: str) -> float | None:
    m = _THRESHOLD_RE.search(question)
    return float(m.group(1)) if m else None


def _parse_close_event(event: dict) -> dict | None:
    points = []
    for m in event.get("markets") or []:
        threshold = _threshold_for_question(m.get("question") or "")
        if threshold is None:
            continue
        try:
            prices = json.loads(m.get("outcomePrices") or "[]")
            points.append((threshold, float(prices[0])))
        except (ValueError, IndexError, TypeError):
            continue
    if len(points) < 3:
        return None
    points.sort(key=lambda p: p[0])
    # A real survival function is non-increasing as the strike rises —
    # confirmed live that SPY's own far, thin strikes quote noisily
    # (probability actually went UP at a higher strike at one snapshot),
    # which would otherwise hand a bucket a negative probability mass
    # below. Clamping each strike's probability to the running minimum
    # seen so far from the low end keeps the curve well-behaved without
    # discarding those strikes outright.
    cleaned = []
    running_min = 1.0
    for threshold, prob in points:
        running_min = min(prob, running_min)
        cleaned.append((threshold, running_min))
    total = 0.0
    weighted = 0.0
    lo_threshold, lo_prob = cleaned[0]
    below_prob = 1.0 - lo_prob
    total += below_prob
    weighted += below_prob * lo_threshold
    for (t0, p0), (t1, p1) in zip(cleaned, cleaned[1:]):
        bucket_prob = p0 - p1
        total += bucket_prob
        weighted += bucket_prob * (t0 + t1) / 2
    hi_threshold, hi_prob = cleaned[-1]
    total += hi_prob
    weighted += hi_prob * hi_threshold
    if total <= 0:
        return None
    forecast = weighted / total
    return {"title": event.get("title"), "end_date": event.get("endDate"), "forecast": forecast}


_last_good_close: dict[str, dict] = {}


def current_close_forecast(series: str) -> dict | None:
    """{"title", "end_date", "forecast"} — the market's own
    probability-weighted expected close for `series` (a CLOSE_SERIES
    key), rolling to the next still-open day's contract the same way
    current_odds() rolls to the next meeting."""
    cfg = CLOSE_SERIES.get(series)
    if cfg is None:
        return None
    try:
        events = _search_raw(cfg["query"])
    except Exception:
        return _last_good_close.get(series)
    open_events = sorted(
        (e for e in events if not e.get("closed") and e.get("endDate")),
        key=lambda e: e["endDate"],
    )
    for event in open_events:
        parsed = _parse_close_event(event)
        if parsed is not None:
            _last_good_close[series] = parsed
            return parsed
    return _last_good_close.get(series)


def close_forecast_return(series: str, last_close: float | None) -> dict | None:
    """The market's own expected-close forecast for `series` turned into
    a plain return % against `last_close` (the caller's job to supply —
    typically the last actual trading session's close, e.g. Friday's
    4pm print over a weekend) — {"title", "end_date", "forecast",
    "last_close", "pct_return"}. None if either side isn't available."""
    forecast_data = current_close_forecast(series)
    if forecast_data is None or not last_close:
        return None
    pct_return = (forecast_data["forecast"] - last_close) / last_close * 100
    return {**forecast_data, "last_close": last_close, "pct_return": pct_return}
