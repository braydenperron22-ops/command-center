"""RSS-based, keyword-filtered news — powers breaking-news alerts AND the
News page's rolling 24h feed, plus keyword-scanning for the Conflicts page.

No API key: pulls from the Fed's own press-release feed (zero-noise, it IS
the source) plus a few general finance RSS feeds. The breaking-news bar
uses the exact same `is_market_relevant` filter as the News page — it's
the same headline pool, just surfaced immediately as each one first
appears rather than waiting to be read on the News page. `classify()`
gives Fed/BoC, Data Surprise, Earnings, Macro Shock, Mergers, and
Milestone headlines their own tag; anything else market-relevant is
tagged "Market News" instead of being dropped. `is_important()` — which
decides red (breaking) vs black (market news) in the alert bar, and the
News page's red-vs-category-colored row border — is exactly
`classify(h) is not None`: every one of those six categories already
requires a topic+qualifier pairing (or is inherently unambiguous enough
not to need one, like Macro Shock), so there's no separate, looser path
for something to sneak through as "breaking" without earning it.
"""

import functools
import hashlib
import re
import time
from xml.etree import ElementTree

import requests
import streamlit as st

from config import TOP_ALERT_HOLD_SECONDS

# (feed URL, display name) — unlike the Conflicts page's Google News
# search (which already gets a " - Publisher" suffix baked into every
# title by Google), these feeds' own <title> tags carry no source
# attribution at all, so it has to come from knowing which feed it was.
FEEDS = [
    ("https://www.federalreserve.gov/feeds/press_all.xml", "Federal Reserve"),
    ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "CNBC"),
    ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
    ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
]

TOAST_SECONDS = 30

# Intro sequencing: "BREAKING NEWS" stretches into view, holds, then slides
# aside to reveal the headline underneath. Positions are computed as a pure
# function of elapsed time (not a replaying CSS keyframe) because the whole
# app reruns every second for the clock tick — a keyframe animation would
# restart on every one of those reruns instead of playing through once.
STRETCH_END = 1.8
SLIDE_END = 3.0

FED_BOC_INCLUDE = [
    "fomc statement", "fomc meeting", "rate decision", "interest rate decision",
    "rate hike", "rate cut", "raises rates", "cuts rates", "holds rates", "holds interest rates",
    "jerome powell", "bank of canada", "boc rate", "tiff macklem", "fed chair",
    "takes oath of office", "sworn in as chair", "steps down as chair", "resigns as chair",
    "named fed chair", "confirmed as fed chair", "quantitative easing", "quantitative tightening",
    "dot plot", "emergency meeting", "emergency rate", "press conference",
    "rate pause", "pauses rate", "hawkish pivot", "dovish pivot", "balance sheet runoff",
    "tapering", "forward guidance", "rate path",
]
# The Fed's own RSS feed is mostly routine bank-supervision paperwork —
# these show up alongside genuine policy news and would otherwise slip
# through on any headline that happens to say "Federal Reserve".
FED_BOC_EXCLUDE = [
    "enforcement action", "triennial payments study", "stress test",
    "distressed or underserved", "reputation risk", "data standards",
    "customer identification program", "results will be released", "stablecoin issuers",
    "middle-income geographies", "passing of",
]
DATA_PRINT_TERMS = [
    "cpi", "consumer price index", "inflation data", "jobs report",
    "nonfarm payrolls", "unemployment rate", "gdp growth", "employment situation",
    "gross domestic product", "inflation report", "retail sales", "ppi",
    "producer price index", "consumer confidence", "housing starts",
]
SURPRISE_TERMS = [
    "unexpectedly", "surprise", "beats estimates", "misses estimates",
    "higher than expected", "lower than expected", "surges", "plunges",
    "hotter than expected", "cooler than expected", "tops forecast", "misses forecast",
    "jumps", "tumbles", "slows more than", "sharply higher", "sharply lower",
    "sinks", "soars", "spikes",
]
# name/ticker variant -> canonical ticker symbol. A dict (not a flat
# list) so a detected company can be resolved to an actual tradable
# symbol — used both for the classify() Earnings pairing check (as
# EARNINGS_COMPANIES.keys()) and to look up a company's 1-year return
# for the News page's inline ticker badge (headline_tickers.py).
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
EARNINGS_TERMS = [
    "earnings", "quarterly results", "beats estimates", "misses estimates",
    "guidance", "q1 results", "q2 results", "q3 results", "q4 results", "profit",
    "revenue", "quarterly report",
]
MACRO_SHOCK_TERMS = [
    "recession fears", "banking crisis", "financial crisis", "market crash",
    "stocks plunge", "stock market sell-off", "bear market", "debt default",
    "credit downgrade", "circuit breaker", "market meltdown", "stocks tumble",
    "flash crash", "contagion fears", "systemic risk",
    # Filled real gaps — genuinely major, unambiguous single-word/phrase
    # events that weren't covered by anything above.
    "bankruptcy", "bailout", "bank run", "trading halted", "halts trading",
    "market rout", "worst day since", "biggest drop since", "stocks crash",
    "stocks collapse", "shares crash", "shares collapse", "wipes out",
    "credit crunch", "liquidity crisis",
]
# Genuinely huge M&A ("$X billion deal") and market-milestone headlines
# ("record high") had no coverage at all before — neither fit the
# existing categories, so big deal/record-setting news was never
# flagged as breaking no matter how significant.
MA_TERMS = [
    "to acquire", "acquires", "announces acquisition", "merger agreement",
    "agrees to buy", "takeover bid", "hostile takeover", "buyout deal",
    "to merge with", "acquisition of",
]
MA_SCALE_TERMS = ["billion", "trillion"]
MILESTONE_TERMS = [
    "record high", "record low", "all-time high", "all-time low",
    "closes at a record", "biggest gain since", "best day since",
]

