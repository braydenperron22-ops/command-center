"""Google News RSS for the Conflicts page — no key needed, and its `when:7d`
search operator gives genuine week-old history directly, rather than
needing to accumulate today's snapshots locally over multiple days."""

from xml.etree import ElementTree

import requests
import streamlit as st

from config import CONFLICT_WINDOW_DAYS

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
QUERY = "war OR conflict OR clashes OR ceasefire OR insurgency OR airstrike"


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fetch_conflict_headlines() -> list[dict]:
    params = {
        "q": f"{QUERY} when:{CONFLICT_WINDOW_DAYS}d",
        "hl": "en-US", "gl": "US", "ceid": "US:en",
    }
    try:
        resp = requests.get(GOOGLE_NEWS_RSS, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except (requests.RequestException, ElementTree.ParseError):
        return []

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if title:
            items.append({"headline": title})
    return items
