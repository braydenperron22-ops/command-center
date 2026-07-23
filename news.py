"""RSS-based news — powers breaking-news alerts AND the News page's
rolling 24h feed, plus (via is_clickbait) a shared pre-filter for the
Conflicts page.

No API key for the feeds themselves: pulls from the Fed's own
press-release feed (zero-noise, it IS the source) plus a few general
finance RSS feeds. The breaking-news bar uses the exact same `decide()`
verdict as the News page — it's the same headline pool, just surfaced
immediately as each one first appears rather than waiting to be read on
the News page.

Every headline's fate — show it at all, and if so Breaking or Market —
used to be decided by a hand-tuned keyword pipeline, then by an AI call
per individual headline as each one arrived. Session feedback moved
this again: "im only getting slop red headlines rn. maybe ping the ai
every five minutes to find genuine headlines and only have them shown
through the ai." Per-headline AI calls turned out to have the same
failure mode as the keyword system whenever the free tier's per-minute
limit got hit mid-burst — a real headline's decide() call would fail
and silently fall back to the old, much looser keyword pipeline, which
is exactly where the "slop" was coming from. That led to batching
(_build_batch_prompt, then BATCH_REFRESH_SECONDS/BATCH_MAX_HEADLINES,
long since renamed away) — one Groq call for every pending headline at
once, first every 5, then every 30 minutes as cost concerns grew.

Reversed again, later the same day: "transition feed processing from
15-minute batching to 1-minute polling so news is processed instantly
as it drops... stream headlines through the classifier individually
so notifications fire in real-time... rather than in periodic bursts."
_run_individual_decide() now classifies each pending headline with its
own real Groq call, polling every INDIVIDUAL_REFRESH_SECONDS (60s)
rather than batching — told directly this costs meaningfully more per
headline (each one now pays the full judgment-criteria overhead alone,
confirmed live at roughly 4x the overhead tokens for the same headline
volume, on the account that had already hit its daily cap once that
same day) and chosen anyway. Crucially, the ORIGINAL reason per-
headline calls got abandoned no longer applies: there is still no
keyword-based fallback — a failed individual call just leaves that one
headline pending, retried on the next tick, never "shown anyway" via
looser rules the way the old slop happened. decide() is still a pure
cache lookup, no network call, no fallback; "only have them shown
through the ai" still means exactly that, per-headline now instead of
per-batch. is_clickbait and the term lists it depends on are the one
piece of the old keyword system kept, since conflict_news.py separately
reuses it as a pre-filter before its own AI overview.

decide() also carries the display headline itself, possibly rewritten
by the AI — session feedback: "theres a lot of headlines who dont tell
me a whole lot... wiston shares surge (by how much???)... I need
numbers, context, and data in a short concise headline." Real feeds'
<description> is often the only place the actual number lives
(sometimes it's empty — Yahoo Finance never sets one — or just a
duplicate of the title), so _run_individual_decide also fetches each
pending headline's own full article page (_fetch_article_excerpt) as
extra grounding beyond the thin RSS summary — session follow-up: "make
it look at the full story for a more detailed headline." Even that can
come up empty (a genuinely thin wire piece, a fetch a site blocked).
In that case the rule is strict, not permissive — session correction:
"if they cant find anything to make the headline unactionable then
dont allow it... if you dont have a number you better have a good
reason for letting it through." A headline only survives without a
real number if its own core claim is already a single, concrete,
unambiguous event (see _CLASSIFICATION_CRITERIA for exactly where that
line is drawn, shared word-for-word by the batch and single-headline
prompt builders) — a headline that's vague on both counts gets
REJECTed outright, not shown vague. Numbers are still never invented,
estimated, or recalled from the model's own training knowledge — a
confidently wrong figure would be worse than dropping the headline
entirely.
"""

import functools
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from bs4 import BeautifulSoup

import data_health
import fetch_throttle
import groq_client
import ntfy_client
import persisted_state
from config import TIMEZONE, TOP_ALERT_HOLD_SECONDS

# (feed URL, display name) — unlike the Conflicts page's Google News
# search (which already gets a " - Publisher" suffix baked into every
# title by Google), these feeds' own <title> tags carry no source
# attribution at all, so it has to come from knowing which feed it was.
#
# The Federal Reserve's own press-release feed
# (federalreserve.gov/feeds/press_all.xml) used to be here — session
# request: "these three fed headlines i want them completely gone, i
# dont want you to pull directly from the fed anymore, theyve been
# showing up since day 1." Its content is administrative/regulatory
# press releases (enforcement actions, routine data reports), not
# market news, and apparently never cleared the AI's own relevance bar
# either way — removed as a source outright rather than trying to
# filter it more aggressively. Real Fed news (rate decisions, etc.)
# still comes through normally via CNBC/MarketWatch/Yahoo reporting on
# it, same "Fed/BoC" category as always — this only removes the Fed's
# own direct feed as a source, not Fed coverage in general.
FEEDS = [
    ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "CNBC"),
    ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
    ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
]

TOAST_SECONDS = 30
# Cap for get_new_alerts()'s "seen headline hashes" tracker — see its
# own comment for why this needs a bound at all on a kiosk session that
# can run for weeks. 500 comfortably covers many days of real headline
# volume across all 4 feeds combined at ~20-40 bytes/hash.
MAX_SEEN_HEADLINES = 500

# Intro sequencing: "BREAKING NEWS" stretches into view, holds, then slides
# aside to reveal the headline underneath, via the toast-label-intro/
# toast-headline-intro CSS animations in theme.py — elapsed feeds a
# negative animation-delay (see render_alert_bar) so the clip resumes at
# the right point every rerun and then plays smoothly on its own via the
# browser's render loop until the next one, rather than a plain keyframe
# animation restarting from 0% on every rerun's fresh DOM node.
STRETCH_END = 1.8
SLIDE_END = 3.0

