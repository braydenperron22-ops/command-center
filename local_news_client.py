"""Local North Bay news, real stuff only — police/OPP incident beats
plus road-closure/construction items, not general local-news (which
mixes in lifestyle pieces and cross-posted "Good morning, North Bay!"
weather fluff from other sections). Deliberately separate from news.py:
that module's entire filtering apparatus (is_market_relevant, classify,
FED_BOC_INCLUDE, ...) is tuned for financial news specifically — a
police-beat headline would just get discarded by it, not surfaced.
"""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests
import streamlit as st

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# Police-beat sections are inherently "incidents" — every item there
# qualifies without needing a keyword filter.
INCIDENT_FEEDS = [
    ("https://www.baytoday.ca/rss/city-police-beat", "North Bay Police"),
    ("https://www.baytoday.ca/rss/opp-beat", "OPP"),
]
# Construction/road-closure news has no section of its own, so it's
# pulled from the general local-news feed instead and kept only on a
# real match — that feed otherwise mixes in the fluff described above.
CONSTRUCTION_FEED = ("https://www.baytoday.ca/rss/local-news", "BayToday")
CONSTRUCTION_TERMS = [
    "road closure", "road closed", "lane closure", "closed to traffic",
    "detour", "construction", "repaving", "road work", "roadwork",
    "bridge closure", "highway closure", "under construction",
    "traffic advisory", "water main",
]

CACHE_TTL_SECONDS = 15 * 60
MAX_ITEMS = 5

_CONSTRUCTION_PATTERN = re.compile("|".join(re.escape(t) for t in CONSTRUCTION_TERMS))


def _fetch_feed(url: str, source: str) -> list[dict]:
    resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = item.findtext("pubDate")
        if not title:
            continue
        try:
            published = parsedate_to_datetime(pub_date) if pub_date else None
            # Normalized to aware (assume UTC) — pubDate strings without
            # a timezone offset parse to naive, and a naive/aware mix
            # would crash the sort below when comparing the two.
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            published = None
        items.append({"headline": title, "link": link, "source": source, "published": published})
    return items


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_items() -> list[dict]:
    """Most recent incident/construction items, newest first, capped to
    MAX_ITEMS — a glance-only list, not something to scroll through."""
    items = []
    for url, source in INCIDENT_FEEDS:
        try:
            items.extend(_fetch_feed(url, source))
        except Exception:
            continue

    try:
        for item in _fetch_feed(*CONSTRUCTION_FEED):
            if _CONSTRUCTION_PATTERN.search(item["headline"].lower()):
                items.append(item)
    except Exception:
        pass

    # Undated items (parse failure) sort last rather than crashing on a
    # None comparison — still shown, just not trusted to be "recent."
    items.sort(key=lambda i: i["published"] or _EPOCH, reverse=True)
    return items[:MAX_ITEMS]
