"""Environment Canada public weather alerts (special weather statements,
warnings, watches) for North Bay — free, no API key, no rate limit beyond
being a polite poller. Environment Canada publishes a plain ATOM feed per
alert region at a fixed URL (weather.gc.ca/rss/battleboard/{code}_e.xml);
this is the North Bay - Powassan - Mattawa region.

When nothing is in effect, the feed still returns one entry whose title
is literally "No alerts in effect, <region>" — that's filtered out here
so callers only ever see genuine active alerts.
"""

from xml.etree import ElementTree

import requests
import streamlit as st

import fetch_throttle
from config import EC_ALERT_REGION_CODE

ALERT_URL = f"https://weather.gc.ca/rss/battleboard/{EC_ALERT_REGION_CODE}_e.xml"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@st.cache_data(ttl=15 * 60, show_spinner=False)
def fetch_alerts() -> list[dict]:
    """Returns active alerts as [{"title": ..., "summary": ...}, ...],
    or [] when nothing is in effect (or the feed can't be reached — a
    dead feed shouldn't ever crash the dashboard, just means no alert
    banner is shown)."""
    try:
        fetch_throttle.wait_turn()
        resp = requests.get(ALERT_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except Exception:
        return []

    alerts = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
        if not title or title.lower().startswith("no alerts in effect"):
            continue
        summary = (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").strip()
        alerts.append({"title": title, "summary": summary})
    return alerts