# name/ticker variant -> canonical ticker symbol. A dict, not a flat
# list, so a detected company can be resolved to an actual tradable
# symbol — used by headline_tickers.py to look up a company's 1-year
# return for the News page's inline ticker badge. (Used to also drive
# this module's own keyword-based Earnings classification — that's
# gone now that decide() is AI-first, see this module's own docstring
# — but headline_tickers.py's own use is unrelated and still live.)
EARNINGS_COMPANIES = {
    # Mega-cap tech.
    "apple": "AAPL", "aapl": "AAPL", "microsoft": "MSFT", "msft": "MSFT",
    "nvidia": "NVDA", "nvda": "NVDA", "amazon": "AMZN", "amzn": "AMZN",
    "alphabet": "GOOGL", "google": "GOOGL", "googl": "GOOGL",
    "meta platforms": "META", "tesla": "TSLA", "tsla": "TSLA",
    "netflix": "NFLX", "nflx": "NFLX", "broadcom": "AVGO", "avgo": "AVGO",
    "berkshire hathaway": "BRK-B",
    # Other software/internet/semis.
    "intel": "INTC", "amd": "AMD", "qualcomm": "QCOM", "oracle": "ORCL",
    "salesforce": "CRM", "adobe": "ADBE", "ibm": "IBM", "cisco": "CSCO",
    "servicenow": "NOW", "workday": "WDAY", "snowflake": "SNOW",
    "palantir": "PLTR", "crowdstrike": "CRWD", "zscaler": "ZS",
    "datadog": "DDOG", "mongodb": "MDB", "shopify": "SHOP", "uber": "UBER",
    "lyft": "LYFT", "airbnb": "ABNB", "doordash": "DASH",
    "booking holdings": "BKNG", "expedia": "EXPE", "spotify": "SPOT",
    "snap inc": "SNAP", "pinterest": "PINS", "roblox": "RBLX", "unity software": "U",
    "twilio": "TWLO", "zoom video": "ZM", "dropbox": "DBX", "atlassian": "TEAM",
    "hubspot": "HUBS", "okta": "OKTA", "paypal": "PYPL", "block inc": "XYZ",
    "coinbase": "COIN", "robinhood": "HOOD", "sofi technologies": "SOFI",
    "affirm holdings": "AFRM", "marvell technology": "MRVL",
    "texas instruments": "TXN", "applied materials": "AMAT",
    "lam research": "LRCX", "micron technology": "MU",
    "western digital": "WDC", "dell technologies": "DELL",
    "hewlett packard enterprise": "HPE", "netapp": "NTAP",
    "arista networks": "ANET", "juniper networks": "JNPR",
    "garmin": "GRMN", "corning inc": "GLW",
    # Finance/banks.
    "jpmorgan": "JPM", "jp morgan": "JPM", "bank of america": "BAC",
    "bofa": "BAC", "wells fargo": "WFC", "citigroup": "C",
    "goldman sachs": "GS", "morgan stanley": "MS", "us bancorp": "USB",
    "pnc financial": "PNC", "truist financial": "TFC",
    "charles schwab": "SCHW", "american express": "AXP",
    "discover financial": "DFS", "capital one": "COF", "visa": "V",
    "mastercard": "MA", "blackrock": "BLK", "state street": "STT",
    "bny mellon": "BK", "moody's corporation": "MCO", "s&p global": "SPGI",
    "intercontinental exchange": "ICE", "cme group": "CME",
    "nasdaq inc": "NDAQ",
    # Healthcare/pharma.
    "unitedhealth": "UNH", "eli lilly": "LLY", "pfizer": "PFE",
    "johnson & johnson": "JNJ", "merck & co": "MRK", "abbvie": "ABBV",
    "bristol myers squibb": "BMY", "amgen": "AMGN", "gilead sciences": "GILD",
    "regeneron": "REGN", "vertex pharmaceuticals": "VRTX", "moderna": "MRNA",
    "biogen": "BIIB", "illumina": "ILMN", "thermo fisher": "TMO",
    "danaher corporation": "DHR", "stryker corporation": "SYK",
    "becton dickinson": "BDX", "medtronic": "MDT", "boston scientific": "BSX",
    "abbott laboratories": "ABT", "cvs health": "CVS", "cigna": "CI",
    "humana": "HUM", "elevance health": "ELV", "hca healthcare": "HCA",
    # Consumer/retail.
    "costco": "COST", "walmart": "WMT", "home depot": "HD", "lowe's": "LOW",
    "target corp": "TGT", "tjx companies": "TJX", "ross stores": "ROST",
    "kroger": "KR", "coca-cola": "KO", "pepsico": "PEP",
    "procter & gamble": "PG", "colgate-palmolive": "CL",
    "kimberly-clark": "KMB", "nike": "NKE", "lululemon": "LULU",
    "starbucks": "SBUX", "mcdonald's": "MCD", "chipotle": "CMG",
    "yum brands": "YUM", "estee lauder": "EL", "clorox": "CLX",
    "general mills": "GIS", "kraft heinz": "KHC", "mondelez": "MDLZ",
    "hershey company": "HSY", "monster beverage": "MNST",
    "constellation brands": "STZ", "philip morris international": "PM",
    "altria group": "MO",
    # Energy/industrials.
    "exxon": "XOM", "exxonmobil": "XOM", "chevron": "CVX",
    "conocophillips": "COP", "schlumberger": "SLB",
    "occidental petroleum": "OXY", "marathon petroleum": "MPC",
    "phillips 66": "PSX", "valero energy": "VLO", "kinder morgan": "KMI",
    "nextera energy": "NEE", "duke energy": "DUK", "southern company": "SO",
    "dominion energy": "D", "boeing": "BA", "lockheed martin": "LMT",
    "raytheon": "RTX", "northrop grumman": "NOC", "general dynamics": "GD",
    "caterpillar": "CAT", "deere & company": "DE", "honeywell": "HON",
    "3m company": "MMM", "general electric": "GE", "union pacific": "UNP",
    "csx corporation": "CSX", "norfolk southern": "NSC", "fedex": "FDX",
    "united parcel service": "UPS",
    # Autos.
    "ford motor": "F", "general motors": "GM", "rivian automotive": "RIVN",
    "lucid motors": "LCID", "ferrari nv": "RACE",
    # Telecom/media.
    "verizon": "VZ", "at&t": "T", "t-mobile us": "TMUS", "comcast": "CMCSA",
    "charter communications": "CHTR", "disney": "DIS",
    "warner bros discovery": "WBD", "paramount global": "PARA",
    "news corp": "NWSA", "fox corporation": "FOXA",
    # Airlines.
    "delta air lines": "DAL", "united airlines": "UAL",
    "american airlines": "AAL", "southwest airlines": "LUV",
    # Crypto-adjacent public companies.
    "microstrategy": "MSTR", "marathon digital": "MARA",
    "riot platforms": "RIOT",
    # More US, across sectors not yet covered.
    "on semiconductor": "ON", "analog devices": "ADI", "skyworks solutions": "SWKS",
    "microchip technology": "MCHP", "palo alto networks": "PANW", "fortinet": "FTNT",
    "autodesk": "ADSK", "intuit": "INTU", "best buy": "BBY", "dollar general": "DG",
    "dollar tree": "DLTR", "ulta beauty": "ULTA", "etsy": "ETSY", "ebay": "EBAY",
    "emerson electric": "EMR", "illinois tool works": "ITW", "parker hannifin": "PH",
    "eaton corporation": "ETN", "american tower": "AMT", "prologis": "PLD",
    "simon property group": "SPG", "public storage": "PSA",
    "marriott international": "MAR", "hilton worldwide": "HLT",
    "las vegas sands": "LVS", "mgm resorts": "MGM", "progressive corp": "PGR",
    "travelers companies": "TRV", "chubb limited": "CB", "metlife": "MET",
    "prudential financial": "PRU", "aig": "AIG", "american electric power": "AEP",
    "exelon corporation": "EXC", "sempra energy": "SRE",
    "live nation entertainment": "LYV", "electronic arts": "EA",
    "take-two interactive": "TTWO", "alnylam pharmaceuticals": "ALNY",
    "biontech": "BNTX", "kla corporation": "KLAC", "global payments": "GPN",
    # Canada — the rest of the TSX heavyweights beyond what's already here.
    "royal bank of canada": "RY", "rbc": "RY", "td bank": "TD",
    "scotiabank": "BNS", "bank of nova scotia": "BNS",
    "bank of montreal": "BMO", "bmo financial": "BMO", "enbridge": "ENB",
    "canadian national railway": "CNI", "canadian pacific kansas city": "CP",
    "canadian pacific": "CP", "bce inc": "BCE", "suncor energy": "SU",
    "suncor": "SU", "barrick gold": "GOLD", "barrick": "GOLD",
    "manulife financial": "MFC", "manulife": "MFC",
    "alimentation couche-tard": "ATD.TO",
    # UK. "bp" and "shell" alone are far too common as ordinary English
    # words/abbreviations to bare-match safely — those two only match on
    # the fuller phrasing, or fall back to an explicit "(BP)"/"(SHEL)"
    # ticker parenthetical if the headline includes one.
    "astrazeneca": "AZN", "glaxosmithkline": "GSK", "gsk": "GSK",
    "bp plc": "BP", "shell plc": "SHEL", "hsbc holdings": "HSBC",
    "hsbc": "HSBC", "rio tinto": "RIO", "bhp group": "BHP", "bhp": "BHP",
    "diageo": "DEO", "british american tobacco": "BTI", "vodafone": "VOD",
    # Continental Europe.
    "sap se": "SAP", "sap": "SAP", "novo nordisk": "NVO",
    "nestle": "NSRGY", "lvmh": "LVMUY", "totalenergies": "TTE",
    "sanofi": "SNY", "roche holding": "RHHBY", "roche": "RHHBY",
    "novartis": "NVS", "ubs group": "UBS", "ubs": "UBS",
    "deutsche bank": "DB", "stellantis": "STLA", "ing group": "ING",
    "philips nv": "PHG", "philips": "PHG", "adidas": "ADDYY",
    # Asia.
    "toyota motor": "TM", "toyota": "TM", "sony group": "SONY",
    "sony": "SONY", "nintendo": "NTDOY", "softbank group": "SFTBY",
    "softbank": "SFTBY", "taiwan semiconductor": "TSM", "tsmc": "TSM",
    "alibaba": "BABA", "alibaba group": "BABA", "tencent holdings": "TCEHY",
    "tencent": "TCEHY", "baidu": "BIDU", "jd.com": "JD",
    "pdd holdings": "PDD", "netease": "NTES", "nio inc": "NIO",
    "nio": "NIO", "byd company": "BYDDY", "xiaomi": "XIACY",
    "honda motor": "HMC", "honda": "HMC", "infosys": "INFY",
    "icici bank": "IBN", "hdfc bank": "HDB",
}
# Clickbait/speculation tells. The goal: "what just happened," not "what
# if" — a real news headline reports a fact that already occurred, it
# doesn't tease an answer, hedge with a maybe, or dress up someone's
# opinion as if it were the story. Grouped by what kind of non-news each
# pattern is aimed at, since "just add more keywords" stops being
# reviewable past a certain point otherwise:
CLICKBAIT_TERMS = [
    # Teaser phrasing that promises an answer instead of stating one. Bare
    # "here's"/"here are" catches every variant ("here's our plan", "here's
    # a closer look", "here are the details") without enumerating each one.
    "here's", "here are", "what this means for", "you need to know",
    # Direct reader-address / advice-column framing — telling you what to
    # do with your money is not the same as reporting what happened.
    "should you buy", "should you sell", "is it too late to buy",
    "is it time to buy", "is it time to sell", "time to buy", "time to sell",
    "worth buying", "worth watching", "worth a look",
    # Superlative/listicle clickbait — the "N best/top X stocks to buy"
    # shape itself is caught by CLICKBAIT_PATTERNS below (a literal
    # phrase like "best stocks to buy" breaks the instant a headline
    # inserts an adjective: "best DIVIDEND stocks to buy" doesn't contain
    # "best stocks to buy" as an exact substring). These are the fixed
    # phrases that don't have that gap-insertion problem.
    "top picks include", "stocks to buy now", "stocks to watch",
    "stocks that benefit", "no-brainer stock", "millionaire maker",
    "must-watch stock", "hidden gem stock", "hottest stock",
    # Forecast/projection phrasing — a prediction, not an event.
    "expected to", "projected to", "forecast to", "poised to",
    "on track to", "gearing up to", "likely to",
    # Analyst-opinion/content-mill brand names — commentary and stock
    # picks packaged to look like news. (jim cramer moved here from the
    # inclusion list above — his segments are opinion/recommendation
    # content, not reporting.)
    "jim cramer", "motley fool", "insider monkey", "simply wall st",
    "zacks", "benzinga",
    # Explicit opinion-column labeling.
    "opinion:", "analysis:", "commentary:",
]
CLICKBAIT_PATTERNS = [
    re.compile(r"\b\d+\s+(things?|reasons?|ways?|takeaways?|stocks?)\s+that\b"),
    re.compile(r"\bthis\s+(?:\w+\s+){0,2}stocks?\b"),
    re.compile(r"\bthese\s+(?:\w+\s+){0,2}stocks?\b"),
    # Numbered listicle leads ("3 Best Dividend Stocks to Buy", "5 Top
    # Growth Stocks for 2026") — allows a gap so an inserted adjective
    # ("best DIVIDEND stocks") doesn't slip past a literal phrase match.
    re.compile(r"^\d+\s+(best|top|worst|hot|great)\b"),
    re.compile(r"\b(best|top|worst)\s+(?:\w+\s+){0,3}stocks?\s+to\s+buy\b"),
    # Bare "could"/"might" — modal words that hedge an outcome rather
    # than report one ("stocks could rally", "Fed might cut rates").
    # "may"/"would" are ambiguous on their own (the month "May", quoted
    # factual statements like "said it would close in Q3"), so those are
    # only excluded when paired with a market-moving verb below.
    re.compile(r"\bcould\b"),
    re.compile(r"\bmight\b"),
    re.compile(
        r"\b(?:may|would)\s+(rise|fall|climb|drop|surge|plunge|gain|lose|"
        r"benefit|hurt|impact|affect|help|drive|boost|hit|see|face|sink|"
        r"soar|tumble|jump)\b"
    ),
    # Auto-generated daily commodity/price-recap template ("Gold prices
    # today, Monday, July 6: ...") — a routine wrapper, not a story.
    re.compile(r"\bprices?\s+today,?\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"),
    # Active-voice forecasting ("analysts expect the Fed to cut rates") —
    # "expected to" above only catches the passive form.
    re.compile(r"\bexpects?\b.{0,40}\bto\b"),
    # Explainer/analysis framing ("Why Iran may find it difficult to...",
    # "'Quote here': Why the market is rethinking...") — this is analysis
    # of why something might be true, not a report of what happened.
    re.compile(r"^why\s"),
    re.compile(r":\s*why\s"),
]


