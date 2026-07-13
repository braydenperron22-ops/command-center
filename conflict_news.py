"""Google News RSS for the Conflicts page — no key needed, and its `when:7d`
search operator gives genuine week-old history directly, rather than
needing to accumulate today's snapshots locally over multiple days.

Shares news.is_clickbait() with the News page's filtering so a teaser
headline ("What Iran's next move means for the region?") doesn't sneak
onto this page just because it wasn't caught by the finance-specific
clickbait phrasing — the question-mark check alone covers most of it.
"""

from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests
import streamlit as st

import fetch_throttle
import news
from config import CONFLICT_WINDOW_DAYS

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
QUERY = "war OR conflict OR clashes OR ceasefire OR insurgency OR airstrike"


def _parse_pub_date(raw: str) -> datetime | None:
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fetch_conflict_headlines() -> list[dict]:
    """Google's own feed order isn't newest-first (confirmed by
    inspection — dates come back mixed), so `published` is captured here
    for the Conflicts page to sort and age-color by, not assumed."""
    params = {
        "q": f"{QUERY} when:{CONFLICT_WINDOW_DAYS}d",
        "hl": "en-US", "gl": "US", "ceid": "US:en",
    }
    try:
        fetch_throttle.wait_turn()
        resp = requests.get(GOOGLE_NEWS_RSS, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except (requests.RequestException, ElementTree.ParseError):
        return []

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if title and not news.is_clickbait(title):
            items.append({
                "headline": title,
                "published": _parse_pub_date(item.findtext("pubDate") or ""),
            })
    return items