# Deliberately looser than the breaking-news categories above — those
# require a topic AND a surprise/magnitude qualifier together, which is
# right for something worth interrupting the screen for, but far too
# narrow for a general news feed. These RSS feeds mix real financial
# content with lifestyle/celebrity fluff (weddings, parenting advice,
# travel pieces), so this still requires ONE real market/finance signal —
# just not the strict pairing — to keep the feed relevant without being
# nearly empty.
#
# Deliberately excludes bare "fed"/"federal reserve" — the Fed's own feed is
# mostly routine bank-supervision paperwork (same issue as the breaking-news
# filter), and matching on those terms let dozens of procedural notices
# crowd out more relevant content. Genuinely policy-relevant Fed news still
# qualifies via FED_BOC_INCLUDE below.
# Deliberately excludes a bare "rate" — it word-boundary-matches ANY rate
# ("discount rate," "birth rate," "graduation rate"), not just financial
# ones, and was letting routine Fed committee-minutes headlines through
# just because they happened to mention a meeting about rates. The
# specific rate-related phrasing that actually signals real news is
# already covered by FED_BOC_INCLUDE ("rate hike," "rate decision," etc.)
# and "bond"/"yield" below.
GENERAL_MARKET_TERMS = [
    "stock", "shares", "earnings", "ipo", "buy rating", "sell rating",
    "price target", "outperform", "underperform", "upgrade", "downgrade",
    "dividend", "etf", "market cap", "bond", "yield", "mortgage rate", "interest rate",
    "inflation", "cpi", "gdp", "jobs report", "unemployment", "recession",
    "economy", "economic", "rally", "sell-off", "selloff", "surge", "plunge",
    "futures", "wall street", "dow jones", "s&p", "nasdaq", "oil", "opec",
    "crude", "takeover", "acquisition", "merger", "analyst", "valuation",
    "warren buffett", "buffett", "hedge fund", "portfolio",
]
TICKER_PATTERN = re.compile(r"\([A-Z]{2,5}\)")

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