def _contains_any(text: str, terms: list[str]) -> bool:
    """Whole-word/phrase match — plain substring matching let terms like
    "shares" match inside unrelated words ("Bankshares", "Bancshares").

    Tolerates an optional trailing "s" so a term also matches its plural
    without needing a separate entry for both — "stock" alone used to
    silently miss the far more common "stocks rally today" phrasing
    (word-boundary matching is strict: \\bstock\\b does not match
    "stocks", since there's no boundary between "k" and "s")."""
    return any(re.search(r"\b" + re.escape(t) + r"s?\b", text) for t in terms)


@functools.lru_cache(maxsize=2048)
def is_clickbait(headline: str) -> bool:
    """True for teaser-style headlines that ask a question or hide their
    subject behind a vague pronoun instead of just stating the fact."""
    if "?" in headline:
        return True
    h = headline.lower()
    if _contains_any(h, CLICKBAIT_TERMS):
        return True
    return any(p.search(h) for p in CLICKBAIT_PATTERNS)


# AI verdict tokens -> display strings, used both for category_class()'s
# CSS mapping and as the actual category shown. BREAKING is a catch-all
# for something genuinely major that doesn't fit any named category, and
# gets its own small theme.py addition.
_AI_VERDICT_LABELS = {
    "FED_BOC": "Fed/BoC",
    "DATA_SURPRISE": "Data Surprise",
    "EARNINGS": "Earnings",
    "MACRO_SHOCK": "Macro Shock",
    "MERGERS": "Mergers",
    "MILESTONE": "Milestone",
    "BREAKING": "Breaking News",
}
_AI_VALID_VERDICTS = {"REJECT", "MARKET"} | set(_AI_VERDICT_LABELS)


