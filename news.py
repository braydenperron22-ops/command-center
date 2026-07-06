"""RSS-based, keyword-filtered news — powers breaking-news alerts AND the
News page's rolling 24h feed, plus keyword-scanning for the Conflicts page.

No API key: pulls from the Fed's own press-release feed (zero-noise, it IS
the source) plus a few general finance RSS feeds. The breaking-news bar
uses the exact same `is_market_relevant` filter as the News page — it's
the same headline pool, just surfaced immediately as each one first
appears rather than waiting to be read on the News page. `classify()`
still runs to give Fed/BoC, Data Surprise, Earnings, and Macro Shock
headlines their own tag; anything else market-relevant is tagged
"Market News" instead of being dropped.
"""

import hashlib
import re
from xml.etree import ElementTree

import requests
import streamlit as st

FEEDS = [
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "http://feeds.marketwatch.com/marketwatch/topstories/",
    "https://finance.yahoo.com/news/rssindex",
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
EARNINGS_COMPANIES = [
    "apple", "aapl", "microsoft", "msft", "nvidia", "nvda",
    "amazon", "amzn", "alphabet", "google", "googl", "meta platforms",
    "jpmorgan", "jp morgan", "bank of america", "bofa",
    "tesla", "tsla", "netflix", "nflx", "broadcom", "avgo", "berkshire hathaway",
]
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
GENERAL_MARKET_TERMS = [
    "stock", "shares", "earnings", "ipo", "buy rating", "sell rating",
    "price target", "outperform", "underperform", "upgrade", "downgrade",
    "dividend", "etf", "market cap", "rate",
    "inflation", "cpi", "gdp", "jobs report", "unemployment", "recession",
    "economy", "economic", "rally", "sell-off", "selloff", "surge", "plunge",
    "futures", "wall street", "dow jones", "s&p", "nasdaq", "oil", "opec",
    "crude", "takeover", "acquisition", "merger", "analyst", "valuation",
    "jim cramer", "warren buffett", "buffett", "hedge fund", "portfolio",
]
TICKER_PATTERN = re.compile(r"\([A-Z]{2,5}\)")


def _contains_any(text: str, terms: list[str]) -> bool:
    """Whole-word/phrase match — plain substring matching let terms like
    "shares" match inside unrelated words ("Bankshares", "Bancshares")."""
    return any(re.search(r"\b" + re.escape(t) + r"\b", text) for t in terms)


def is_market_relevant(headline: str) -> bool:
    """Looser filter for the News page: any real finance/market signal
    qualifies, not just the narrow topic+surprise combos above."""
    if TICKER_PATTERN.search(headline):
        return True
    h = headline.lower()
    if _contains_any(h, FED_BOC_INCLUDE) and not _contains_any(h, FED_BOC_EXCLUDE):
        return True
    return _contains_any(h, GENERAL_MARKET_TERMS)


# "This headline matters enough to go red" words — every term across the
# topic/qualifier categories above, checked as a simple membership test
# rather than requiring the topic+qualifier pairing classify() needs.
# Anything from the News feed that hits one of these is a breaking-red
# item; everything else market-relevant is black.
IMPORTANT_OTHER_TERMS = DATA_PRINT_TERMS + SURPRISE_TERMS + EARNINGS_COMPANIES + MACRO_SHOCK_TERMS


def is_important(headline: str) -> bool:
    """True if the headline references one of our important target
    words — decides red (breaking) vs black (market news) in the alert
    bar, independent of the category label classify() picks."""
    h = headline.lower()
    if _contains_any(h, FED_BOC_INCLUDE) and not _contains_any(h, FED_BOC_EXCLUDE):
        return True
    return _contains_any(h, IMPORTANT_OTHER_TERMS)


def classify(headline: str) -> str | None:
    h = headline.lower()
    if _contains_any(h, FED_BOC_INCLUDE) and not _contains_any(h, FED_BOC_EXCLUDE):
        return "Fed/BoC"
    if _contains_any(h, DATA_PRINT_TERMS) and _contains_any(h, SURPRISE_TERMS):
        return "Data Surprise"
    if _contains_any(h, EARNINGS_COMPANIES) and _contains_any(h, EARNINGS_TERMS):
        return "Earnings"
    if _contains_any(h, MACRO_SHOCK_TERMS):
        return "Macro Shock"
    return None


@st.cache_data(ttl=3 * 60, show_spinner=False)
def fetch_headlines() -> list[dict]:
    items = []
    for url in FEEDS:
        try:
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                if title:
                    items.append({"headline": title, "link": link})
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
    category_class = "news-cat-" + alert["category"].lower().replace("/", "-").replace(" ", "-")
    st.markdown(
        f"""<div class="{bar_class}">
            <span class="news-breaking-label" style="{label_style}">{label_text}</span>
            <span class="news-alert-tag {category_class}" style="{headline_style}">{alert['category']}</span>
            <span class="news-alert-headline" style="{headline_style}">{alert['headline']}</span>
        </div>""",
        unsafe_allow_html=True,
    )
