"""Local North Bay news, real stuff only — police/OPP incident beats,
official 511 Ontario road events, and keyword-matched construction
items, not general local-news (which mixes in lifestyle pieces and
cross-posted "Good morning, North Bay!" weather fluff from other
sections). Deliberately separate from news.py: that module's whole
classification pipeline (decide(), AI-judged — see its own docstring)
is tuned for financial news specifically — a police-beat headline
would just get discarded by it, not surfaced.
"""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import asin, cos, radians, sin, sqrt
from xml.etree import ElementTree

import requests
import streamlit as st

import fetch_throttle
from config import COMMUTE_DESTINATION, COMMUTE_ORIGIN

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

# Official Ministry of Transportation feed — 400+ events province-wide
# at any given time, almost all irrelevant here, so filtered to
# whichever are actually near the commute (either end of it, not just
# home) rather than the whole province. Real government data, not a
# news article's paraphrase of it — complements (doesn't duplicate)
# TomTom's live delay number by saying what's actually causing it.
ROAD_EVENTS_URL = "https://511on.ca/api/v2/get/event"
ROAD_EVENTS_SOURCE = "511 Ontario"
ROAD_EVENT_TYPES = {"roadwork", "accidentsAndIncidents"}
NEARBY_RADIUS_KM = 25

CACHE_TTL_SECONDS = 15 * 60
MAX_ITEMS = 5

_CONSTRUCTION_PATTERN = re.compile("|".join(re.escape(t) for t in CONSTRUCTION_TERMS))


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def _fetch_road_events() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(ROAD_EVENTS_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    items = []
    for event in resp.json():
        if event.get("EventType") not in ROAD_EVENT_TYPES:
            continue
        lat, lon = event.get("Latitude"), event.get("Longitude")
        description = (event.get("Description") or "").strip()
        if lat is None or lon is None or not description:
            continue
        near = (
            _distance_km(lat, lon, COMMUTE_ORIGIN["lat"], COMMUTE_ORIGIN["lon"]) <= NEARBY_RADIUS_KM
            or _distance_km(lat, lon, COMMUTE_DESTINATION["lat"], COMMUTE_DESTINATION["lon"]) <= NEARBY_RADIUS_KM
        )
        if not near:
            continue
        last_updated = event.get("LastUpdated")
        published = datetime.fromtimestamp(last_updated, tz=timezone.utc) if last_updated else None
        items.append({"headline": description, "link": "", "source": ROAD_EVENTS_SOURCE, "published": published})
    return items


def _fetch_feed(url: str, source: str) -> list[dict]:
    fetch_throttle.wait_turn()
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

    try:
        items.extend(_fetch_road_events())
    except Exception:
        pass

    # Undated items (parse failure) sort last rather than crashing on a
    # None comparison — still shown, just not trusted to be "recent."
    items.sort(key=lambda i: i["published"] or _EPOCH, reverse=True)
    return items[:MAX_ITEMS]