# Session request history: "maybe ping the ai every five minutes to
# find genuine headlines" -> widened to 30 min once full-article
# grounding made a worst-case full batch ~9-11k tokens on its own ->
# weekday/weekend headline caps to cut per-call size further. Then a
# direct reversal: "transition feed processing from 15-minute batching
# to 1-minute polling so news is processed instantly as it drops...
# stream headlines through the classifier individually so notifications
# fire in real-time... rather than in periodic bursts." Told explicitly
# this costs meaningfully more (each headline now pays the full
# judgment-criteria overhead alone instead of sharing it across a
# batch — confirmed live, roughly 4x more overhead tokens for the same
# headline volume) on the account that had already hit its daily cap
# once that same day, and chose it anyway — see groq_client's own
# daily-budget guard for what still catches this gracefully if it runs
# the account dry again.
INDIVIDUAL_REFRESH_SECONDS = 60
# Caps how many headlines get their own real classification call in a
# single tick — NOT the old batch caps repurposed, deliberately much
# smaller: at up to ~900 tokens each (criteria overhead + one
# headline), the old weekday batch cap of 15 would mean ~13,500 tokens
# in a single minute if a backlog ever piled up, blowing straight
# through Groq's 12k-tokens/minute bucket in one tick. A genuine
# backlog beyond this just drains over the next several 1-minute ticks
# instead — nothing is ever dropped, only delayed a little further.
INDIVIDUAL_MAX_PER_TICK_WEEKDAY = 5
INDIVIDUAL_MAX_PER_TICK_WEEKEND = 2
INDIVIDUAL_MAX_OUTPUT_TOKENS = 150