@functools.lru_cache(maxsize=2048)
def is_market_relevant(headline: str) -> bool:
    """Looser filter for the News page: any real finance/market signal
    qualifies, not just the narrow topic+surprise combos above — except
    clickbait, which is excluded outright regardless of what else it
    matches (see is_clickbait).

    Cached: this app reruns its whole script every second for the clock
    tick, and `fetch_headlines()` only changes every 3 minutes (its own
    cache TTL) — without memoizing, the same ~100 headlines were getting
    re-run through a few dozen regex checks each, every single second,
    for no reason. The input is just a string, so a plain function cache
    is safe (no session/request state involved).
    """
    if is_clickbait(headline):
        return False
    h = headline.lower()
    # Routine Fed supervisory paperwork (stress tests, enforcement
    # actions, etc.) is excluded outright — this used to only guard the
    # strict FED_BOC_INCLUDE path above, but a stress-test press release
    # mentioning "recession" (as in "confirms banks can weather a severe
    # recession") was slipping in through GENERAL_MARKET_TERMS instead,
    # which this blanket check up front closes for good.
    if _contains_any(h, FED_BOC_EXCLUDE):
        return False
    if TICKER_PATTERN.search(headline):
        return True
    if _contains_any(h, FED_BOC_INCLUDE):
        return True
    return _contains_any(h, GENERAL_MARKET_TERMS)


@functools.lru_cache(maxsize=2048)
def classify(headline: str) -> str | None:
    """Cached for the same reason as is_market_relevant above."""
    h = headline.lower()
    if _contains_any(h, FED_BOC_INCLUDE) and not _contains_any(h, FED_BOC_EXCLUDE):
        return "Fed/BoC"
    if _contains_any(h, DATA_PRINT_TERMS) and _contains_any(h, SURPRISE_TERMS):
        return "Data Surprise"
    if _contains_any(h, EARNINGS_COMPANIES) and _contains_any(h, EARNINGS_TERMS):
        return "Earnings"
    if _contains_any(h, MACRO_SHOCK_TERMS):
        return "Macro Shock"
    if _contains_any(h, MA_TERMS) and _contains_any(h, MA_SCALE_TERMS):
        return "Mergers"
    if _contains_any(h, MILESTONE_TERMS):
        return "Milestone"
    return None


def is_important(headline: str) -> bool:
    """True if this headline matches one of the strict breaking
    categories above — decides red (breaking) vs black (market news) in
    the alert bar.

    This used to be its own separate, looser check: a flat OR across
    every term in every category's list, with no requirement that a
    topic term be paired with its qualifier the way classify() requires
    (a data-print term needs a surprise word alongside it; a company
    name needs an earnings word alongside it). That looseness meant a
    headline just containing "Apple" or "CPI" — with zero surprising or
    earnings-related content — still flagged as breaking. Now it's
    exactly classify()'s pairing logic; nothing gets to skip it.
    """
    return classify(headline) is not None


def category_class(category: str) -> str:
    """CSS class for a classify()/"Market News" category — shared so the
    News page's row accent color and the alert bar's tag color are always
    the same mapping, not two copies that could drift apart."""
    return "news-cat-" + category.lower().replace("/", "-").replace(" ", "-")


@st.cache_data(ttl=3 * 60, show_spinner=False)
def fetch_headlines() -> list[dict]:
    items = []
    for url, source in FEEDS:
        try:
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                if title:
                    items.append({"headline": title, "link": link, "source": source})
        except Exception:
            continue  # one dead/slow feed shouldn't take down the others
    return items


