"""RSS-based, keyword-filtered news alerts for the side toast.

No API key: pulls from the Fed's own press-release feed (zero-noise, it IS
the source) plus a few general finance RSS feeds, then applies a strict
keyword filter so only Fed/BoC policy, surprising CPI/jobs/GDP prints,
mega-cap earnings, and clear macro shocks ever qualify.
"""

import hashlib
from xml.etree import ElementTree

import requests
import streamlit as st

FEEDS = [
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "http://feeds.marketwatch.com/marketwatch/topstories/",
    "https://finance.yahoo.com/news/rssindex",
]

TOAST_SECONDS = 15

FED_BOC_INCLUDE = [
    "fomc statement", "fomc meeting", "rate decision", "interest rate decision",
    "rate hike", "rate cut", "raises rates", "cuts rates", "holds rates", "holds interest rates",
    "jerome powell", "bank of canada", "boc rate", "tiff macklem", "fed chair",
    "takes oath of office", "sworn in as chair", "steps down as chair", "resigns as chair",
    "named fed chair", "confirmed as fed chair",
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
    "gross domestic product", "inflation report",
]
SURPRISE_TERMS = [
    "unexpectedly", "surprise", "beats estimates", "misses estimates",
    "higher than expected", "lower than expected", "surges", "plunges",
    "hotter than expected", "cooler than expected", "tops forecast", "misses forecast",
    "jumps", "tumbles", "slows more than",
]
EARNINGS_COMPANIES = [
    "apple", "aapl", "microsoft", "msft", "nvidia", "nvda",
    "amazon", "amzn", "alphabet", "google", "googl", "meta platforms",
    "jpmorgan", "jp morgan", "bank of america", "bofa",
]
EARNINGS_TERMS = [
    "earnings", "quarterly results", "beats estimates", "misses estimates",
    "guidance", "q1 results", "q2 results", "q3 results", "q4 results", "profit",
]
MACRO_SHOCK_TERMS = [
    "recession fears", "banking crisis", "financial crisis", "market crash",
    "stocks plunge", "stock market sell-off", "bear market", "debt default",
    "credit downgrade", "circuit breaker", "market meltdown", "stocks tumble",
]


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(t in text for t in terms)


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
    """Classify fresh headlines; only returns ones not already seen this session.

    The very first call establishes a baseline (marks whatever already
    qualifies as "seen" without alerting) so opening the dashboard doesn't
    immediately flood every historical headline as if it just broke.
    """
    seen = st.session_state.setdefault("seen_headlines", set())
    baseline_done = st.session_state.get("news_baseline_done", False)

    alerts = []
    for item in fetch_headlines():
        category = classify(item["headline"])
        if not category:
            continue
        h = hashlib.sha1(item["headline"].encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        if baseline_done:
            alerts.append({**item, "category": category})

    st.session_state["news_baseline_done"] = True
    return alerts


def render_alert_bar(alert: dict):
    """Breaking-news style bar that takes over the bottom strip (normally
    the release-calendar ticker) for the duration this alert is shown.
    """
    category_class = "news-cat-" + alert["category"].lower().replace("/", "-").replace(" ", "-")
    st.markdown(
        f"""<div class="news-alert-bar {category_class}">
            <span class="news-alert-tag">{alert['category']}</span>
            <span class="news-alert-headline">{alert['headline']}</span>
        </div>""",
        unsafe_allow_html=True,
    )