def _max_headlines_per_tick(now: datetime | None = None) -> int:
    now = now or datetime.now(ZoneInfo(TIMEZONE))
    is_weekend = now.weekday() >= 5  # Monday=0 ... Saturday=5, Sunday=6
    return INDIVIDUAL_MAX_PER_TICK_WEEKEND if is_weekend else INDIVIDUAL_MAX_PER_TICK_WEEKDAY

# hash -> decision dict (kept) or None (AI rejected). A key's absence
# means "not yet classified" — decide() and _run_individual_decide()
# both rely on that three-way distinction (see their own docstrings).
# Plain module state (same convention as sports_client.py's own
# _last_good_*/_delay_buffers, groq_client's _periodic_cache) rather
# than st.session_state: classification is shared across every browser
# session hitting this one server process, not per-tab.
_decided: dict[str, dict | None] = {}
_last_tick_at: float = 0.0


def _hash(headline: str) -> str:
    return hashlib.sha1(headline.encode()).hexdigest()


ARTICLE_FETCH_TIMEOUT_SECONDS = 6
# A full 30-headline batch at the old 1500-char cap ran ~11k input
# tokens — right against Groq's 12k-tokens/minute limit, so the whole
# batch (not just this one headline) would silently 429 and every
# pending headline would stay unclassified for another window. 800 is
# still enough for a lead paragraph's numbers while leaving headroom.
ARTICLE_EXCERPT_MAX_CHARS = 800


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _fetch_article_excerpt(url: str) -> str:
    """Best-effort plain-text excerpt of the actual article page — not
    just the RSS <description>, which is often empty or unhelpful.
    Session request: "make it look at the full story for a more
    detailed headline." Strips script/style/nav/header/footer/aside/
    form first, then joins visible <p> tag text (skipping short
    fragments under 40 chars — nav labels, image captions, "read more"
    links, not real article prose), truncated to
    ARTICLE_EXCERPT_MAX_CHARS. The number a vague headline is missing
    is almost always in the lede, well within a paywall's free preview
    even on sites that gate the rest of a piece.

    "" (never an exception) on any failure — a site block, timeout, or
    genuinely thin page all just mean "no extra context available,"
    treated exactly like an empty RSS description already was; this
    must never be able to stall a batch over one slow or hostile site.
    Cached an hour per URL — this app never asks about the same article
    twice anyway (see _decided), but a batch that retries a fetch
    failure on the next window shouldn't hit the same slow site again
    within the hour."""
    if not url:
        return ""
    try:
        fetch_throttle.wait_turn()
        resp = requests.get(url, timeout=ARTICLE_FETCH_TIMEOUT_SECONDS, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(p for p in paragraphs if len(p) > 40)
        return text[:ARTICLE_EXCERPT_MAX_CHARS]
    except Exception:
        return ""


# Shared word-for-word between _build_batch_prompt and
# _build_single_prompt so the two paths (batch, and per-headline
# individual streaming — see _run_individual_decide) can never quietly
# drift into judging the same headline differently depending on which
# one happened to classify it. "this list"/"the same batch" language
# generalized to "a different story" so it reads correctly whether
# there's one headline in front of the model or several.
_CLASSIFICATION_CRITERIA = (
    "For each: is it genuinely informational — reporting a fact that has already happened, "
    "not clickbait, not a listicle ('5 stocks to buy'), not opinion/analysis/commentary, not "
    "speculation ('could', 'might', 'expected to'), not an advice column ('should you buy') "
    "— and specifically finance/markets/economy relevant (not general news, sports, "
    "entertainment, lifestyle)? Also REJECT routine Fed/regulator administrative or "
    "supervisory business that isn't real news to a general reader — enforcement actions "
    "against individual bank employees, routine stress-test results confirming banks are "
    "fine, name/personnel changes, procedural notices — these read as Fed-related but "
    "aren't; don't let them through as MARKET just because they mention the Fed.\n\n"
    "Also REJECT retrospective analysis, recaps, and explainers — a headline whose entire "
    "point is looking back at or explaining something that already happened, not reporting a "
    "new event as it's happening. This includes headlines shaped like 'Why [X] surged/fell/"
    "did...', 'Here's why...', 'Here's what...', '[period] in Review', 'First Half of "
    "[year]...', 'Everything you need to know about...', 'Breaking down...', 'The story "
    "behind...' — even when the underlying fact is real and specific, explaining or "
    "recapping it after the fact is not the same as it breaking now. If a headline fails any "
    "of this, its verdict is REJECT.\n\n"
    "Otherwise pick exactly one category: FED_BOC (a real Fed/BoC policy action — a rate "
    "decision, a genuinely market-moving statement — not routine paperwork), DATA_SURPRISE "
    "(a major economic data release meaningfully above/below expectations), EARNINGS (a "
    "company's actual reported results that meaningfully BEAT or MISSED expectations — not "
    "a routine 'reports Q2 results' headline with no real surprise attached), MACRO_SHOCK (a "
    "crash/crisis/systemic event, or a real trading halt/circuit breaker), MERGERS (a $1B+ "
    "announced deal), MILESTONE (a genuine record high/low), MARKET "
    "(real but routine financial news), or BREAKING (something else genuinely major that "
    "doesn't fit those).\n\n"
    "STRICT DATA REQUIREMENT — be strict here. Look at the headline, its SUMMARY, and its "
    "ARTICLE EXCERPT (whichever are present) for a specific number, percentage, or figure. "
    "If one exists, rewrite the headline into one short, concise, factual sentence that "
    "includes it — never invent, estimate, or guess a number that isn't actually present in "
    "that text, and never borrow a number from a different story.\n\n"
    "If NO real number is available anywhere in the headline, summary, or article excerpt, "
    "apply strict scrutiny before letting the headline through: is its own core claim "
    "already a single, concrete, unambiguous event on its own — a specific decision, "
    "acquisition, resignation, bankruptcy, ceasefire, or similarly definite fact — genuinely "
    "meaningful even without a number attached? If yes, keep it as-is, unchanged, with no "
    "fabricated data. If no — the headline is fundamentally vague with no specifics anywhere "
    "about by how much, to what, or what exactly changed ('lowers forecast', 'warns of "
    "headwinds', 'beats expectations' with nothing concrete attached anywhere) — its verdict "
    "MUST be REJECT, even if it would otherwise pass the relevance check above. A vague, "
    "unactionable headline is not worth showing regardless of topic."
)


def _build_batch_prompt(items: list[dict]) -> str:
    """One prompt judging every item in `items` independently — same
    two-task judgment the old per-headline version asked (keep-or-
    reject + category; rewrite with real numbers when available), just
    asked once for many headlines instead of once per headline. Each
    item may carry an "article_excerpt" (see _fetch_article_excerpt)
    alongside its RSS "description" — both are offered as grounding,
    but numbers are NEVER invented, estimated, or recalled from the
    model's own training knowledge, and NEVER borrowed from a different
    headline in the same batch — a confidently wrong figure would be
    worse than a vague headline on a finance dashboard.

    Session correction after that still let a genuinely data-free
    headline through unchanged: "if they cant find anything to make
    the headline unactionable then dont allow it... if you dont have a
    number you better have a good reason for letting it through." A
    headline with no number anywhere now only survives if its own core
    claim is already a single, concrete, unambiguous event — otherwise
    REJECT, even if it would have passed the relevance check on its
    own.

    Session report of a further quality gap: "the AI classifier is
    letting non-actionable, retrospective fluff (e.g., 'Why stock X
    surged in the first half of 2026') trigger breaking news push
    alerts... reserve notification-worthy status strictly for genuine,
    real-time market-moving events." A "why did X happen" explainer can
    describe a perfectly real, specific fact and still not be news —
    it's looking back at something already known, not reporting
    something breaking now. Explicit REJECT criteria added for that
    shape of headline, and EARNINGS tightened to require an actual
    beat/miss rather than any routine earnings report — both push
    notifications (see update_top_alert) and the News page itself
    inherit this directly, since both key off the same verdict here."""
    lines = []
    for i, item in enumerate(items):
        entry = f"{i + 1}. HEADLINE: {item['headline']}"
        description = (item.get("description") or "").strip()
        if description and description != item["headline"].strip():
            entry += f"\n   SUMMARY: {description}"
        excerpt = (item.get("article_excerpt") or "").strip()
        if excerpt:
            entry += f"\n   ARTICLE EXCERPT: {excerpt}"
        lines.append(entry)
    headline_block = "\n".join(lines)
    return (
        "You are a strict news editor for a personal finance/markets dashboard. Judge EACH of "
        f"the following {len(items)} headlines independently — they are unrelated to each "
        "other.\n\n"
        f"{_CLASSIFICATION_CRITERIA}\n\n"
        f"{headline_block}\n\n"
        "Respond with ONLY a JSON array, no markdown code fences, no other text, exactly one "
        "object per headline above IN THE SAME ORDER, in exactly this shape (omit \"headline\" "
        "entirely for a REJECT):\n"
        '[{"verdict": "REJECT"}, {"verdict": "MARKET", "headline": "..."}, '
        '{"verdict": "FED_BOC", "headline": "..."}]'
    )


def _build_single_prompt(item: dict) -> str:
    """Same judgment as _build_batch_prompt (see _CLASSIFICATION_CRITERIA,
    shared word-for-word between both so they can never quietly drift
    apart), for exactly one headline instead of a numbered list — session
    request: "stream headlines through the classifier individually so
    notifications fire in real-time... instead of in periodic bursts."
    Asks for a single JSON object rather than an array of one; that
    framing difference, plus dropping the batch prompt's "judge each of
    the following N headlines... IN THE SAME ORDER" wrapper, is the only
    real savings available here without weakening the actual judgment
    criteria, which is the bulk of the prompt either way."""
    entry = f"HEADLINE: {item['headline']}"
    description = (item.get("description") or "").strip()
    if description and description != item["headline"].strip():
        entry += f"\nSUMMARY: {description}"
    excerpt = (item.get("article_excerpt") or "").strip()
    if excerpt:
        entry += f"\nARTICLE EXCERPT: {excerpt}"
    return (
        "You are a strict news editor for a personal finance/markets dashboard. Judge this one "
        "headline.\n\n"
        f"{_CLASSIFICATION_CRITERIA}\n\n"
        f"{entry}\n\n"
        "Respond with ONLY a JSON object, no markdown code fences, no other text, in exactly "
        "this shape (omit \"headline\" entirely for a REJECT):\n"
        '{"verdict": "REJECT"}\n'
        "or\n"
        '{"verdict": "MARKET", "headline": "..."}\n'
        "or e.g.\n"
        '{"verdict": "FED_BOC", "headline": "..."}'
    )


def _apply_verdict(item: dict, verdict_obj) -> None:
    """Parses one AI verdict object — the batch and single-headline
    prompts both ask for the exact same object shape, just wrapped
    differently (an array of them vs. one on its own) — and records it
    in _decided. Shared so both call sites apply identical parsing and
    validation, not two copies that could quietly drift apart."""
    h = _hash(item["headline"])
    if not isinstance(verdict_obj, dict):
        return
    verdict = str(verdict_obj.get("verdict", "")).strip().upper()
    if verdict not in _AI_VALID_VERDICTS or verdict == "REJECT":
        _decided[h] = None
        return
    display_headline = (verdict_obj.get("headline") or "").strip() or item["headline"]
    if verdict == "MARKET":
        _decided[h] = {"headline": display_headline, "category": "Market News", "important": False}
    else:
        _decided[h] = {"headline": display_headline, "category": _AI_VERDICT_LABELS[verdict], "important": True}


def _run_individual_decide() -> None:
    """Classifies up to _max_headlines_per_tick() currently-pending
    headlines (from the current fetch_headlines() pool, not already in
    _decided), each with its own real Groq call, throttled to at most
    once per INDIVIDUAL_REFRESH_SECONDS regardless of how often this is
    called — see this module's own docstring for why this replaced
    batching. A no-op if it's not yet time for a new tick, or there's
    nothing pending. Call this once per rerun before relying on
    decide() for fresh coverage; get_new_alerts() already does, and
    since that runs early in app.py regardless of which page is up,
    callers like pages_news.py don't need to call this themselves.

    A backlog beyond the per-tick cap simply waits for the next tick —
    nothing is ever dropped, only delayed a little further (see
    INDIVIDUAL_MAX_PER_TICK_WEEKDAY/WEEKEND's own comment for why that
    cap exists — protecting the per-minute token bucket from a burst,
    now that each headline's classification isn't sharing a single
    call's overhead with anything else). Each headline's call succeeds
    or fails independently — one rate-limited or unparseable response
    only leaves THAT headline pending for the next tick, not the rest
    of this one."""
    global _last_tick_at
    now = time.time()
    if now - _last_tick_at < INDIVIDUAL_REFRESH_SECONDS:
        return
    pending = [item for item in fetch_headlines() if _hash(item["headline"]) not in _decided][:_max_headlines_per_tick()]
    if not pending:
        _last_tick_at = now
        return
    # Set before the calls, not after — same reasoning the old batch
    # design already established: a failed attempt still counts against
    # the cadence, so a rate-limit blip can't turn into a tight retry
    # loop; the next tick waits the full window regardless.
    _last_tick_at = now
    for item in pending:
        # Full article text, not just the RSS description — session
        # request: "make it look at the full story for a more detailed
        # headline." A slow or blocked site just contributes "" for
        # this one item (see _fetch_article_excerpt's own docstring)
        # rather than derailing anything else in this tick.
        excerpt = _fetch_article_excerpt(item.get("link", ""))
        prompt = _build_single_prompt({**item, "article_excerpt": excerpt})
        # Low temperature — this is a judgment call that should be
        # consistent, not creative prose (see groq_client.generate's own
        # docstring: confirmed live that the default 0.7 made the exact
        # same headline flip between two different verdicts across
        # repeat calls).
        result = groq_client.generate(prompt, temperature=0.1, max_output_tokens=INDIVIDUAL_MAX_OUTPUT_TOKENS)
        if result is None:
            continue  # this one headline stays pending, retried next tick
        text = result.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            text = text.rsplit("```", 1)[0]
        try:
            verdict_obj = json.loads(text.strip())
        except Exception:
            continue  # unparseable response — stays pending, retried next tick
        _apply_verdict(item, verdict_obj)


def decide(headline: str) -> dict | None:
    """The one real decision every caller in this module uses:
    {"headline": <display text, possibly AI-rewritten with real
    numbers>, "category": <display name>, "important": bool} to show
    this headline, None to drop it — either because the AI rejected it,
    or because no tick has reached it yet (see _run_individual_decide).
    There is no keyword-based fallback anymore — session request: "only
    have them shown through the ai." Pure cache lookup, no network
    call; callers must have already given _run_individual_decide a
    chance to run this rerun for the answer to be fresh."""
    return _decided.get(_hash(headline))


def category_class(category: str) -> str:
    """CSS class for a decide()-returned category — shared so the News
    page's row accent color and the alert bar's tag color are always
    the same mapping, not two copies that could drift apart."""
    return "news-cat-" + category.lower().replace("/", "-").replace(" ", "-")


_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(raw: str) -> str:
    """Some feeds' <description> carries inline markup (a stray <a>/<b>)
    — plain text is all _build_batch_prompt needs, and stripped-but-
    imperfect is fine here since this only ever feeds a prompt, never
    gets rendered as HTML itself."""
    return _HTML_TAG.sub("", raw).strip()


def _parse_pub_date(raw: str) -> datetime | None:
    """Handles both date formats seen across FEEDS — RFC 822
    ("Thu, 16 Jul 2026 18:00:00 GMT", most feeds) and ISO 8601
    ("2026-07-19T16:54:17Z", Yahoo Finance specifically)."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


@st.cache_data(ttl=3 * 60, show_spinner=False)
def fetch_headlines() -> list[dict]:
    items = []
    any_feed_succeeded = False
    for url, source in FEEDS:
        try:
            fetch_throttle.wait_turn()
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
            any_feed_succeeded = True
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                published = _parse_pub_date(item.findtext("pubDate") or "")
                # Each feed's own <description> — often empty (Yahoo
                # Finance never sets it) or just a duplicate of the
                # title (the Fed's feed), but sometimes carries the
                # concrete number/figure the headline itself lacks. Fed
                # to _build_batch_prompt as grounding for its headline
                # rewrite — see that function's own docstring for why
                # it's only ever allowed to use a number if it's
                # actually here, never invented.
                description = _strip_html(item.findtext("description") or "")
                if title:
                    items.append(
                        {"headline": title, "link": link, "source": source, "published": published, "description": description}
                    )
        except Exception:
            continue  # one dead/slow feed shouldn't take down the others
    # At least one of FEEDS came through — news is still genuinely
    # flowing, even if some other feed is currently down (see
    # data_health.py). Only runs on an actual cache miss (st.cache_data
    # skips this whole body on a hit), so this tracks "when a real fetch
    # last succeeded," on this function's own 3-minute cadence.
    if any_feed_succeeded:
        data_health.record_success("news")
    return items


def get_new_alerts() -> list[dict]:
    """Flags fresh headlines that qualify for the News page; only returns
    ones not already seen this session. Uses the same `decide()` verdict
    as the News page itself so the breaking-news bar is just the News
    page's feed, surfaced the moment each headline first appears.

    Calls _run_individual_decide() first — this is the one call site
    that runs every rerun regardless of which page is up, so it's what
    keeps the classification cadence moving even when nobody's looking
    at the News or Conflicts pages; pages_news.py relies on this having
    already run earlier in the same script execution and just calls
    decide() itself.

    The very first call establishes a baseline (marks whatever already
    qualifies as "seen" without alerting) so opening the dashboard doesn't
    immediately flood every historical headline as if it just broke.
    """
    _run_individual_decide()
    # A plain set only ever grew — fine for a normal Streamlit session,
    # but this kiosk's one browser tab can stay open for weeks without a
    # reload, so it was a real unbounded-forever accumulator on a process
    # that has crash-looped from memory pressure before. A dict (Python
    # 3.7+ preserves insertion order) doubles as an ordered set here so
    # the oldest hash can be evicted once the cap's hit — headlines this
    # old have long since rolled off every RSS feed's own window anyway,
    # so they'd never need to be recognized as "seen" again regardless.
    seen = st.session_state.setdefault("seen_headlines", {})
    baseline_done = st.session_state.get("news_baseline_done", False)

    alerts = []
    for item in fetch_headlines():
        # decide() is a plain cache lookup now (no network call), so
        # checking it before "seen" costs nothing — a still-pending or
        # rejected headline just keeps getting skipped for free until a
        # later batch (if ever) actually classifies it as keepable.
        decision = decide(item["headline"])
        if decision is None:
            continue
        h = hashlib.sha1(item["headline"].encode()).hexdigest()
        if h in seen:
            continue
        seen[h] = True
        if len(seen) > MAX_SEEN_HEADLINES:
            seen.pop(next(iter(seen)))
        if baseline_done:
            alerts.append({**item, **decision})

    st.session_state["news_baseline_done"] = True
    # Session request: when several headlines qualify as new in the
    # same batch (e.g. a feed recovering from an outage and surfacing
    # everything it missed at once), line them up in the toast queue in
    # the order they were actually published — not FEEDS' own fixed
    # iteration order, which has nothing to do with real chronology.
    # Anything with an unparseable/missing pubDate sorts to the end
    # rather than crashing the comparison or claiming a false "first."
    alerts.sort(key=lambda a: a["published"] or datetime.min.replace(tzinfo=timezone.utc))
    return alerts


def render_alert_bar(alert: dict, elapsed: float, variant: str = "a"):
    """Bottom-strip takeover bar (normally the release-calendar ticker): a
    label stretches into view, holds, then slides aside to reveal the
    category tag + headline underneath.

    Red "BREAKING NEWS" when decide() judged this important, black
    "MARKET NEWS" otherwise, so the bar's own color signals how urgent
    a given item actually is before you even read the headline.

    `variant` ("a"/"b") picks between two functionally identical
    keyframe animations (theme.py) — alternated by the caller each
    rerun so a new alert always gets a genuine restart rather than
    reusing a completed animation instance on the same DOM node (see
    theme.py's comment above the toast-*-intro keyframes).
    """
    is_breaking = alert.get("important", alert["category"] != "Market News")
    bar_class = "news-alert-bar" if is_breaking else "news-alert-bar-market"
    label_text = "BREAKING NEWS" if is_breaking else "MARKET NEWS"
    delay = f"animation-delay: -{elapsed:.2f}s;"
    st.markdown(
        f"""<div class="{bar_class}">
            <span class="news-breaking-label toast-label-anim-{variant}" style="{delay}">{label_text}</span>
            <span class="news-alert-tag {category_class(alert['category'])} toast-headline-anim-{variant}" style="{delay}">{alert['category']}</span>
            <span class="news-alert-headline toast-headline-anim-{variant}" style="{delay}">{alert['headline']}</span>
        </div>""",
        unsafe_allow_html=True,
    )


# Bounded, FIFO, disk-persisted list of headline hashes already
# pushed — comfortably covers a long stretch of breaking headlines
# without growing forever (same shape as MAX_SEEN_HEADLINES above, same
# reasoning: headlines this old have long since rolled off every RSS
# feed's own window, so they'd never come back around as "new" anyway).
PUSHED_HEADLINES_MAX = 200


def update_top_alert(new_alerts: list[dict]) -> None:
    """Whenever a fresh important (red) headline comes through, it takes
    over the persistent top banner, replacing whatever was there before —
    "the next red headline" is exactly the next call here where an alert
    has important=True. Call once per rerun with whatever `get_new_alerts`
    just returned.

    Also pushes a phone notification for the same event — session
    request: "if it deems that a headline is truly breaking news... get
    it to ping me." The push specifically needs its own independent,
    disk-persisted dedup (PUSHED_HEADLINES_MAX below), NOT just trust in
    `new_alerts` already being filtered — session report of a real
    duplicate (the same Brent oil headline pushed twice) traced to
    get_new_alerts()'s own seen_headlines tracking living in
    st.session_state, which resets on a reconnect or a process restart
    and can hand the exact same headline back as "new" a second time.
    The on-screen top banner isn't re-gated here, only the push — a
    banner re-appearing after a rare reconnect was never reported as a
    problem the way a duplicate phone buzz was."""
    pushed = persisted_state.load("pushed_headlines", [])
    pushed_set = set(pushed)
    changed = False
    for alert in new_alerts:
        if alert.get("important"):
            st.session_state["top_alert"] = {**alert, "set_at": time.time()}
            h = _hash(alert["headline"])
            if h in pushed_set:
                continue
            pushed_set.add(h)
            pushed.append(h)
            changed = True
            ntfy_client.send(
                title=f"Breaking: {alert['category']}",
                message=alert["headline"],
                priority="urgent",
                tags="rotating_light",
            )
    if changed:
        if len(pushed) > PUSHED_HEADLINES_MAX:
            pushed = pushed[-PUSHED_HEADLINES_MAX:]
        persisted_state.save("pushed_headlines", pushed)


def render_top_alert_bar() -> None:
    """Renders the persistent top banner if a red headline is still
    within its hold window (TOP_ALERT_HOLD_SECONDS) — a plain static bar
    in normal document flow, not fixed/animated, since it needs to sit
    there unchanged for up to two hours rather than play an intro.

    Used to also re-check the stored headline against the live filter
    each render, in case a keyword-list edit mid-session made it no
    longer qualify. decide()'s AI verdict is trusted as final once made
    (same "locked in at first sight" philosophy pages_news.py's own
    entries already use) — nothing here changes that mid-hold, so
    there's nothing left to re-validate, and it would mean a real AI
    call every render besides."""
    top_alert = st.session_state.get("top_alert")
    if not top_alert:
        return
    expired = time.time() - top_alert["set_at"] > TOP_ALERT_HOLD_SECONDS
    if expired:
        del st.session_state["top_alert"]
        return
    st.markdown(
        f"""<div class="top-alert-bar">
            <span class="top-alert-dot"></span>
            <span class="top-alert-label">Breaking</span>
            <span class="top-alert-headline">{top_alert['headline']}</span>
        </div>""",
        unsafe_allow_html=True,
    )