def get_new_alerts() -> list[dict]:
    """Flags fresh headlines that qualify for the News page; only returns
    ones not already seen this session. Uses the same `is_market_relevant`
    filter as the News page itself (rather than the narrower `classify()`
    categories) so the breaking-news bar is just the News page's feed,
    surfaced the moment each headline first appears.

    `classify()` still runs for a more specific tag (Fed/BoC, Data
    Surprise, Earnings, Macro Shock) when a headline happens to match one
    of those; anything else that's still market-relevant is tagged
    generically so it isn't dropped.

    The very first call establishes a baseline (marks whatever already
    qualifies as "seen" without alerting) so opening the dashboard doesn't
    immediately flood every historical headline as if it just broke.
    """
    seen = st.session_state.setdefault("seen_headlines", set())
    baseline_done = st.session_state.get("news_baseline_done", False)

    alerts = []
    for item in fetch_headlines():
        if not is_market_relevant(item["headline"]):
            continue
        category = classify(item["headline"]) or "Market News"
        h = hashlib.sha1(item["headline"].encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        if baseline_done:
            alerts.append({**item, "category": category, "important": is_important(item["headline"])})

    st.session_state["news_baseline_done"] = True
    return alerts


def render_alert_bar(alert: dict, elapsed: float):
    """Bottom-strip takeover bar (normally the release-calendar ticker): a
    label stretches into view, holds, then slides aside to reveal the
    category tag + headline underneath.

    Red "BREAKING NEWS" when the headline references one of our
    important target words (`is_important`), black "MARKET NEWS"
    otherwise, so the bar's own color signals how urgent a given item
    actually is before you even read the headline.
    """
    if elapsed < STRETCH_END:
        label_progress = elapsed / STRETCH_END
        label_style = f"opacity: {label_progress:.2f}; transform: translateY(0); letter-spacing: {0.5 * label_progress:.2f}em;"
        headline_style = "opacity: 0; transform: translateX(16px);"
    elif elapsed < SLIDE_END:
        slide_progress = (elapsed - STRETCH_END) / (SLIDE_END - STRETCH_END)
        label_style = f"opacity: {max(1 - slide_progress * 1.3, 0):.2f}; transform: translateX({-140 * slide_progress:.0f}%); letter-spacing: 0.5em;"
        headline_style = f"opacity: {min(slide_progress * 1.3, 1):.2f}; transform: translateX({16 * (1 - slide_progress):.0f}px);"
    else:
        label_style = "opacity: 0; transform: translateX(-140%);"
        headline_style = "opacity: 1; transform: translateX(0);"

    is_breaking = alert.get("important", alert["category"] != "Market News")
    bar_class = "news-alert-bar" if is_breaking else "news-alert-bar-market"
    label_text = "BREAKING NEWS" if is_breaking else "MARKET NEWS"
    st.markdown(
        f"""<div class="{bar_class}">
            <span class="news-breaking-label" style="{label_style}">{label_text}</span>
            <span class="news-alert-tag {category_class(alert['category'])}" style="{headline_style}">{alert['category']}</span>
            <span class="news-alert-headline" style="{headline_style}">{alert['headline']}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def update_top_alert(new_alerts: list[dict]) -> None:
    """Whenever a fresh important (red) headline comes through, it takes
    over the persistent top banner, replacing whatever was there before —
    "the next red headline" is exactly the next call here where an alert
    has important=True. Call once per rerun with whatever `get_new_alerts`
    just returned."""
    for alert in new_alerts:
        if alert.get("important"):
            st.session_state["top_alert"] = {**alert, "set_at": time.time()}


def render_top_alert_bar() -> None:
    """Renders the persistent top banner if a red headline is still
    within its hold window (TOP_ALERT_HOLD_SECONDS) — a plain static bar
    in normal document flow, not fixed/animated, since it needs to sit
    there unchanged for up to two hours rather than play an intro."""
    top_alert = st.session_state.get("top_alert")
    if not top_alert:
        return
    expired = time.time() - top_alert["set_at"] > TOP_ALERT_HOLD_SECONDS
    # Re-checked against today's filters, not just re-fetched under them —
    # this kiosk keeps one browser session open for hours/days, so a
    # headline queued under a since-tightened filter would otherwise keep
    # showing for its full 2-hour hold even though it'd never qualify if
    # seen fresh right now.
    stale = not is_market_relevant(top_alert["headline"]) or not is_important(top_alert["headline"])
    if expired or stale:
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
